# http_client.py
# HTTP/auth/session-pool helpers for IndyBiz PM Parts Generator
from __future__ import annotations

import os
import re
import logging
from contextlib import contextmanager
from queue import LifoQueue, Empty
from typing import Optional, List, Dict
from datetime import date
import datetime as _dt

import requests

# Logging (safe; excludes credentials)
LOG_DIR = os.path.join(os.path.expanduser("~"), ".indybiz_pm")
os.makedirs(LOG_DIR, exist_ok=True)
log = logging.getLogger("IndyBizPM.HTTP")

# HTTP constants
BASE_URL = "https://eservice.toshiba-solutions.com"
LOGIN_PAGE = f"{BASE_URL}/Account/LogOn"
LOGIN_POST = f"{BASE_URL}/Account/LogOn"
SERVICE_FILES = f"{BASE_URL}/Device/GetServiceFiles"
DEVICE_INDEX = f"{BASE_URL}/Device/Index"

HEADERS_COMMON = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                   "Gecko/20100101 Firefox/128.0"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": LOGIN_PAGE,
}

# --- Keyring-backed credentials (same behavior as before) ---
SERVICE_NAME = "IndyBiz_PM_Generator"
try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None


def get_saved_username() -> Optional[str]:
    if not keyring:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, "username")
    except Exception:
        return None


def get_saved_password() -> Optional[str]:
    if not keyring:
        return None
    try:
        u = get_saved_username()
        if not u:
            return None
        return keyring.get_password(SERVICE_NAME, u)
    except Exception:
        return None


def save_credentials(username: str, password: str) -> None:
    if not keyring:
        raise RuntimeError("Install 'keyring' with: pip install keyring")
    if not username or not password:
        raise ValueError("Username and Password cannot be empty.")
    keyring.set_password(SERVICE_NAME, "username", username)
    keyring.set_password(SERVICE_NAME, username, password)


def have_credentials() -> bool:
    return bool(get_saved_username() and get_saved_password())


# --- Auth / HTTP ---
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', re.I)


def _extract_anti_forgery(html: str) -> str:
    m = _TOKEN_RE.search(html)
    if not m:
        raise RuntimeError("Could not find __RequestVerificationToken on login page.")
    return m.group(1)


