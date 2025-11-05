# pmgen/io/fetch_serials.py
from __future__ import annotations

from typing import List, Iterable
import re
import requests

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

# ─────────────────────────────────────────────────────────────
# Endpoint & headers (matches old_http_client.py)
# ─────────────────────────────────────────────────────────────
BASE_URL = "https://eservice.toshiba-solutions.com"
LOGIN_PAGE = f"{BASE_URL}/Account/LogOn"
DEVICE_INDEX = f"{BASE_URL}/Device/Index"

HEADERS_COMMON = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": LOGIN_PAGE,
}

# ─────────────────────────────────────────────────────────────
# Serial parsing (your existing code, kept intact)
# ─────────────────────────────────────────────────────────────
_SERIAL_RE = re.compile(r"\b[A-Z][A-Z0-9]{3}\d{5}\b", re.I)

def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out

def parse_serial_numbers(html: str) -> List[str]:
    """
    Extract device serials from the provided HTML string.

    Returns:
        A de-duplicated list of serials, preserving first-seen order.
    """
    if not isinstance(html, str) or not html:
        return []

    found: List[str] = []

    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # <div data-serial="CNAM66582">…</div>
            for el in soup.select("[data-serial]"):
                val = (el.get("data-serial") or "").strip()
                if val and _SERIAL_RE.fullmatch(val):
                    found.append(val)

            # hrefs with ?serial=XYZ or ?deviceSerial=XYZ
            for a in soup.find_all("a", href=True):
                href = a["href"]
                for key in ("serial", "deviceSerial"):
                    m = re.search(rf"(?:\?|&){key}=([^&#]+)", href)
                    if m:
                        cand = m.group(1).strip()
                        cand = re.sub(r"%2f|%2F|%20", "", cand)
                        if _SERIAL_RE.fullmatch(cand):
                            found.append(cand)
        except Exception:
            # fall back to regex sweep
            pass

    # Regex sweep for stragglers (JSON-inlined, plain text tables, etc.)
    for m in _SERIAL_RE.finditer(html):
        found.append(m.group(0))

    return _dedupe_preserve_order(found)

# ─────────────────────────────────────────────────────────────
# Public API used by http_client.SessionPool callers
# ─────────────────────────────────────────────────────────────
def get_active_serials(session: requests.Session) -> List[str]:
    """
    Fetch the Toshiba eService device index using a **logged-in** session and
    return all device serials found on that page.

    - Assumes `session` is already authenticated (login handled elsewhere).
    - Mirrors the exact request old_http_client.py used:
        GET https://eservice.toshiba-solutions.com/Device/Index
        with the same HEADERS_COMMON.
    """
    r = session.get(DEVICE_INDEX, headers=HEADERS_COMMON, timeout=30)
    r.raise_for_status()
    html = r.text
    # Parse serials from the HTML
    return parse_serial_numbers(html)
