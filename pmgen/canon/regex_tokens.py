from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Tuple

BUILTIN_REGEX_TOKENS: Dict[str, str] = OrderedDict(
    [
        ("SPC", r"\s*"),
        ("SPC1", r"\s+"),
        ("LP", r"\(?"),
        ("RP", r"\)?"),
        ("COLOR", r"(?P<chan>K|C|M|Y)"),
        ("DF_TYPE", r"(?:DF|RADF|DSDF)"),
        ("SFB_BYPASS", r"(?:SFB|BYPASS)"),
    ]
)

_TOKEN_EXPR = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def expand_regex_tokens(pattern: str) -> Tuple[str, List[str], List[str]]:
    """Expands {TOKEN} placeholders in regex patterns.

    Returns (expanded_pattern, unknown_tokens, used_tokens).
    """
    unknown: List[str] = []
    used: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        value = BUILTIN_REGEX_TOKENS.get(token)
        if value is None:
            if token not in unknown:
                unknown.append(token)
            return match.group(0)
        if token not in used:
            used.append(token)
        return value

    expanded = _TOKEN_EXPR.sub(_replace, pattern or "")
    return expanded, unknown, used