def login(sess: requests.Session) -> None:
    """
    Logs in the provided session using saved credentials.
    Raises on failure (same behavior as before).
    """
    username = get_saved_username()
    password = get_saved_password()
    if not (username and password):
        raise RuntimeError("No saved credentials. Use Settings → Credentials…")

    log.info("Fetching login page for token.")
    r = sess.get(LOGIN_PAGE, headers=HEADERS_COMMON, timeout=30)
    r.raise_for_status()
    token = _extract_anti_forgery(r.text)

    form = {
        "UserName": username,
        "Password": password,
        "OneTimePassword": "",
        "RememberMe2FA": "false",
        "timeZoneOffSet": "0",
        "returnUrl": "/Device/Index",
        "serial": "",
        "__RequestVerificationToken": token,
    }
    headers = {
        **HEADERS_COMMON,
        "Origin": BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    log.info("Submitting login POST (no credentials logged).")
    r = sess.post(LOGIN_POST, data=form, headers=headers, timeout=30)
    r.raise_for_status()

    if r.headers.get("Content-Type", "").lower().startswith("application/json"):
        js = r.json()
        if not js.get("page"):
            raise RuntimeError(f"Login returned JSON but no 'page': {js}")
    else:
        chk = sess.get(DEVICE_INDEX, headers=HEADERS_COMMON, timeout=30, allow_redirects=True)
        if "Log On" in chk.text or chk.status_code in (401, 403):
            raise RuntimeError("Login appears unsuccessful (got login page again).")
    log.info("Login successful.")


# --- Session Pool (thread-safe) ---
class SessionPool:
    """
    Thread-safe pool of logged-in requests.Session objects.
    Use: with pool.acquire() as sess: ...
    """
    def __init__(self, size: int):
        size = max(1, int(size))
        self._q: LifoQueue[requests.Session] = LifoQueue()
        for _ in range(size):
            s = requests.Session()
            login(s)
            self._q.put(s)
        self._size = size
        log.info(f"SessionPool initialized with {self._size} logged-in session(s).")

    @contextmanager
    def acquire(self):
        sess: Optional[requests.Session] = None
        try:
            sess = self._q.get(timeout=60)
            yield sess
        finally:
            if sess is not None:
                self._q.put(sess)

    def close(self) -> None:
        n = 0
        while True:
            try:
                s = self._q.get_nowait()
            except Empty:
                break
            try:
                s.close()
            except Exception:
                pass
            n += 1
        log.info(f"SessionPool closed {n} session(s).")


# --- Reusable HTTP helpers that accept an optional session ---
def get_service_file_bytes(serial: str, option: str = "PMSupport",
                           sess: Optional[requests.Session] = None) -> bytes:
    """
    Download service file bytes. If sess is provided, it is re-used; otherwise a
    temp session is created and closed (same behavior as before).
    """
    owns_session = False
    if sess is None:
        sess = requests.Session()
        login(sess)
        owns_session = True
    try:
        params = {"deviceSerial": serial, "option": option}
        headers = {**HEADERS_COMMON, "Referer": DEVICE_INDEX}
        log.info(f"Requesting service file: serial={serial}, option={option}")
        r = sess.get(SERVICE_FILES, params=params, headers=headers, timeout=60, stream=True)
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/html" in ctype:
            raise RuntimeError("Got HTML instead of file (login failed or invalid serial).")
        blob = b"".join(r.iter_content(chunk_size=8192))
        log.info(f"Received service file bytes: {len(blob)}")
        return blob
    finally:
        if owns_session and sess is not None:
            try:
                sess.close()
            except Exception:
                pass


def get_serials_after_login(sess: Optional[requests.Session] = None) -> List[str]:
    """
    Fetch /Device/Index using a logged-in session and parse serials.
    Accepts an optional session for reuse; otherwise logs in a temporary one.
    """
    # Local imports; keep light on module load
    from bs4 import BeautifulSoup  # type: ignore

    # Prefer package-relative import; fall back to top-level if someone runs loose files
    try:
        from pmgen.io import fetch_serials as fs  # package layout
    except Exception:
        import fetch_serials as fs                 # loose script layout

    owns_session = False
    if sess is None:
        sess = requests.Session()
        login(sess)
        owns_session = True
    try:
        r = sess.get(DEVICE_INDEX, headers=HEADERS_COMMON, timeout=30)
        r.raise_for_status()
        html = r.text
    finally:
        if owns_session and sess is not None:
            try:
                sess.close()
            except Exception:
                pass

    return fs.parse_serial_numbers(html)

def _add_months(d: date, months: int) -> date:
    """Safe month addition without dateutil."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # clamp day to end-of-month
    import calendar
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))

def _parse_unpacking_date_from_08_bytes(blob: bytes) -> Optional[date]:
    """
    Input: the bytes returned by /Device/GetServiceFiles?option=08
    The file is CSV-like text:
        CODE, SUB, DATA,
        ...
        3612, 0, 2507292085501,
    We only need the first 6 digits of DATA → YYMMDD (e.g., 25 07 29 = 2025-07-29).
    """
    try:
        txt = blob.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return None

    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    if not lines:
        return None

    # find any line that starts with "3612,"
    for ln in lines:
        # normalize commas, keep blanks
        parts = [p.strip() for p in ln.split(",")]
        if not parts:
            continue
        if parts[0] == "3612":
            # DATA is typically the 3rd column
            data_field = parts[2] if len(parts) > 2 else ""
            import re
            digits = re.sub(r"\D", "", data_field or "")
            if len(digits) < 6:
                continue
            y2 = int(digits[0:2], 10)
            mo = int(digits[2:4], 10)
            dy = int(digits[4:6], 10)
            # Assume 20xx (machines are modern)
            yy = 2000 + y2
            # basic validation
            try:
                return date(yy, mo, dy)
            except Exception:
                continue
    return None

def get_unpacking_date(serial: str, sess: Optional[requests.Session] = None) -> Optional[date]:
    """
    Fetch the 08 Setting Mode file for *serial* and return the unpacking date (CODE=3612)
    as a datetime.date, or None if not present/parseable.
    """
    try:
        blob = get_service_file_bytes(serial, option="08", sess=sess)
    except Exception:
        return None
    return _parse_unpacking_date_from_08_bytes(blob)