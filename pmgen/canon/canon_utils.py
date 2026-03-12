import sqlite3
import re
import os
from typing import Optional, Iterable, Set, Tuple, List
from pmgen.io.http_client import get_db_path
from pmgen.canon.regex_tokens import expand_regex_tokens

_MAPPINGS_CACHE: Optional[List[Tuple[str, str]]] = None

def reload_mappings_cache():
    """Forces a reload of the mappings from DB."""
    global _MAPPINGS_CACHE
    db_path = get_db_path()
    if not os.path.exists(db_path):
        _MAPPINGS_CACHE = []
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT pattern, template FROM canon_mappings ORDER BY pattern, id")
        mappings = cur.fetchall()
        conn.close()
        _MAPPINGS_CACHE = mappings
    except sqlite3.Error:
        _MAPPINGS_CACHE = []

def get_cached_mappings() -> List[Tuple[str, str]]:
    """Returns the cached mappings, loading them if necessary."""
    global _MAPPINGS_CACHE
    if _MAPPINGS_CACHE is None:
        reload_mappings_cache()
    return _MAPPINGS_CACHE or []

def canon_unit(raw: str) -> Optional[str]:
    s = re.sub(r"\s+", " ", raw.strip())
    s = s.replace("（", "(").replace("）", ")")

    mappings = get_cached_mappings()

    for pattern_str, template in mappings:
        try:
            expanded_pattern, unknown_tokens, _used_tokens = expand_regex_tokens(pattern_str)
            if unknown_tokens:
                continue
            pat = re.compile(expanded_pattern, re.I)
            m = pat.match(s)
            if m:
                return template.format(**m.groupdict())
        except (re.error, KeyError, ValueError):
            continue
            
    return None

def canonize_units(units: Iterable[str]) -> Tuple[Set[str], List[str]]:
    canon: Set[str] = set()
    unknown: List[str] = []
    for u in units:
        c = canon_unit(u)
        if c:
            canon.add(c)
        else:
            unknown.append(u)
    return canon, unknown