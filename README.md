# 🧭 PmGen — Toshiba e-STUDIO Preventive Maintenance Generator

**PmGen** is a cross-platform Python 3.13 application that automates the generation of preventive-maintenance (PM) parts lists for Toshiba e-STUDIO MFP devices.  
It fetches, parses, and analyzes official **PM Support Code List** reports from Toshiba e-Service, applies smart rule-based logic to determine _due_ items, and outputs structured “Most-Due Items” and “Final Parts” reports with part-number resolution via the local **Ribon.accdb** database.

Built with **PyQt 6**, **threaded HTTP sessions**, and a **modular rule engine**, PmGen can operate interactively or in unattended “bulk” mode across an entire fleet.

---

## ✨ Features

| Category                 | Highlights                                                                                                                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Data Parsing & Rules** | Parses official PM Support Code List text/CSV exports.<br>Applies chained rules: `GenericLifeRule`, `KitLinkRule`, `QtyOverrideRule`.<br>Supports per-color and aggregate counting (via `ColorScope`). |
| **Part Resolution**      | Uses Microsoft Access database (`Ribon.accdb`) to expand catalog kit codes to actual part numbers (`PARTS_NO`).<br>Selects units by latest creation dates.                                             |
| **Authentication**       | Secure login using `keyring` (stores password in OS credential vault).<br>Optional “Stay Logged In” and automatic startup login.                                                                       |
| **Bulk Runner**          | Multi-threaded fleet processing with configurable thread pool, Top N filtering, blacklist, and “unpack-date” filter.<br>Writes one text report per serial + consolidated summary.                      |
| **Customization**        | Adjustable due-threshold (0.01–2.00 × life).<br>Switchable life-basis (page / drive).<br>“Show All Items” toggle to include sub-threshold parts.                                                       |
| **Extensible**           | Modular: catalog registry, canon maps, rules system, HTTP layer, UI separated.                                                                                                                         |

---

## 🧱 Architecture Overview

```

pmgen/
├── ui/
│   ├── app.py              # Entry-point bootstrapper (GUI)
│   └── main_window.py      # PyQt MainWindow + dialogs + BulkRunner
├── engine/
│   ├── run_rules.py        # Orchestrates rule chain execution
│   ├── single_report.py    # Parse → Rule → Format pipeline
│   └── resolve_to_pn.py    # Kit → Part Number resolver
├── canon/
│   └── canon_utils.py      # Canon Mappings
├── rules/
│   ├── base.py             # RuleBase & Context classes
│   ├── kit_link.py         # Canon → Kit resolution
│   ├── qty_override.py     # Manual quantity overrides
│   └── generic_life.py     # Core life % rule
├── catalog/
│   └── part_kit_catalog.py # Full model registry & kits
├── io/
│   ├── http_client.py      # SessionPool + e-Service fetching
│   ├── ribon_db.py         # Access DB queries
│   └── fetch_serials.py    # Index retrieval
├── parsing/
│   └── parse_pm_report.py  # Text parser → PmReport
└── types.py                # Dataclasses (PmReport, PmItem, Finding, Selection)

```

**Flow diagram**

