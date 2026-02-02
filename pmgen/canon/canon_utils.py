import sqlite3
import re
import os
from typing import Dict, Optional, Iterable, Set, Tuple, List, Pattern
import types
from pmgen.io.http_client import get_db_path

SPC   = r"\s*"
LP    = r"\(?"
RP    = r"\)?"
COLOR = r"(?P<chan>K|C|M|Y)"

CANON = types.SimpleNamespace(
    # Color parts (order doesn’t matter; names used for dynamic lookup)
    Y_DRUM = "DRUM[Y]",
    M_DRUM = "DRUM[M]",
    C_DRUM = "DRUM[C]",
    K_DRUM = "DRUM[K]",

    Y_DRUM_BLADE = "DRUM BLADE[Y]",
    M_DRUM_BLADE = "DRUM BLADE[M]",
    C_DRUM_BLADE = "DRUM BLADE[C]",
    K_DRUM_BLADE = "DRUM BLADE[K]",

    Y_CHARGER_NEEDLE = "MAIN CHARGER NEEDLE[Y]",
    M_CHARGER_NEEDLE = "MAIN CHARGER NEEDLE[M]",
    C_CHARGER_NEEDLE = "MAIN CHARGER NEEDLE[C]",
    K_CHARGER_NEEDLE = "MAIN CHARGER NEEDLE[K]",

    Y_GRID = "GRID[Y]",
    M_GRID = "GRID[M]",
    C_GRID = "GRID[C]",
    K_GRID = "GRID[K]",

    Y_CLEANING_PAD = "CHARGER CLEANING PAD[Y]",
    M_CLEANING_PAD = "CHARGER CLEANING PAD[M]",
    C_CLEANING_PAD = "CHARGER CLEANING PAD[C]",
    K_CLEANING_PAD = "CHARGER CLEANING PAD[K]",

    Y_DEVELOPER = "DEVELOPER[Y]",
    M_DEVELOPER = "DEVELOPER[M]",
    C_DEVELOPER = "DEVELOPER[C]",
    K_DEVELOPER = "DEVELOPER[K]",

    # Generic parts (mono / non-color-specific)
    BELT_BLADE = "BELT BLADE",
    FUSER_BELT = "FUSER BELT",
    PRESS_ROLLER = "PRESS ROLLER",
    PRESS_ROLLER_FINGER = "PRESS ROLLER FINGER",
    FUSER_PAD = "FUSER PAD",
    OIL_SLIDE_SHEET = "OIL/SLIDE SHEET",
    OZONE_FILTER = "OZONE FILTER",
    TONER_FILTER = "TONER FILTER",
    TRANSFER_ROLLER = "TRANSFER ROLLER",

    # Mono (A-line) expand-to-K channel
    MONO_DRUM = "DRUM[K]",
    MONO_DRUM_BLADE = "DRUM BLADE[K]",
    MONO_DEVELOPER = "DEVELOPER[K]",
    MONO_GRID = "GRID[K]",
    MONO_CHARGER_NEEDLE = "MAIN CHARGER NEEDLE[K]",

    # Fuser / transfer / misc
    FUSER_ROLLER = "FUSER ROLLER",
    SEPARATION_FINGER_DRUM  = "SEPARATION FINGER (DRUM)",
    SEPARATION_FINGER_FUSER = "SEPARATION FINGER (FUSER)",
    OZONE_FILTER_1 = "OZONE FILTER 1",
    OZONE_FILTER_2 = "OZONE FILTER 2",
    VOC_FILTER = "VOC FILTER",
    TRANSFER_BELT = "TRANSFER BELT",
    HEAT_ROLLER = "HEAT ROLLER",

    # DF generic
    DF_FEED_ROLLER = "DF FEED ROLLER",
    DF_PICK_UP_ROLLER = "DF PICK UP ROLLER",
    DF_SEP_ROLLER = "DF SEP ROLLER",

    # Cassette/bypass/LCF positions — keep punctuation/spaces exactly
    FEED_1ST_CST = "FEED ROLLER (1st CST.)",
    FEED_2ND_CST = "FEED ROLLER (2nd CST.)",
    FEED_3RD_CST = "FEED ROLLER (3rd CST.)",
    FEED_4TH_CST = "FEED ROLLER (4th CST.)",
    FEED_SFB = "FEED ROLLER (SFB/BYPASS)",
    FEED_LCF = "FEED ROLLER (LCF)",
    FEED_OLCF = "FEED ROLLER (O-LCF)",
    FEED_O2LCF = "FEED ROLLER (O2-LCF)",
    FEED_TLCF = "FEED ROLLER (T-LCF)",

    PICK_1ST_CST = "PICK UP ROLLER (1st CST.)",
    PICK_2ND_CST = "PICK UP ROLLER (2nd CST.)",
    PICK_3RD_CST = "PICK UP ROLLER (3rd CST.)",
    PICK_4TH_CST = "PICK UP ROLLER (4th CST.)",
    PICK_SFB = "PICK UP ROLLER/PAD (SFB/BYPASS)",
    PICK_LCF = "PICK UP ROLLER (LCF)",
    PICK_OLCF = "PICK UP ROLLER (O-LCF)",
    PICK_O2LCF = "PICK UP ROLLER (O2-LCF)",
    PICK_TLCF = "PICK UP ROLLER (T-LCF)",

    SEP_1ST_CST = "SEP ROLLER/PAD (1st CST.)",
    SEP_2ND_CST = "SEP ROLLER/PAD (2nd CST.)",
    SEP_3RD_CST = "SEP ROLLER/PAD (3rd CST.)",
    SEP_4TH_CST = "SEP ROLLER/PAD (4th CST.)",
    SEP_SFB = "SEP ROLLER/PAD (SFB/BYPASS)",
    SEP_LCF = "SEP ROLLER/PAD (LCF)",
    SEP_OLCF = "SEP ROLLER/PAD (O-LCF)",
    SEP_O2LCF = "SEP ROLLER/PAD (O2-LCF)",
    SEP_TLCF = "SEP ROLLER/PAD (T-LCF)",

    PICK_FEED_DSDF_COMBO = "PICK UP ROLLER/FEED ROLLER(DSDF)",
)

