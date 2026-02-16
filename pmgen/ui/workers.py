import os
import logging
import traceback
from fnmatch import fnmatchcase
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QThread

@dataclass
class BulkConfig:
    top_n: int = 25
    out_dir: str = ""
    pool_size: int = 4
    blacklist: list[str] = None
    show_all: bool = False

    def __post_init__(self):
        if self.blacklist is None: self.blacklist = []

class BulkRunner(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    # Signal Signature: (Serial, Status, Result, Model, UnpackDate)
    item_updated = pyqtSignal(str, str, str, str, str)

    def __init__(self, cfg: BulkConfig, threshold: float, life_basis: str,
                 threshold_enabled: bool = True,
                 unpack_max_enabled: bool = False, unpack_max_months: int = 0,
                 unpack_min_enabled: bool = False, unpack_min_months: int = 0):
        super().__init__()
        self.cfg = cfg
        self.threshold = threshold
        self.life_basis = life_basis
        self.threshold_enabled = bool(threshold_enabled)
        self._blacklist = [p.upper() for p in (cfg.blacklist or [])]

        self._unpack_max_enabled = bool(unpack_max_enabled)
        self._unpack_max_months = max(0, min(120, int(unpack_max_months)))
        self._unpack_min_enabled = bool(unpack_min_enabled)
        self._unpack_min_months = max(0, min(120, int(unpack_min_months)))

    def _update_pool_progress(self, current, total):
        self.progress.emit(f"[Info] Creating session pool ({current}/{total})...")

    def _is_blacklisted(self, serial: str) -> bool:
        s = (serial or "").upper()
        for pat in (self._blacklist or []):
            if fnmatchcase(s, pat): return True
        return False

    def _prefilter_by_unpack_date(self, serials: list[str], pool) -> list[str]:
        if not self._unpack_max_enabled and not self._unpack_min_enabled:
            self.progress.emit("[Info] Unpack date filters disabled.")
            return list(serials)

        try:
            from pmgen.io.http_client import get_device_info_08
            _use_combined = True
        except ImportError:
            from pmgen.io.http_client import get_unpacking_date as _get_unpack
            _use_combined = False

        from datetime import date
        import calendar

        def _add_months(d: date, months: int) -> date:
            y = d.year + (d.month - 1 + months) // 12
            m = (d.month - 1 + months) % 12 + 1
            return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

        kept = []

        self.progress.emit("[Bulk] Fetching dates for pre-filtering...")

        with pool.acquire() as sess:
            total = len(serials)
            count = 0
            today = date.today()

            for s in serials:
                # CHANGE 2: Check for stop signal during pre-filtering
                if QThread.currentThread().isInterruptionRequested():
                    self.progress.emit("[Info] Date check stopped by user.")
                    return kept

                count += 1
                self.progress_value.emit(count, total)

                if count % 5 == 0:
                    self.progress.emit(f"[Bulk] Checking dates... ({count}/{total})")

                d = None
                model = "Unknown"

                try:
                    if _use_combined:
                        info = get_device_info_08(s, sess=sess)
                        d = info.get("date")
                        model = info.get("model", "Unknown")
                    else:
                        d = _get_unpack(s, sess=sess)
                except Exception:
                    kept.append(s)
                    continue

                if model and model != "Unknown":
                     self.item_updated.emit(s, "Queued", "", model, "")

                if not d:
                    kept.append(s)
                    continue

                d_str = d.strftime("%Y-%m-%d")

                # Max Age Check
                if self._unpack_max_enabled:
                    cutoff_max = _add_months(d, self._unpack_max_months)
                    if today > cutoff_max:
                        self.item_updated.emit(s, "Filtered", "Too Old", model, d_str)
                        continue

                # Min Age Check
                if self._unpack_min_enabled:
                    cutoff_min = _add_months(d, self._unpack_min_months)
                    if today < cutoff_min:
                        self.item_updated.emit(s, "Filtered", "Too New", model, d_str)
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

            from pmgen.io.http_client import SessionPool, get_serials_after_login, get_service_file_bytes, get_unpacking_date
            from pmgen.parsing.parse_pm_report import parse_pm_report
            from pmgen.engine.run_rules import run_rules
            from pmgen.engine.single_report import create_pdf_report
            from pmgen.engine.final_report import write_final_summary_pdf

            pool_size = self.cfg.pool_size
            self.progress.emit(f"[Info] Initializing {pool_size} sessions...")

            try:
                pool = SessionPool(pool_size, callback=self._update_pool_progress)

            except Exception as e:
                self.progress.emit(f"[Info] Failed to create pool: {e}")
                return

            with pool.acquire() as sess:
                serials = get_serials_after_login(sess)

            self.progress.emit(f"[Info] Found {len(serials)} Active Serials.")

            serials0 = list(serials or [])
            serials1 = [s for s in serials0 if not self._is_blacklisted(s)]

            for s in serials1:
                self.item_updated.emit(s, "Queued", "", "Unknown", "")

            kept_serials = self._prefilter_by_unpack_date(serials1, pool)
            
            # Stop check in case user stopped during pre-filter
            if QThread.currentThread().isInterruptionRequested():
                self.finished.emit("[Info] Stopped.")
                return

            self.progress.emit(f"[Info] Processing {len(kept_serials)} Serials...")

            thr = self.threshold
            basis = self.life_basis
            show_all = self.cfg.show_all
            thr_enabled = self.threshold_enabled

            def get_val(item, key, default=0.0):
                val = getattr(item, key, None)
                if val is not None: return val
                if isinstance(item, dict): return item.get(key, default)
                return default

            def work(serial: str):
                self.item_updated.emit(serial, "Processing", "...", "", "")
                try:
                    with pool.acquire() as sess:
                        blob = get_service_file_bytes(serial, "PMSupport", sess=sess)
                        unpack_date = get_unpacking_date(serial, sess=sess)

                    report = parse_pm_report(blob)
                    model_name = (report.headers or {}).get("model") or "Unknown"

                    selection = run_rules(report, threshold=thr, life_basis=basis, threshold_enabled=thr_enabled)

                    meta = getattr(selection, "meta", {}) or {}
                    all_items = meta.get("all_items", []) or meta.get("all", []) or getattr(selection, "all_items", []) or []
                    best_used = max([float(get_val(f, "life_used", 0.0) or 0.0) for f in all_items], default=0.0)

                    create_pdf_report(
                        report=report, selection=selection, threshold=thr, life_basis=basis,
                        show_all=show_all, out_dir=final_out_dir, threshold_enabled=thr_enabled,
                        unpacking_date=unpack_date
                    )

                    pct_str = self._fmt_pct(best_used)
                    d_str = unpack_date.strftime("%Y-%m-%d") if unpack_date else ""

                    self.item_updated.emit(serial, "Done", pct_str, model_name, d_str)

                    return {
                        "serial": (report.headers or {}).get("serial") or serial,
                        "model": model_name,
                        "best_used": float(best_used),
                        "text": "None",
                        "grouped": meta.get("selection_pn_grouped", {}) or {},
                        "flat": meta.get("selection_pn", {}) or {},
                        "kit_by_pn": meta.get("kit_by_pn", {}) or {},
                        "due_sources": meta.get("due_sources", {}) or {},
                        "unpacking_date": unpack_date
                    }
                except Exception as e:
                    self.item_updated.emit(serial, "Failed", str(e), "", "")
                    return {"serial": serial, "error": str(e), "trace": traceback.format_exc()}

            results = []
            completed_count = 0
            total_work = len(kept_serials)

            if total_work > 0:
                with ThreadPoolExecutor(max_workers=self.cfg.pool_size) as ex:
                    futures = {ex.submit(work, s): s for s in kept_serials}
                    
                    for fut in as_completed(futures):
                        # CHANGE 3: Check for stop signal inside main loop
                        if QThread.currentThread().isInterruptionRequested():
                            self.progress.emit("[Info] Stop requested. Cancelling pending tasks...")
                            # Cancel any tasks that haven't started yet
                            for f in futures:
                                f.cancel()
                            break
                        
                        s = futures[fut]
                        completed_count += 1
                        self.progress_value.emit(completed_count, total_work)

                        try:
                            res = fut.result()
                            if "error" in res:
                                self.progress.emit(f"[Bulk] {s}: ERROR — {res['error']}")
                            else:
                                self.progress.emit(f"[Bulk] {s}: OK — {self._fmt_pct(res['best_used'])}")
                            results.append(res)
                        except Exception as e:
                            self.progress.emit(f"[Bulk] {s}: CRITICAL — {e}")
            else:
                self.progress.emit("[Info] No serials to process after filtering.")
            
            # If stopped, we still generate reports for whatever finished
            if QThread.currentThread().isInterruptionRequested():
                 self.finished.emit("[Info] Process Stopped by User.")
                 return

            ok = [r for r in results if "error" not in r]
            ok.sort(key=lambda r: (r.get("best_used") or 0.0), reverse=True)
            top = ok[: self.cfg.top_n]

            if len(top) > 0:
                self.progress.emit(f"[Info] Wrote {len(top)} report files to: {final_out_dir}")
                try:
                    pdf_path = write_final_summary_pdf(
                        out_dir=final_out_dir, results=results, top=top, thr=thr, basis=basis,
                        filename="Final_Summary.pdf", threshold_enabled=thr_enabled
                    )
                    self.finished.emit(f"[Info] Complete. Summary written to: {pdf_path}")
                except Exception as e:
                    self.finished.emit(f"[Info] Reports generated, but Summary PDF failed: {e}")
            else:
                self.finished.emit("[Info] Complete (No valid reports generated).")

        except Exception as e:
            self.finished.emit(f"[Info] Failed: {e}")
            traceback.print_exc()
        finally:
            if pool:
                try: pool.close()
                except: pass