```

┌────────────────────────────────────────────┐
│            PM_Report (.txt / .csv)         │
└────────────────────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │  parse_pm_report            │
        │  → produces PmReport        │
        └─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                        PmReport                              │
│--------------------------------------------------------------│
│ headers: {model, serial, date, fin, ...}                     │
│ counters: {color, black, df, total}                          │
│ items: List[PmItem]                                          │
│   ├─ descriptor → canon (via canon_utils)                    │
│   ├─ page_current / page_expected                            │
│   └─ drive_current / drive_expected                          │
└──────────────────────────────────────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │  run_rules (engine stage)   │
        └─────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │  build_context()            │
        │  → Context(                 │
        │      report, model,         │
        │      counters,              │
        │      items_by_canon,        │
        │      threshold, life_basis) │
        └─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                    Rule Engine Pipeline                      │
│--------------------------------------------------------------│
│  1. GenericLifeRule                                           │
│     • Calculates life_used (% of life).                       │
│     • Marks items DUE if ≥ threshold.                         │
│                                                              │
│  2. KitLinkRule                                               │
│     • Looks up canon → kit_code via part_kit_catalog.         │
│     • Resolves model’s catalog registry.                      │
│                                                              │
│  3. QtyOverrideRule (optional)                                │
│     • Overrides quantities (e.g., FILTER-OZN-KCH-A08K ×2).    │
│                                                              │
│  → All rules produce Finding objects                          │
│    merged & deduplicated by canon.                            │
└──────────────────────────────────────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │  _unit_bucket_key() logic   │
        │  • per-color kits counted   │
        │  • per-tray CST rollers     │
        │  • others aggregated once   │
        └─────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │  Selection                  │
        │  → selection_codes: {kit→qty}│
        │  → watch / not_due / all     │
        │  → meta (threshold, etc.)    │
        └─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│        resolve_to_pn / resolve_with_rows                     │
│--------------------------------------------------------------│
│  • Queries RIBON.accdb via pyodbc                            │
│  • query_parts_rows({kit_codes})                             │
│  • expand_to_part_numbers({kit→qty}, rows)                   │
│                                                              │
│  Outputs:                                                    │
│   - selection_pn: {PARTS_NO → qty}                           │
│   - selection_pn_grouped: {kit → {PARTS_NO → qty}}           │
│   - ribon_rows (raw DB data)                                 │
└──────────────────────────────────────────────────────────────┘
                     │
                     ▼
        ┌─────────────────────────────┐
        │ single_report.format_report │
        │  → generates final text     │
        │    with due items, kits,    │
        │    part numbers, counters,  │
        │    and thresholds.          │
        └─────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│          Human-Readable PM Report          │
│--------------------------------------------│
│ “Most-Due Items” list                      │
│ “Final Parts” (Qty → PN → Kit)             │
│ Counters / Threshold summary               │
└────────────────────────────────────────────┘


```

---

## ⚙️ Installation

### Prerequisites

- **Python 3.13+**
- **Microsoft Access Database Engine** (on Windows)  
  or `mdbtools` (on Linux for read-only access)
  _this gets downloaded with RIBON_
- Recommended: `pipx` or virtual environment

### Install dependencies

```bash
pip install -r requirements.txt
```

---

## 🚀 Running the App

```bash
python -m pmgen.ui.app
```

### First Run

1. On startup, enter your Toshiba e-Service credentials.
2. Enable “Stay Logged In” to persist credentials in your OS keyring.
3. Choose “Generate” and enter a serial number (e.g., **CNAM66582**).
4. The output panel displays a colorized report:

   - **Most-Due Items**
   - **Final Parts (Qty → PN → Kit)**
   - **Counters / Thresholds**

### Bulk Mode

1. Open **Bulk ▾ → Bulk Settings…**
2. Configure:

   - Top N results
   - Thread pool size
   - Output folder
   - Blacklist patterns (`*CNGM*`, `S8GN*`, etc.)
   - Optional “Unpacking date filter”

3. Choose **Bulk ▾ → Run Bulk…**
   → Runs threaded fleet analysis and writes one report per device + summary.

---

## 🧮 Rules System Overview

Rules derive from `RuleBase` and register under `pmgen.rules`.

| Rule                | Purpose                                                                           |
| ------------------- | --------------------------------------------------------------------------------- |
| **GenericLifeRule** | Flags items ≥ threshold of life used (`page` or `drive`).                         |
| **KitLinkRule**     | Maps canonized descriptors (e.g., `DRUM[Y]`) to kit codes via `part_kit_catalog`. |
| **QtyOverrideRule** | Forces custom quantities for specific kits (e.g., `FILTER-OZN-KCH-A08K: 2`).      |

Rules operate sequentially and emit `Finding` objects.
You can add custom rules by creating `pmgen/rules/my_rule.py` and importing it in `run_rules.py`.

---

## 📘 Catalog Registry

`pmgen/catalog/part_kit_catalog.py`
defines every supported Toshiba e-STUDIO model and its corresponding kits:

```python
_2515AC_3015AC_3515AC_clog = Catalog([
    EPU_KIT_FC505CLR,
    DEV_KIT_FC505K,
    FR_KIT_FC505,
    OD_FC50,
    ...
])
REGISTRY = {
    "2515AC": Model(_2515AC_3015AC_3515AC_clog),
    ...
}
```

Each `PmUnit` maps unit name → canonical items (e.g., `CANON.Y_DRUM`, `CANON.Y_GRID`).

---

