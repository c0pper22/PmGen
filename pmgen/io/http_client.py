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
import weakref
from weakref import WeakSet
from pmgen.ui.main_window import SERVICE_NAME
from pmgen.io.fetch_serials import parse_serial_numbers

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
LOGOUT_URL = f"{BASE_URL}/Account/LogOff"

HEADERS_COMMON = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                   "Gecko/20100101 Firefox/128.0"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": LOGIN_PAGE,
}

# --- Keyring-backed credentials (same behavior as before) ---
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

def clear_credentials() -> None:
    """Delete the 'username' marker and its password under the unified service."""
    if not keyring:
        return
    try:
        u = keyring.get_password(SERVICE_NAME, "username")
    except Exception:
        u = None
    try:
        keyring.delete_password(SERVICE_NAME, "username")
    except Exception:
        pass
    if u:
        try:
            keyring.delete_password(SERVICE_NAME, u)
        except Exception:
            pass


# --- Login helpers (unchanged behavior) ---

def _extract_anti_forgery(html: str) -> str:
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("Could not find __RequestVerificationToken on login page.")
    return m.group(1)


def login(sess: requests.Session) -> None:
    """
    Logs in the provided session using saved credentials.
    Raises on failure.
    """
    username = get_saved_username()
    password = get_saved_password()
    
    if not (username and password):
        raise RuntimeError("No saved credentials. Use Settings -> Credentials...")

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
        try:
            js = r.json()
            
            page_value = js.get("page", "")
            if "Invalid User Name or Password" in page_value:
                raise RuntimeError("Login failed: Invalid User Name or Password.")
                        
        except ValueError:
            log.warning("Response Content-Type was JSON but could not parse body.")

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
    _all_pools: WeakSet = WeakSet()

    def __init__(self, size: int):
        size = max(1, int(size))
        self._q: LifoQueue[requests.Session] = LifoQueue()
        for _ in range(size):
            s = requests.Session()
            login(s)
            self._q.put(s)
        self._size = size
        # register this pool so we can close on logout
        try:
            SessionPool._all_pools.add(self)
        except Exception:
            pass
        log.info(f"SessionPool initialized with {self._size} logged-in session(s).")

    @contextmanager
    def acquire(self):
        sess = None
        try:
            sess = self._q.get(timeout=60)
            yield sess
        finally:
            if sess is not None:
                try:
                    self._q.put(sess)
                except Exception:
                    pass

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

    @classmethod
    def close_all_pools(cls) -> int:
        """Close all known pools; returns number of pools closed."""
        n = 0
        dead = []
        for p in list(cls._all_pools):
            try:
                p.close()
                n += 1
            except Exception:
                pass
            finally:
                dead.append(p)
        for p in dead:
            try:
                cls._all_pools.discard(p)
            except Exception:
                pass
        return n


# --- Reusable HTTP helpers that accept an optional session ---
def get_service_file_bytes(serial: str, option: str = "PMSupport",
                           sess: Optional[requests.Session] = None) -> bytes:
    """
    Download a service file for the given serial and option.
    If *sess* is None, a temp session is created and closed (same behavior as before).
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
            raise RuntimeError("Expected file bytes; got HTML (likely not logged in).")
        return r.content
    finally:
        if owns_session:
            try:
                sess.close()
            except Exception:
                pass


def get_serials_after_login(sess: requests.Session) -> List[str]:
    """
    Navigate to Device Index and parse active serials.
    Requires a logged-in session.
    """
    r = sess.get(DEVICE_INDEX, headers=HEADERS_COMMON, timeout=30, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    serials: List[str] = []
    serials = parse_serial_numbers(html)
    return serials


def _parse_unpacking_date_from_08_bytes(blob: bytes) -> Optional[date]:
    """
    Look for the 08 Setting Mode "Unpacking date" (code 3612).
    Handles packed numeric format like:
        3612, , 2507292085501,
    where first 6 digits are YYMMDD.
    """
    for raw in blob.decode(errors="ignore").splitlines():
        if "3612" not in raw:
            continue
        # find a long numeric token after 3612
        parts = re.split(r"[,\s]+", raw.strip())
        try:
            idx = parts.index("3612")
        except ValueError:
            continue

        # search forward for the first 6+ digit number
        for token in parts[idx + 1:]:
            if re.fullmatch(r"\d{6,}", token):
                try:
                    yy = int(token[0:2])
                    mm = int(token[2:4])
                    dd = int(token[4:6])
                    year = 2000 + yy  # assume 20xx
                    return date(year, mm, dd)
                except Exception:
                    break
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


# --- NEW: server-side logout helper (best effort) ---
def server_side_logout(sess: Optional[requests.Session] = None) -> None:
    """Best-effort: call portal logout endpoint with a session (or temp one)."""
    s = sess or requests.Session()
    try:
        s.get(LOGOUT_URL, headers=HEADERS_COMMON, timeout=10, allow_redirects=True)
    except Exception:
        pass