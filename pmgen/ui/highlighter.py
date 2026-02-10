import re
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont

class OutputHighlighter(QSyntaxHighlighter):
    def __init__(self, parent_doc):
        super().__init__(parent_doc)
        self._build_formats()

    def _mkfmt(self, fg=None, bold=False, italic=False):
        fmt = QTextCharFormat()
        if fg is not None:
            fmt.setForeground(QColor(fg))
        if bold:
            fmt.setFontWeight(QFont.Weight.DemiBold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_formats(self):
        self.fmt_normal     = self._mkfmt("#ffffff", bold=True)
        self.fmt_header     = self._mkfmt("#7aa2f7", bold=True)
        self.fmt_rule       = self._mkfmt("#444444")
        self.fmt_muted      = self._mkfmt("#888888", italic=True)
        self.fmt_kit_row    = self._mkfmt("#a6da95")
        self.fmt_due_bullet = self._mkfmt("#f7768e", bold=True)
        self.fmt_percentage = self._mkfmt("#f77600", bold=True)
        self.fmt_label      = self._mkfmt("#c0caf5", bold=True)

        self.fmt_due_row_base = self._mkfmt("#bbbbbb")
        self.fmt_due_canon    = self._mkfmt("#1c94d5", bold=True)
        self.fmt_due_pct      = self._mkfmt("#e0af68", bold=True)
        self.fmt_due_flag     = self._mkfmt("#f7768e", bold=True)

        self.fmt_header_line_base = self._mkfmt("#bfbfbf")
        self.fmt_model_value      = self._mkfmt("#a6da95", bold=True)
        self.fmt_serial_value     = self._mkfmt("#7dcfff", bold=True)
        self.fmt_date_value       = self._mkfmt("#e0af68")

        self.fmt_badge_line_base  = self._mkfmt("#bfbfbf")
        self.fmt_thresh_value     = self._mkfmt("#e0af68", bold=True)
        self.fmt_basis_badge      = self._mkfmt("#e0af68", bold=True)

        self.fmt_counters_base    = self._mkfmt("#bfbfbf")
        self.fmt_kv_label         = self._mkfmt("#1c94d5", bold=True)
        self.fmt_kv_value         = self._mkfmt("#e0af68", bold=True)
        
        self.fmt_bulk             = self._mkfmt("#97eb80ff", bold=True)
        self.fmt_info             = self._mkfmt("#D8B30C", bold=True)

        self.fmt_pct_low          = self._mkfmt("#40ed68", bold=True)
        self.fmt_pct_mid          = self._mkfmt("#f79346", bold=True)
        self.fmt_pct_high         = self._mkfmt("#d83d37", bold=True)

        self.fmt_bulk_serial      = self._mkfmt("#81A1C1", bold=True)
        self.fmt_bulk_ok          = self._mkfmt("#40ed68", bold=True)
        self.fmt_bulk_filtered    = self._mkfmt("#d83d37", bold=True)

    def highlightBlock(self, text: str):
        # --- CHANGE: Apply the default White/Bold to the whole line first ---
        # Any specific matches below will overwrite this, but "gaps" will remain White/Bold.
        self.setFormat(0, len(text), self.fmt_normal)

        t = text.strip()

        # --- CHANGE 1: Only highlight the [Auto-Login] tag ---
        if "[Auto-Login]" in t:
            # This overwrites the bold white with the muted style
            self.setFormat(0, len(text), self.fmt_muted)
            return
        
        if "[Info]" in t:
            self.setFormat(0, len(text), self.fmt_info) 
            
        # --- CHANGE 3: Only highlight the [Bulk] tag ---
        tag_bulk = "[Bulk]"
        if tag_bulk in t:
            # 1. Color just the [Bulk] tag
            start_index = text.find(tag_bulk)
            if start_index >= 0:
                self.setFormat(start_index, len(tag_bulk), self.fmt_bulk)

            # 2. Handle the specific regex coloring inside the line (Percentages)
            pct_re = re.compile(r"(?P<num>\d+(?:\.\d+)?)%")
            for m in pct_re.finditer(t):
                val_str = m.group("num")
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                if val < 84.0:
                    fmt = self.fmt_pct_low
                elif val < 100.0:
                    fmt = self.fmt_pct_mid
                else:
                    fmt = self.fmt_pct_high
                self.setFormat(m.start(), m.end() - m.start(), fmt)

            # 3. Handle OK
            ok_re = re.compile(r"\bOK\b", re.IGNORECASE)
            for m in ok_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_ok)

            # 4. Handle FILTERED
            filtered_re = re.compile(r"\bFILTERED\b", re.IGNORECASE)
            for m in filtered_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_filtered)

            # 5. Handle Serial Numbers
            serial_re = re.compile(r"\b[A-Z0-9]{5,10}\b")
            for m in serial_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_serial)
            return

        # --- The rest of the logic remains unchanged ---

        if t in ("Final Parts", "Most-Due Items", "Counters", "End of Report"):
            self.setFormat(0, len(text), self.fmt_header)
            return

        if set(t) in ({"─"}, {"-"}, {"="}):
            self.setFormat(0, len(text), self.fmt_rule)
            return

        if t.startswith("(") and any(tok in t.lower() for tok in ("qty", "catalog", "part number", "×", " x ")):
            self.setFormat(0, len(text), self.fmt_muted)
            return

        if "→" in t and not t.startswith("Report Date"):
            kit_new_after = re.compile(r"^\s*(?P<qty>\d+)\s*[x×]\s*→\s*(?P<pn>\S+)\s*→\s*(?P<kit>\S.*?)\s*$", re.IGNORECASE)
            kit_new_before = re.compile(r"^\s*x\s*(?P<qty>\d+)\s*→\s*(?P<pn>\S+)\s*→\s*(?P<kit>\S.*?)\s*$", re.IGNORECASE)
            kit_old = re.compile(r"^\s*(?P<kit>\S.*?)\s*→\s*(?P<pn>\S+)\s*[×x]\s*(?P<qty>\d+)\s*$", re.IGNORECASE)

            if kit_new_after.match(t) or kit_new_before.match(t) or kit_old.match(t):
                self.setFormat(0, len(text), self.fmt_kit_row)
                return

        if t.startswith("• ") or "→ DUE" in t:
            m = re.match(r"^\s*•\s+(?P<canon>.+?)\s+—\s+(?P<pct>\S+)(?:\s*→\s*(?P<due>DUE))?\s*$", t)
            if m:
                # IMPORTANT: Overwrite the base white with the grey base for this row type
                self.setFormat(0, len(text), self.fmt_due_row_base) 
                
                left_ws = len(text) - len(text.lstrip())
                def _apply(name, fmt):
                    if name in m.groupdict() and m.group(name):
                        s, e = m.start(name), m.end(name)
                        self.setFormat(left_ws + s, e - s, fmt)
                _apply("canon", self.fmt_due_canon)
                _apply("pct",   self.fmt_due_pct)
                if m.group("due"):
                    _apply("due", self.fmt_due_flag)
                return
            else:
                self.setFormat(0, len(text), self.fmt_due_bullet)
                return

        if t.startswith("Model:") and "Serial:" in t and "Date:" in t:
            self.setFormat(0, len(text), self.fmt_header_line_base)
            m = re.search(r"Model:\s*(?P<model>.+?)\s*\|\s*Serial:\s*(?P<serial>\S+)\s*\|\s*Date:\s*(?P<date>.+)$", text)
            if m:
                self.setFormat(*m.span("model"), self.fmt_model_value)
                self.setFormat(*m.span("serial"), self.fmt_serial_value)
                self.setFormat(*m.span("date"), self.fmt_date_value)
            return

        if t.startswith("Basis:") or t.startswith("Report Date:"):
            self.setFormat(0, len(text), self.fmt_label)
            return

        if t.lower().startswith("due threshold:") and "basis:" in t.lower():
            self.setFormat(0, len(text), self.fmt_badge_line_base)
            m = re.search(r"(?i)due\s*threshold:\s*(?P<thresh>[0-9.]+%?)\s*•\s*basis:\s*(?P<basis>\S+)", text)
            if m:
                self.setFormat(*m.span("thresh"), self.fmt_thresh_value)
                self.setFormat(*m.span("basis"),  self.fmt_basis_badge)
            return

        if t.lower().startswith("color:") or (" black:" in t.lower() and " total:" in t.lower()):
            self.setFormat(0, len(text), self.fmt_counters_base)
            for m in re.finditer(r"([A-Za-z]+):\s*([0-9,]+)", text):
                self.setFormat(*m.span(1), self.fmt_kv_label)
                self.setFormat(*m.span(2), self.fmt_kv_value)
            return