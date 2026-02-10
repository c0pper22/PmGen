import os
import traceback
from datetime import datetime
from dataclasses import dataclass
from fnmatch import fnmatchcase
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QObject, pyqtSignal

@dataclass
class BulkConfig:
    top_n: int = 25
    out_dir: str = ""
    pool_size: int = 4
    blacklist: list[str] = None
    show_all: bool = False
    def __post_init__(self):
        if self.blacklist is None:
            self.blacklist = []

class BulkRunner(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, cfg: BulkConfig, threshold: float, life_basis: str, threshold_enabled: bool = True,
                 # Updated parameters
                 unpack_max_enabled: bool = False, unpack_max_months: int = 0,
                 unpack_min_enabled: bool = False, unpack_min_months: int = 0):
        super().__init__()
        self.cfg = cfg
        self.threshold = threshold
        self.life_basis = life_basis
        self.threshold_enabled = bool(threshold_enabled)
        self._blacklist = [p.upper() for p in (cfg.blacklist or [])]
        
        # Max Age (Exclude Older Than)
        self._unpack_max_enabled = bool(unpack_max_enabled)
        self._unpack_max_months = max(0, min(120, int(unpack_max_months)))

        # Min Age (Exclude Newer Than)
        self._unpack_min_enabled = bool(unpack_min_enabled)
        self._unpack_min_months = max(0, min(120, int(unpack_min_months)))

    def _is_blacklisted(self, serial: str) -> bool:
        s = (serial or "").upper()
        for pat in (self._blacklist or []):
            if fnmatchcase(s, pat):
                return True
        return False

    def _prefilter_by_unpack_date(self, serials: list[str], pool) -> list[str]:
        # If neither filter is on, skip everything
        if not self._unpack_max_enabled and not self._unpack_min_enabled:
            self.progress.emit("[Info] Unpack date filters disabled.")
            return list(serials)

        try:
            from pmgen.io.http_client import get_unpacking_date as _get_unpack
            _sig_uses_kw = True
        except Exception:
            try:
                from pmgen.io.http_client import get_unpack_date as _get_unpack
                _sig_uses_kw = False
            except Exception as e:
                self.progress.emit(f"[Bulk] Unpack filter unavailable ({e}).")
                return list(serials)

        from datetime import date
        import calendar

        def _add_months(d: date, months: int) -> date:
            y = d.year + (d.month - 1 + months) // 12
            m = (d.month - 1 + months) % 12 + 1
            return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

        kept = []
        
        with pool.acquire() as sess:
            msg_parts = []
            if self._unpack_max_enabled: msg_parts.append(f"Older than {self._unpack_max_months}mo")
            if self._unpack_min_enabled: msg_parts.append(f"Newer than {self._unpack_min_months}mo")
            
            self.progress.emit(f"[Bulk] Applying filters: {', '.join(msg_parts)}")
            
            count = 0
            total = len(serials)
            today = date.today()
            
            for s in serials:
                count += 1
                if count % 10 == 0: 
                    self.progress.emit(f"[Bulk] Checking dates... ({count}/{total})")
                    
                try:
                    if _sig_uses_kw:
                        d = _get_unpack(s, sess=sess)
                    else:
                        d = _get_unpack(s, sess)
                except Exception:
                    kept.append(s) # Keep on error
                    continue

                if not d:
                    kept.append(s) # Keep if no date found
                    continue

                # --- 1. Max Age Check (Exclude Old Stuff) ---
                if self._unpack_max_enabled:
                    cutoff_max = _add_months(d, self._unpack_max_months)
                    if today > cutoff_max:
                        # Too old
                        kept_months = (today.year - cutoff_max.year) * 12 + (today.month - cutoff_max.month)
                        self.progress.emit(f"[Bulk] Filtered (Too Old): {s} ({d}) is > {self._unpack_max_months} months old")
                        continue 

                # --- 2. Min Age Check (Exclude New Stuff) ---
                if self._unpack_min_enabled:
                    cutoff_min = _add_months(d, self._unpack_min_months)
                    if today < cutoff_min:
                        # Too new
                        self.progress.emit(f"[Bulk] Filtered (Too New): {s} ({d}) is < {self._unpack_min_months} months old")
                        continue

                kept.append(s)
        return kept

    def _fmt_pct(self, p):
        if p is None: return "—"
        try: return f"{(float(p) * 100):.1f}%"
        except Exception: return "—"

    def run(self):
        pool = None
        try:
            # 1. Validation
            if not self.cfg.out_dir or not self.cfg.out_dir.strip():
                raise ValueError("Output directory is not set.")
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            base_path = os.path.join(self.cfg.out_dir, date_str)
            final_out_dir = base_path
            
            counter = 1
            while os.path.exists(final_out_dir):
                final_out_dir = f"{base_path} ({counter})"
                counter += 1
            
            os.makedirs(final_out_dir, exist_ok=True)
            # -----------------------------------------------

            from pmgen.io.http_client import SessionPool, get_serials_after_login, get_service_file_bytes, get_unpacking_date
            from pmgen.parsing.parse_pm_report import parse_pm_report
            from pmgen.engine.run_rules import run_rules
            from pmgen.engine.single_report import create_pdf_report
            from pmgen.engine.final_report import write_final_summary_pdf

            self.progress.emit("[Info] Creating session pool...")
            pool = SessionPool(self.cfg.pool_size)

            # 2. Fetch Serials
            with pool.acquire() as sess:
                serials = get_serials_after_login(sess)
            self.progress.emit(f"[Info] Found {len(serials)} Active Serials.")

            # 3. Apply Blacklist
            serials0 = list(serials or [])
            serials1 = [s for s in serials0 if not self._is_blacklisted(s)]
            skipped = len(serials0) - len(serials1)
            if skipped:
                self.progress.emit(f"[Info] Skipped {skipped} serial(s) via blacklist.")
            if not serials1:
                raise RuntimeError("No serials to process after applying blacklist.")

            # 4. Apply Date Filter
            kept_serials = self._prefilter_by_unpack_date(serials1, pool)
            if not kept_serials:
                raise RuntimeError("All serials were filtered out by unpack-date/cutoff logic.")
            
            self.progress.emit(f"[Info] Filtered out {len(serials) - len(kept_serials)} Serials")
            self.progress.emit(f"[Info] Continuing with {len(kept_serials)} Serials")

            thr = self.threshold
            basis = self.life_basis
            show_all = self.cfg.show_all
            thr_enabled = self.threshold_enabled

            # --- HELPER FOR DATA EXTRACTION ---
            def get_val(item, key, default=0.0):
                """Safely get value from object attribute OR dict key"""
                val = getattr(item, key, None)
                if val is not None:
                    return val
                if isinstance(item, dict):
                    return item.get(key, default)
                return default

            def work(serial: str):
                try:
                    with pool.acquire() as sess:
                        # 1. Fetch PM bytes
                        blob = get_service_file_bytes(serial, "PMSupport", sess=sess)
                        # 2. Fetch Unpacking Date (08 mode)
                        unpack_date = get_unpacking_date(serial, sess=sess)
                    
                    report = parse_pm_report(blob)
                    selection = run_rules(report, threshold=thr, life_basis=basis, threshold_enabled=thr_enabled)

                    meta = getattr(selection, "meta", {}) or {}
                    all_items = meta.get("all_items", []) or meta.get("all", []) or getattr(selection, "all_items", []) or []
                    
                    # Calculate best usage percentage
                    best_used = max([float(get_val(f, "life_used", 0.0) or 0.0) for f in all_items], default=0.0)

                    # Pass unpacking_date to the PDF creator
                    create_pdf_report(
                        report=report,
                        selection=selection,
                        threshold=thr,
                        life_basis=basis,
                        show_all=show_all,
                        out_dir=final_out_dir,
                        threshold_enabled=thr_enabled,
                        unpacking_date=unpack_date 
                    )

                    # Return data for the Final Summary
                    return {
                        "serial": (report.headers or {}).get("serial") or serial,
                        "model": (report.headers or {}).get("model")  or "Unknown",
                        "best_used": float(best_used),
                        "text": "None",
                        "grouped": meta.get("selection_pn_grouped", {}) or {},
                        "flat": meta.get("selection_pn", {}) or {},
                        "kit_by_pn": meta.get("kit_by_pn", {}) or {},
                        "due_sources": meta.get("due_sources", {}) or {},
                        "unpacking_date": unpack_date 
                    }
                except Exception as e:
                    return {"serial": serial, "error": str(e), "trace": traceback.format_exc()}

            # 5. Execute Thread Pool
            results = []
            with ThreadPoolExecutor(max_workers=self.cfg.pool_size) as ex:
                futures = {ex.submit(work, s): s for s in kept_serials}
                for fut in as_completed(futures):
                    s = futures[fut]
                    try:
                        res = fut.result()
                        if "error" in res:
                            self.progress.emit(f"[Bulk] {s}: ERROR — {res['error']}")
                        else:
                            self.progress.emit(f"[Bulk] {s}: OK — {self._fmt_pct(res['best_used'])}")
                        results.append(res)
                    except Exception as e:
                        self.progress.emit(f"[Bulk] {s}: CRITICAL — {e}")

            # 6. Final Summary
            ok = [r for r in results if "error" not in r]
            ok.sort(key=lambda r: (r.get("best_used") or 0.0), reverse=True)
            top = ok[: self.cfg.top_n]

            self.progress.emit(f"[Info] Wrote {len(top)} report files to: {final_out_dir}")

            try:
                pdf_path = write_final_summary_pdf(
                    out_dir=final_out_dir,
                    results=results, 
                    top=top,
                    thr=thr,
                    basis=basis,
                    filename="Final_Summary.pdf",
                    threshold_enabled=thr_enabled
                )
                self.finished.emit(f"[Info] Complete. Summary written to: {pdf_path}")
            except Exception as e:
                self.finished.emit(f"[Info] Reports generated, but Summary PDF failed: {e}")

        except Exception as e:
            self.finished.emit(f"[Info] Failed: {e}")
            traceback.print_exc()
        finally:
            if pool:
                try: pool.close()
                except: pass