CANON_MAP: Dict[Pattern[str], str] = {
    # ─── Color channels ─────────────────────────────────────────────
    re.compile(rf"^DRUM{SPC}{LP}{COLOR}{RP}$", re.I):                "DRUM[{chan}]",
    re.compile(rf"^DRUM{SPC}BLADE{SPC}{LP}{COLOR}{RP}$", re.I):      "DRUM BLADE[{chan}]",
    re.compile(rf"^(?:MAIN{SPC})?CHARGER{SPC}NEEDLE{SPC}{LP}{COLOR}{RP}$", re.I): "MAIN CHARGER NEEDLE[{chan}]",
    re.compile(rf"^GRID{SPC}{LP}{COLOR}{RP}$", re.I):                "GRID[{chan}]",
    re.compile(rf"^CHARGER{SPC}CLEANING{SPC}PAD{SPC}{LP}{COLOR}{RP}$", re.I): "CHARGER CLEANING PAD[{chan}]",
    re.compile(r"^BLACK\s+DEVELOPER$", re.I):                        CANON.K_DEVELOPER,
    re.compile(r"^CYAN\s+DEVELOPER$", re.I):                         CANON.C_DEVELOPER,
    re.compile(r"^MAGENTA\s+DEVELOPER$", re.I):                      CANON.M_DEVELOPER,
    re.compile(r"^YELLOW\s+DEVELOPER$", re.I):                       CANON.Y_DEVELOPER,

    # ─── Generic parts ─────────────────────────────────────────────
    re.compile(r"^(BELT|RECOVERY)\s+BLADE$", re.I):                  CANON.BELT_BLADE,
    re.compile(r"^FUSER\s+BELT$", re.I):                             CANON.FUSER_BELT,
    re.compile(r"^PRESS\s+ROLLER$", re.I):                           CANON.PRESS_ROLLER,
    re.compile(r"^PRESS\s+ROLLER\s+FINGER$", re.I):                  CANON.PRESS_ROLLER_FINGER,
    re.compile(r"^FUSER\s+PAD$", re.I):                              CANON.FUSER_PAD,
    re.compile(r"^(?:OIL\s+RECOVERY|SLIDE)\s+SHEET$", re.I):         CANON.OIL_SLIDE_SHEET,
    re.compile(r"^OZONE\s+FILTER(?:\s*\(?REAR\)?)?$", re.I):         CANON.OZONE_FILTER,
    re.compile(r"^TONER\s+FILTER$", re.I):                           CANON.TONER_FILTER,
    re.compile(r"^(?:2(?:ND)?\s*)?TRANSFER\s+ROLLER$", re.I):        CANON.TRANSFER_ROLLER,

    # ─── Document Feeder types ──────────────────────────────────────
    re.compile(r"^FEED\s+ROLLER\s*\((?:DF|RADF|DSDF)\)$", re.I):     CANON.DF_FEED_ROLLER,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\((?:DF|RADF|DSDF)\)$", re.I):CANON.DF_PICK_UP_ROLLER,
    re.compile(r"^SEP(?:ARATION)?\s+ROLLER\s*\((?:DF|RADF|DSDF)\)$", re.I): CANON.DF_SEP_ROLLER,

    # ─── Individual cassette / bypass / LCF feed types ──────────────
    re.compile(r"^FEED\s+ROLLER\s*\(1st\s*CST\.?\)$", re.I):         CANON.FEED_1ST_CST,
    re.compile(r"^FEED\s+ROLLER\s*\(2nd\s*CST\.?\)$", re.I):         CANON.FEED_2ND_CST,
    re.compile(r"^FEED\s+ROLLER\s*\(3rd\s*CST\.?\)$", re.I):         CANON.FEED_3RD_CST,
    re.compile(r"^FEED\s+ROLLER\s*\(4th\s*CST\.?\)$", re.I):         CANON.FEED_4TH_CST,
    re.compile(r"^FEED\s+ROLLER\s*\((?:SFB|BYPASS)\)$", re.I):       CANON.FEED_SFB,
    re.compile(r"^FEED\s+ROLLER\s*\(LCF\)$", re.I):                  CANON.FEED_LCF,
    re.compile(r"^FEED\s+ROLLER\s*\(O-?LCF\)$", re.I):               CANON.FEED_OLCF,
    re.compile(r"^FEED\s+ROLLER\s*\(O2-?LCF\)$", re.I):              CANON.FEED_O2LCF,
    re.compile(r"^FEED\s+ROLLER\s*\(T-?LCF\)$", re.I):               CANON.FEED_TLCF,

    # ─── Same expansion for PICK UP and SEP rollers ─────────────────
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(1st\s*CST\.?\)$", re.I):    CANON.PICK_1ST_CST,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(2nd\s*CST\.?\)$", re.I):    CANON.PICK_2ND_CST,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(3rd\s*CST\.?\)$", re.I):    CANON.PICK_3RD_CST,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(4th\s*CST\.?\)$", re.I):    CANON.PICK_4TH_CST,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\((?:SFB|BYPASS)\)$", re.I):  CANON.PICK_SFB,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(LCF\)$", re.I):             CANON.PICK_LCF,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(O-?LCF\)$", re.I):          CANON.PICK_OLCF,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(O2-?LCF\)$", re.I):         CANON.PICK_O2LCF,
    re.compile(r"^PICK\s+UP\s+ROLLER\s*\(T-?LCF\)$", re.I):          CANON.PICK_TLCF,

    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(1st\s*CST\.?\)$", re.I): CANON.SEP_1ST_CST,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(2nd\s*CST\.?\)$", re.I): CANON.SEP_2ND_CST,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(3rd\s*CST\.?\)$", re.I): CANON.SEP_3RD_CST,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(4th\s*CST\.?\)$", re.I): CANON.SEP_4TH_CST,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\((?:SFB|BYPASS)\)$", re.I): CANON.SEP_SFB,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(LCF\)$", re.I):          CANON.SEP_LCF,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(O-?LCF\)$", re.I):       CANON.SEP_OLCF,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(O2-?LCF\)$", re.I):      CANON.SEP_O2LCF,
    re.compile(r"^SEP(?:ARATION)?\s+(?:ROLLER|PAD)\s*\(T-?LCF\)$", re.I):       CANON.SEP_TLCF,

    re.compile(r"^PICK\s+UP\s+ROLLER\s*/\s*FEED\s+ROLLER\s*\(DSDF\)$", re.I):   CANON.PICK_FEED_DSDF_COMBO,

    # ─── Mono families (A-line) use K channel ───────────────────────
    re.compile(r"^DRUM$", re.I):                                     CANON.K_DRUM,
    re.compile(r"^DRUM\s+BLADE$", re.I):                             CANON.K_DRUM_BLADE,
    re.compile(r"^DEVELOPER$", re.I):                                CANON.K_DEVELOPER,
    re.compile(r"^GRID$", re.I):                                     CANON.K_GRID,
    re.compile(r"^(?:NEEDLE\s+ELECTRODE|MAIN\s+CHARGER\s+NEEDLE)$", re.I): CANON.K_CHARGER_NEEDLE,

    # ─── Misc mono + fuser/transfer parts ───────────────────────────
    re.compile(r"^FUSER\s+ROLLER$", re.I):                           CANON.FUSER_ROLLER,
    re.compile(r"^SEPARATION\s+FINGER\(DRUM\)$", re.I):              CANON.SEPARATION_FINGER_DRUM,
    re.compile(r"^SEPARATION\s+FINGER\(FUSER\)$", re.I):             CANON.SEPARATION_FINGER_FUSER,

    # ─── Misc filters and sheets ────────────────────────────────────
    re.compile(r"^OZONE\s+FILTER\s*1$", re.I):                       CANON.OZONE_FILTER_1,
    re.compile(r"^OZONE\s+FILTER\s*2$", re.I):                       CANON.OZONE_FILTER_2,
    re.compile(r"^VOC\s+FILTER$", re.I):                             CANON.VOC_FILTER,
    re.compile(r"^TRANSFER\s+BELT$", re.I):                          CANON.TRANSFER_BELT,
    re.compile(r"^HEAT\s+ROLLER$", re.I):                            CANON.HEAT_ROLLER,
}

