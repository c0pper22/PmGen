import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
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
                 unpack_filter_enabled: bool = False, unpack_extra_months: int = 0):
        super().__init__()
        self.cfg = cfg
        self.threshold = threshold
        self.life_basis = life_basis
        self.threshold_enabled = bool(threshold_enabled)
        self._blacklist = [p.upper() for p in (cfg.blacklist or [])]
        self._unpack_filter_enabled = bool(unpack_filter_enabled)
        self._unpack_extra_months = max(0, min(120, int(unpack_extra_months)))

    def _is_blacklisted(self, serial: str) -> bool:
        s = (serial or "").upper()
        for pat in (self._blacklist or []):
            if fnmatchcase(s, pat):
                return True
        return False

    def _prefilter_by_unpack_date(self, serials: list[str], pool) -> list[str]:
        if not self._unpack_filter_enabled:
            self.progress.emit("[Info] Unpack filter disabled.")
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
        base_months = int(self._unpack_extra_months)
        with pool.acquire() as sess:
            self.progress.emit(f"[Bulk] Applying unpacking date filter (+{self._unpack_extra_months} mo)…")
            for s in serials:
                try:
                    if _sig_uses_kw:
                        d = _get_unpack(s, sess=sess)
                    else:
                        d = _get_unpack(s, sess)
                except Exception:
                    kept.append(s)
                    continue

                if not d:
                    kept.append(s)
                    self.progress.emit(f"[Bulk] OK: {s} (no unpack date)")
                    continue

                cutoff = _add_months(d, base_months)
                today = date.today()
                if today > cutoff:
                    over = (today.year - cutoff.year) * 12 + (today.month - cutoff.month)
                    if today.day < cutoff.day:
                        over -= 1
                    over = max(0, over)
                    self.progress.emit(
                        f"[Bulk] Filtered: {s} unpacked {d:%Y-%m-%d} → cutoff {cutoff:%Y-%m-%d} (>{base_months} mo{f' +{over}' if over else ''})"
                    )
                else:
                    self.progress.emit(
                        f"[Bulk] OK: {s} unpacked {d:%Y-%m-%d} (cutoff {cutoff:%Y-%m-%d})"
                    )
                    kept.append(s)
        return kept

    def _fmt_pct(self, p):
        if p is None: return "—"
        try: return f"{(float(p) * 100):.1f}%"
        except Exception: return "—"

    def run(self):
        try:
            from pmgen.io.http_client import SessionPool, get_serials_after_login, get_service_file_bytes
            from pmgen.parsing.parse_pm_report import parse_pm_report
            from pmgen.engine.run_rules import run_rules
            from pmgen.engine.single_report import create_pdf_report
            from pmgen.engine.final_report import write_final_summary_pdf

            os.makedirs(self.cfg.out_dir, exist_ok=True)

            self.progress.emit("[Info] Creating session pool...")
            pool = SessionPool(self.cfg.pool_size)

            with pool.acquire() as sess:
                serials = get_serials_after_login(sess)
            self.progress.emit(f"[Info] Found {len(serials)} Active Serials.")

            serials0 = list(serials or [])
            serials1 = [s for s in serials0 if not self._is_blacklisted(s)]
            skipped = len(serials0) - len(serials1)
            if skipped:
                self.progress.emit(f"[Info] Skipped {skipped} serial(s) via blacklist.")
            if not serials1:
                raise RuntimeError("No serials to process after applying blacklist.")

            kept_serials = self._prefilter_by_unpack_date(serials1, pool)
            if not kept_serials:
                raise RuntimeError("All serials were filtered out by unpack-date/cutoff logic.")
            
            self.progress.emit(f"[Info] Filtered out {len(serials) - len(kept_serials)} Serials")
            self.progress.emit(f"[Info] Countinuing with {len(kept_serials)} Serials")

            thr = self.threshold
            basis = self.life_basis
            show_all = self.cfg.show_all
            thr_enabled = self.threshold_enabled

            def work(serial: str):
                try:
                    with pool.acquire() as sess:
                        blob = get_service_file_bytes(serial, "PMSupport", sess=sess)
                    report = parse_pm_report(blob)
                    selection = run_rules(report, threshold=thr, life_basis=basis, threshold_enabled=thr_enabled)

                    all_items = (getattr(selection, "meta", {}) or {}).get("all", []) or getattr(selection, "all_items", []) or []
                    best_used = max([getattr(f, "life_used", 0.0) or 0.0 for f in all_items], default=0.0)

                    create_pdf_report(
                        report=report,
                        selection=selection,
                        threshold=thr,
                        life_basis=basis,
                        show_all=show_all,
                        out_dir=self.cfg.out_dir,
                        threshold_enabled=thr_enabled
                    )

                    meta = getattr(selection, "meta", {}) or {}
                    return {
                        "serial": (report.headers or {}).get("serial") or serial,
                        "model": (report.headers or {}).get("model")  or "Unknown",
                        "best_used": float(best_used),
                        "text": "None",
                        "grouped": meta.get("selection_pn_grouped", {}) or {},
                        "flat": meta.get("selection_pn", {}) or {},
                        "kit_by_pn": meta.get("kit_by_pn", {}) or {},
                        "due_sources": meta.get("due_sources", {}) or {},
                    }
                except Exception as e:
                    import traceback
                    return {"serial": serial, "error": str(e), "trace": traceback.format_exc()}

            results = []
            from concurrent.futures import ThreadPoolExecutor, as_completed
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
                        self.progress.emit(f"[Bulk] {s}: ERROR — {e}")

            ok = [r for r in results if "error" not in r]
            ok.sort(key=lambda r: (r.get("best_used") or 0.0), reverse=True)
            top = ok[: self.cfg.top_n]

            self.progress.emit(f"[Info] Wrote {len(top)} report files to: {self.cfg.out_dir}")

            pdf_path = write_final_summary_pdf(
                out_dir=self.cfg.out_dir,
                results=results,
                top=top,
                thr=thr,
                basis=basis,
                filename="Final_Summary.pdf",
                threshold_enabled=thr_enabled
            )

            pool.close()
            self.finished.emit(f"[Info] Complete. Summary written to: {pdf_path}")
        except Exception as e:
            self.finished.emit(f"[Info] Failed: {e}")