## 🧠 Canon Mapping

`canon_utils.py` normalizes noisy report descriptors to canonical keys:

```
1st TRANSFER ROLLER(C)       -> None
1st TRANSFER ROLLER(K)       -> None
1st TRANSFER ROLLER(M)       -> None
1st TRANSFER ROLLER(Y)       -> None
2nd TRANSFER ROLLER          -> TRANSFER ROLLER
BELT BLADE                   -> BELT BLADE
BLACK DEVELOPER              -> DEVELOPER[K]
BRAKE PAD(DSDF)              -> None
CHARGER CLEANING PAD (C)     -> CHARGER CLEANING PAD[C]
CHARGER CLEANING PAD (K)     -> CHARGER CLEANING PAD[K]
CHARGER CLEANING PAD (M)     -> CHARGER CLEANING PAD[M]
CHARGER CLEANING PAD (Y)     -> CHARGER CLEANING PAD[Y]
CHARGER CLEANING PAD(C)      -> CHARGER CLEANING PAD[C]
CHARGER CLEANING PAD(K)      -> CHARGER CLEANING PAD[K]
CHARGER CLEANING PAD(M)      -> CHARGER CLEANING PAD[M]
CHARGER CLEANING PAD(Y)      -> CHARGER CLEANING PAD[Y]
CLEANING PAD                 -> None
CYAN DEVELOPER               -> DEVELOPER[C]
DEVELOPER                    -> DEVELOPER[K]
DRUM                         -> DRUM[K]
DRUM (C)                     -> DRUM[C]
DRUM (K)                     -> DRUM[K]
DRUM (M)                     -> DRUM[M]
DRUM (Y)                     -> DRUM[Y]
DRUM BLADE                   -> DRUM BLADE[K]
DRUM BLADE (C)               -> DRUM BLADE[C]
DRUM BLADE (K)               -> DRUM BLADE[K]
DRUM BLADE (M)               -> DRUM BLADE[M]
DRUM BLADE (Y)               -> DRUM BLADE[Y]
DRUM BLADE(C)                -> DRUM BLADE[C]
DRUM BLADE(K)                -> DRUM BLADE[K]
DRUM BLADE(M)                -> DRUM BLADE[M]
DRUM BLADE(Y)                -> DRUM BLADE[Y]
DRUM GAP SPACER (C)          -> None
DRUM GAP SPACER (K)          -> None
DRUM GAP SPACER (M)          -> None
DRUM GAP SPACER (Y)          -> None
DRUM(C)                      -> DRUM[C]
DRUM(K)                      -> DRUM[K]
DRUM(M)                      -> DRUM[M]
DRUM(Y)                      -> DRUM[Y]
FEED ROLLER (O-LCF)          -> FEED ROLLER (O-LCF)
FEED ROLLER(1st CST.)        -> FEED ROLLER (1st CST.)
FEED ROLLER(2nd CST.)        -> FEED ROLLER (2nd CST.)
FEED ROLLER(3rd CST.)        -> FEED ROLLER (3rd CST.)
FEED ROLLER(4th CST.)        -> FEED ROLLER (4th CST.)
FEED ROLLER(BYPASS)          -> FEED ROLLER (SFB/BYPASS)
FEED ROLLER(DF)              -> DF FEED ROLLER
FEED ROLLER(DSDF)            -> DF FEED ROLLER
FEED ROLLER(LCF)             -> FEED ROLLER (LCF)
FEED ROLLER(O-LCF)           -> FEED ROLLER (O-LCF)
FEED ROLLER(O2-LCF)          -> FEED ROLLER (O2-LCF)
FEED ROLLER(RADF)            -> DF FEED ROLLER
FEED ROLLER(SFB)             -> FEED ROLLER (SFB/BYPASS)
FEED ROLLER(T-LCF)           -> FEED ROLLER (T-LCF)
FUSER BELT                   -> FUSER BELT
FUSER PAD                    -> FUSER PAD
FUSER ROLLER                 -> FUSER ROLLER
GRID                         -> GRID[K]
GRID (C)                     -> GRID[C]
GRID (K)                     -> GRID[K]
GRID (M)                     -> GRID[M]
GRID (Y)                     -> GRID[Y]
GRID(C)                      -> GRID[C]
GRID(K)                      -> GRID[K]
GRID(M)                      -> GRID[M]
GRID(Y)                      -> GRID[Y]
HEAT ROLLER                  -> HEAT ROLLER
LED GAP SPACER (C)           -> None
LED GAP SPACER (K)           -> None
LED GAP SPACER (M)           -> None
LED GAP SPACER (Y)           -> None
MAGENTA DEVELOPER            -> DEVELOPER[M]
MAIN CHARGER NEEDLE (C)      -> MAIN CHARGER NEEDLE[C]
MAIN CHARGER NEEDLE (K)      -> MAIN CHARGER NEEDLE[K]
MAIN CHARGER NEEDLE (M)      -> MAIN CHARGER NEEDLE[M]
MAIN CHARGER NEEDLE (Y)      -> MAIN CHARGER NEEDLE[Y]
MAIN CHARGER NEEDLE(C)       -> MAIN CHARGER NEEDLE[C]
MAIN CHARGER NEEDLE(K)       -> MAIN CHARGER NEEDLE[K]
MAIN CHARGER NEEDLE(M)       -> MAIN CHARGER NEEDLE[M]
MAIN CHARGER NEEDLE(Y)       -> MAIN CHARGER NEEDLE[Y]
NEEDLE ELECTRODE             -> MAIN CHARGER NEEDLE[K]
OIL RECOVERY  SHEET          -> OIL/SLIDE SHEET
OZONE FILTER                 -> OZONE FILTER
OZONE FILTER (REAR)          -> OZONE FILTER
OZONE FILTER 1               -> OZONE FILTER 1
OZONE FILTER 2               -> OZONE FILTER 2
OZONE FILTER(REAR)           -> OZONE FILTER
PICK UP ROLLER (1st CST.)    -> PICK UP ROLLER (1st CST.)
PICK UP ROLLER (O-LCF)       -> PICK UP ROLLER (O-LCF)
PICK UP ROLLER(1st CST.)     -> PICK UP ROLLER (1st CST.)
PICK UP ROLLER(2nd CST.)     -> PICK UP ROLLER (2nd CST.)
PICK UP ROLLER(3rd CST.)     -> PICK UP ROLLER (3rd CST.)
PICK UP ROLLER(4th CST.)     -> PICK UP ROLLER (4th CST.)
PICK UP ROLLER(BYPASS)       -> PICK UP ROLLER/PAD (SFB/BYPASS)
PICK UP ROLLER(DF)           -> DF PICK UP ROLLER
PICK UP ROLLER(DSDF)         -> DF PICK UP ROLLER
PICK UP ROLLER(LCF)          -> PICK UP ROLLER (LCF)
PICK UP ROLLER(O-LCF)        -> PICK UP ROLLER (O-LCF)
PICK UP ROLLER(O2-LCF)       -> PICK UP ROLLER (O2-LCF)
PICK UP ROLLER(RADF)         -> DF PICK UP ROLLER
PICK UP ROLLER(SFB)          -> PICK UP ROLLER/PAD (SFB/BYPASS)
PICK UP ROLLER(T-LCF)        -> PICK UP ROLLER (T-LCF)
PICK UP ROLLER/FEED ROLLER(DSDF) -> PICK UP ROLLER/FEED ROLLER(DSDF)
PRESS ROLLER                 -> PRESS ROLLER
PRESS ROLLER FINGER          -> PRESS ROLLER FINGER
RECOVERY BLADE               -> RECOVERY BLADE
SEP PAD(1st CST.)            -> SEP ROLLER/PAD (1st CST.)
SEP PAD(SFB)                 -> SEP ROLLER/PAD (SFB/BYPASS)
SEP ROLLER (1st CST.)        -> SEP ROLLER/PAD (1st CST.)
SEP ROLLER (O-LCF)           -> SEP ROLLER/PAD (O-LCF)
SEP ROLLER(1st CST.)         -> SEP ROLLER/PAD (1st CST.)
SEP ROLLER(2nd CST.)         -> SEP ROLLER/PAD (2nd CST.)
SEP ROLLER(3rd CST.)         -> SEP ROLLER/PAD (3rd CST.)
SEP ROLLER(4th CST.)         -> SEP ROLLER/PAD (4th CST.)
SEP ROLLER(BYPASS)           -> SEP ROLLER/PAD (SFB/BYPASS)
SEP ROLLER(DF)               -> DF SEP ROLLER
SEP ROLLER(DSDF)             -> DF SEP ROLLER
SEP ROLLER(LCF)              -> SEP ROLLER/PAD (LCF)
SEP ROLLER(O-LCF)            -> SEP ROLLER/PAD (O-LCF)
SEP ROLLER(O2-LCF)           -> SEP ROLLER/PAD (O2-LCF)
SEP ROLLER(RADF)             -> DF SEP ROLLER
SEP ROLLER(SFB)              -> SEP ROLLER/PAD (SFB/BYPASS)
SEP ROLLER(T-LCF)            -> SEP ROLLER/PAD (T-LCF)
SEPARATION FINGER(DRUM)      -> SEPARATION FINGER (DRUM)
SEPARATION FINGER(FUSER)     -> SEPARATION FINGER (FUSER)
SLIDE SHEET                  -> OIL/SLIDE SHEET
TBU DRIVER ROLLER            -> None
TONER FILTER                 -> TONER FILTER
TRANSFER BELT                -> TRANSFER BELT
TRANSFER ROLLER              -> TRANSFER ROLLER
VOC FILTER                   -> VOC FILTER
YELLOW DEVELOPER             -> DEVELOPER[Y]
```