def canon_unit(raw: str) -> Optional[str]:
    s = re.sub(r"\s+", " ", raw.strip())
    s = s.replace("（", "(").replace("）", ")")

    db_path = get_db_path()
    if not os.path.exists(db_path):
        # Fallback or log error so the app doesn't crash
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT pattern, template FROM canon_mappings")
        mappings = cur.fetchall()
        conn.close()

        for pattern_str, template in mappings:
            pat = re.compile(pattern_str, re.I)
            m = pat.match(s)
            if m:
                return template.format(**m.groupdict())
    except sqlite3.Error:
        return None
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


if __name__ == "__main__":
    # demo only

    #this is the unique list of possible PM items specifically for Indybiz on (10/28/2025)
    units = [
        "1st TRANSFER ROLLER(C)",
        "1st TRANSFER ROLLER(K)",
        "1st TRANSFER ROLLER(M)",
        "1st TRANSFER ROLLER(Y)",
        "2nd TRANSFER ROLLER",
        "BELT BLADE",
        "BLACK DEVELOPER",
        "BRAKE PAD(DSDF)",
        "CHARGER CLEANING PAD (C)",
        "CHARGER CLEANING PAD (K)",
        "CHARGER CLEANING PAD (M)",
        "CHARGER CLEANING PAD (Y)",
        "CHARGER CLEANING PAD(C)",
        "CHARGER CLEANING PAD(K)",
        "CHARGER CLEANING PAD(M)",
        "CHARGER CLEANING PAD(Y)",
        "CLEANING PAD",
        "CYAN DEVELOPER",
        "DEVELOPER",
        "DRUM",
        "DRUM (C)",
        "DRUM (K)",
        "DRUM (M)",
        "DRUM (Y)",
        "DRUM BLADE",
        "DRUM BLADE (C)",
        "DRUM BLADE (K)",
        "DRUM BLADE (M)",
        "DRUM BLADE (Y)",
        "DRUM BLADE(C)",
        "DRUM BLADE(K)",
        "DRUM BLADE(M)",
        "DRUM BLADE(Y)",
        "DRUM GAP SPACER (C)",
        "DRUM GAP SPACER (K)",
        "DRUM GAP SPACER (M)",
        "DRUM GAP SPACER (Y)",
        "DRUM(C)",
        "DRUM(K)",
        "DRUM(M)",
        "DRUM(Y)",
        "FEED ROLLER (O-LCF)",
        "FEED ROLLER(1st CST.)",
        "FEED ROLLER(2nd CST.)",
        "FEED ROLLER(3rd CST.)",
        "FEED ROLLER(4th CST.)",
        "FEED ROLLER(BYPASS)",
        "FEED ROLLER(DF)",
        "FEED ROLLER(DSDF)",
        "FEED ROLLER(LCF)",
        "FEED ROLLER(O-LCF)",
        "FEED ROLLER(O2-LCF)",
        "FEED ROLLER(RADF)",
        "FEED ROLLER(SFB)",
        "FEED ROLLER(T-LCF)",
        "FUSER BELT",
        "FUSER PAD",
        "FUSER ROLLER",
        "GRID",
        "GRID (C)",
        "GRID (K)",
        "GRID (M)",
        "GRID (Y)",
        "GRID(C)",
        "GRID(K)",
        "GRID(M)",
        "GRID(Y)",
        "HEAT ROLLER",
        "LED GAP SPACER (C)",
        "LED GAP SPACER (K)",
        "LED GAP SPACER (M)",
        "LED GAP SPACER (Y)",
        "MAGENTA DEVELOPER",
        "MAIN CHARGER NEEDLE (C)",
        "MAIN CHARGER NEEDLE (K)",
        "MAIN CHARGER NEEDLE (M)",
        "MAIN CHARGER NEEDLE (Y)",
        "MAIN CHARGER NEEDLE(C)",
        "MAIN CHARGER NEEDLE(K)",
        "MAIN CHARGER NEEDLE(M)",
        "MAIN CHARGER NEEDLE(Y)",
        "NEEDLE ELECTRODE",
        "OIL RECOVERY  SHEET",
        "OZONE FILTER",
        "OZONE FILTER (REAR)",
        "OZONE FILTER 1",
        "OZONE FILTER 2",
        "OZONE FILTER(REAR)",
        "PICK UP ROLLER (1st CST.)",
        "PICK UP ROLLER (O-LCF)",
        "PICK UP ROLLER(1st CST.)",
        "PICK UP ROLLER(2nd CST.)",
        "PICK UP ROLLER(3rd CST.)",
        "PICK UP ROLLER(4th CST.)",
        "PICK UP ROLLER(BYPASS)",
        "PICK UP ROLLER(DF)",
        "PICK UP ROLLER(DSDF)",
        "PICK UP ROLLER(LCF)",
        "PICK UP ROLLER(O-LCF)",
        "PICK UP ROLLER(O2-LCF)",
        "PICK UP ROLLER(RADF)",
        "PICK UP ROLLER(SFB)",
        "PICK UP ROLLER(T-LCF)",
        "PICK UP ROLLER/FEED ROLLER(DSDF)",
        "PRESS ROLLER",
        "PRESS ROLLER FINGER",
        "RECOVERY BLADE",
        "SEP PAD(1st CST.)",
        "SEP PAD(SFB)",
        "SEP ROLLER (1st CST.)",
        "SEP ROLLER (O-LCF)",
        "SEP ROLLER(1st CST.)",
        "SEP ROLLER(2nd CST.)",
        "SEP ROLLER(3rd CST.)",
        "SEP ROLLER(4th CST.)",
        "SEP ROLLER(BYPASS)",
        "SEP ROLLER(DF)",
        "SEP ROLLER(DSDF)",
        "SEP ROLLER(LCF)",
        "SEP ROLLER(O-LCF)",
        "SEP ROLLER(O2-LCF)",
        "SEP ROLLER(RADF)",
        "SEP ROLLER(SFB)",
        "SEP ROLLER(T-LCF)",
        "SEPARATION FINGER(DRUM)",
        "SEPARATION FINGER(FUSER)",
        "SLIDE SHEET",
        "TBU DRIVER ROLLER",
        "TONER FILTER",
        "TRANSFER BELT",
        "TRANSFER ROLLER",
        "VOC FILTER",
        "YELLOW DEVELOPER",
    ]

    for s0 in units:
        print(f"{s0:28s} -> {canon_unit(s0)}")