This ensures stable matching between parsed reports and catalog entries. You may notice not all descriptors get converted into a canon descriptor. This is because either they may differ too much between models or may not have been deemed necesarry for determining if the PM kit/part needs replaced.

Run stand-alone tests:

```bash
python -m pmgen.catalog.canon_utils
```

---

## 🧵 Session & Networking

- `http_client.py` provides `SessionPool` for thread-safe reuse.
- `get_serials_after_login()` → fetches all active serial numbers.
- `get_service_file_bytes(serial, "PMSupport")` → downloads the PM report.
- `get_unpacking_date()` → returns `date` of initial device unpacking.

All HTTP calls are `requests.Session` based with shared cookies.

---

## 📊 Output Example

```
Model: TOSHIBA e-STUDIO2515AC  |  Serial: CNAM66582  |  Date: 11-05-2025 01:34
Due threshold: 63.0%  •  Basis: PAGE

Counters:
  Color: 57278  Black: 56518  DF: 42152  Total: 113796

───────────────────────────────────────────────────────────────
Most-Due Items
───────────────
  • PICK UP ROLLER (1st CST.) — 95.1% → DUE
      ↳ Catalog: ROL-KIT-FC30-U

  • FEED ROLLER (1st CST.) — 95.1% → DUE
      ↳ Catalog: ROL-KIT-FC30-U

  • SEP ROLLER/PAD (1st CST.) — 95.1% → DUE
      ↳ Catalog: ROL-KIT-FC30-U

  • DRUM[Y] — 82.3% → DUE
      ↳ Catalog: OD-FC50

  • DRUM BLADE[Y] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • GRID[Y] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • MAIN CHARGER NEEDLE[Y] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • CHARGER CLEANING PAD[Y] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • DRUM[M] — 82.3% → DUE
      ↳ Catalog: OD-FC50

  • DRUM BLADE[M] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • GRID[M] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • MAIN CHARGER NEEDLE[M] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • CHARGER CLEANING PAD[M] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • DRUM[C] — 82.3% → DUE
      ↳ Catalog: OD-FC50

  • DRUM BLADE[C] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • GRID[C] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • MAIN CHARGER NEEDLE[C] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • CHARGER CLEANING PAD[C] — 82.3% → DUE
      ↳ Catalog: EPU-KIT-FC505CLR

  • DRUM GAP SPACER (Y) — 82.3% → DUE
      ↳ Catalog: (N/A)

  • DRUM GAP SPACER (M) — 82.3% → DUE
      ↳ Catalog: (N/A)

  • DRUM GAP SPACER (C) — 82.3% → DUE
      ↳ Catalog: (N/A)

  • DRUM[K] — 80.0% → DUE
      ↳ Catalog: OD-FC505

  • DRUM BLADE[K] — 80.0% → DUE
      ↳ Catalog: DEV-KIT-FC505K

  • GRID[K] — 80.0% → DUE
      ↳ Catalog: DEV-KIT-FC505K

  • MAIN CHARGER NEEDLE[K] — 80.0% → DUE
      ↳ Catalog: DEV-KIT-FC505K

  • CHARGER CLEANING PAD[K] — 80.0% → DUE
      ↳ Catalog: DEV-KIT-FC505K

  • DEVELOPER[K] — 80.0% → DUE
      ↳ Catalog: DEV-KIT-FC505K

  • BELT BLADE — 80.0% → DUE
      ↳ Catalog: TBU-KIT-FC50

  • TRANSFER ROLLER — 80.0% → DUE
      ↳ Catalog: CR-FC30TR2

  • DRUM GAP SPACER (K) — 80.0% → DUE
      ↳ Catalog: (N/A)

  • FUSER BELT — 60.0%
      ↳ Catalog: (N/A)

  • PRESS ROLLER — 60.0%
      ↳ Catalog: (N/A)

  • PRESS ROLLER FINGER — 60.0%
      ↳ Catalog: (N/A)

  • FUSER PAD — 60.0%
      ↳ Catalog: (N/A)

  • OIL/SLIDE SHEET — 60.0%
      ↳ Catalog: (N/A)

  • DEVELOPER[Y] — 41.1%
      ↳ Catalog: (N/A)

  • DEVELOPER[M] — 41.1%
      ↳ Catalog: (N/A)

  • DEVELOPER[C] — 41.1%
      ↳ Catalog: (N/A)

  • DF PICK UP ROLLER — 37.6%
      ↳ Catalog: (N/A)

  • DF FEED ROLLER — 37.6%
      ↳ Catalog: (N/A)

  • DF SEP ROLLER — 37.6%
      ↳ Catalog: (N/A)

  • OZONE FILTER — 26.7%
      ↳ Catalog: (N/A)

  • PICK UP ROLLER (4th CST.) — 11.1%
      ↳ Catalog: (N/A)

  • FEED ROLLER (4th CST.) — 11.1%
      ↳ Catalog: (N/A)

  • SEP ROLLER/PAD (4th CST.) — 11.1%
      ↳ Catalog: (N/A)

  • PICK UP ROLLER (2nd CST.) — 10.3%
      ↳ Catalog: (N/A)

  • FEED ROLLER (2nd CST.) — 10.3%
      ↳ Catalog: (N/A)

  • SEP ROLLER/PAD (2nd CST.) — 10.3%
      ↳ Catalog: (N/A)

  • PICK UP ROLLER (3rd CST.) — 7.6%
      ↳ Catalog: (N/A)

  • FEED ROLLER (3rd CST.) — 7.6%
      ↳ Catalog: (N/A)

  • SEP ROLLER/PAD (3rd CST.) — 7.6%
      ↳ Catalog: (N/A)

  • FEED ROLLER (SFB/BYPASS) — 0.3%
      ↳ Catalog: (N/A)

  • SEP ROLLER/PAD (SFB/BYPASS) — 0.3%
      ↳ Catalog: (N/A)

  • PICK UP ROLLER (LCF) — 0.0%
      ↳ Catalog: (N/A)

  • FEED ROLLER (LCF) — 0.0%
      ↳ Catalog: (N/A)

  • SEP ROLLER/PAD (LCF) — 0.0%
      ↳ Catalog: (N/A)


Final Parts
───────────────────────────────────────────────────────────────
(Qty → Part Number → Unit )
1x → 6LK50755000 → ROL-KIT-FC30-U
3x → 6LJ70598000 → OD-FC50
1x → 6LK49167000 → EPU-KIT-FC505CLR
1x → 6LK49015000 → OD-FC505
1x → 6LK49168000 → DEV-KIT-FC505K
1x → 6LJ70575000 → TBU-KIT-FC50
1x → 6LJ58192000 → CR-FC30TR2

───────────────────────────────────────────────────────────────
End of Report
```

---

## 🧩 Extending the System

| Goal                 | How                                                |
| -------------------- | -------------------------------------------------- |
| Add new model        | Define its `Catalog([...])` and add to `REGISTRY`. |
| Add new rule         | Drop `rules/my_rule.py` → extend `run_rules.py`.   |
| Add new part mapping | Update `canon_utils.CANON_MAP`.                    |
| Adjust qty override  | Edit `qty_override.py → QTY_OVERRIDES`.            |

---

## 🧾 License

**License:** Business Source License 1.1 (will convert to Apache 2.0 on 2028-11-05)
