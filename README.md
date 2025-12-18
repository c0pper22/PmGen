# 🧭 PmGen — Toshiba e-STUDIO Preventive Maintenance Generator

**PmGen** is a modern Python 3.13 application (PyQt6) that automates the generation of preventive-maintenance (PM) parts lists for Toshiba e-STUDIO MFP devices.

It fetches official **PM Support Code List** reports, applies rule-based logic to determine due items, resolves part numbers via a local database, and can cross-reference results against your local **Inventory** to generate precise "Order Lists" versus "In-Stock" matches.

---

## ✨ New in this Version

| Feature | Description |
| --- | --- |
| **📦 Inventory System** | A dedicated **Inventory Tab** allows you to import stock CSVs, manually add/edit items, and track total stock value. |
| **✅ Stock Reconciliation** | The report engine now checks your inventory cache. Reports automatically split items into **"Inventory Matches (In Stock)"** and **"Items to Order"**. |
| **📅 Smart Bulk Filters** | The Bulk Runner now supports **Unpack Date filtering**. You can exclude machines that are too new (< X months) or too old (> X months). |
| **🖥️ Modern UI** | A custom frameless interface with tabbed navigation ("Home" vs "Inventory"), auto-complete for serials, and a colorized output editor. |

---

## 🚀 Features Overview

* **Smart Parsing:** Fetches and parses PM Support Code Lists from Toshiba Elevate Sky / e-Service.
* **Rule Engine:** Applies a pipeline of logic:
1. **Life Calculation:** Flags items based on % life used (Page or Drive basis).
2. **Canon Mapping:** Normalizes varying descriptor names (e.g., `DRUM[Y]`) to standard codes.
3. **Part Resolution:** Resolves generic kit codes to specific Part Numbers using `Ribon.accdb`.
4. **Inventory Check:** Compares needed parts against local stock levels.


* **Bulk Fleet Analysis:** Multi-threaded processing of hundreds of serials. Generates a consolidated PDF summary with color-coded stock status (Red=Missing, Yellow=Partial, Green=In Stock).
* **Authentication:** Secure login with OS keyring support.
* **Auto-Updater:** Integrated update checker to keep the tool current.

---

## 🧱 Architecture & Logic Flow

The system now operates on a **Tabbed** workflow:

1. **Inventory Tab:** Manage your stock.
* Load CSVs (currently only supports EAutomate csv export) or manually add rows.
* Data is cached locally to `inventory_cache.csv`.


2. **Home Tab:** Generate reports.
* Enter Serial -> Fetch Data -> Run Rules -> Check Inventory -> Output Report.



### The Rule Pipeline

`run_rules.py` orchestrates the logic in this specific order:

1. `GenericLifeRule`: Calculates life used vs threshold.
2. `KitLinkRule`: Maps descriptors to Catalog Kit Codes.
3. `UnitGroupingRule`: Groups items (e.g., Color Drums, Feed Rollers).
4. `QtyOverrideRule`: Applies manual quantity fixes.
5. **`InventoryCheckRule`**: Queries the loaded inventory cache to determine what is in stock vs missing.
6. `RibonExpansionRule`: Finalizes part numbers.

### Inventory Logic

When generating a report, PmGen looks at `inventory_cache.csv`.

* **Matches:** If you have the part, it appears under "Inventory Matches."
* **Missing:** If you have 0 or partial quantity, it appears under "Items to Order."
* **Summary PDF:** The bulk summary uses color codes:
* 🟥 **Red:** 0 Stock (Need to order)
* 🟨 **Yellow:** Partial Stock (Need to order balance)
* 🟩 **Green:** Full Stock (No order needed)



---

## ⚙️ Installation

### Prerequisites

* **Python 3.13+**
* **Toshiba's RIBON.exe**

### Install dependencies

```bash
pip install -r requirements.txt

```

---

## 🖥️ Usage Guide

### 1. Inventory Management

Go to the **Inventory** tab.

* **Import:** Load a CSV file (only supports EAutomate csv export).
* **Edit:** Double-click cells to update Quantities or Costs.
* **Add/Delete:** Use the toolbar buttons to manage rows manually.
* *Note: Changes are auto-saved to your local cache.*

### 2. Single Report (Home Tab)

1. Enter a **Serial Number** (Auto-complete remembers history).
2. Click **Generate** (or press Enter).
3. The output window displays:
* **Highest Wear Items:** Items exceeding the % threshold.
* **Final Parts:** Total quantities needed.
* **Inventory Matches:** Parts you already have.
* **Items to Order:** Parts you need to buy.



### 3. Bulk Mode

Go to **Bulk ▾ → Bulk Settings…**

* **Top N:** How many "most worn" machines to include in the summary.
* **Pool Size:** Number of parallel download threads.
* **Date Filters:**
* `Exclude if OLDER than X months`: Ignores old machines (based on unpack date).
* `Exclude if NEWER than X months`: Ignores brand new installs.


* **Run Bulk:** Processes the fleet and produces individual PDFs + `Final_Summary.pdf`.

---

## 📊 Output Example

**Text Report (Home Tab):**

```text
Highest Wear Items
───────────────────────────────────────────────────────────────
  • DRUM[K] — 112.5% → DUE
      ↳ Unit: OD-FC505

Inventory Matches (In Stock)
───────────────────────────────────────────────────────────────
(Matched Code → Needed → In Stock)
  ✓ 6LK49015000 : Need 1 | Have 5

Items to Order (Missing from Stock)
───────────────────────────────────────────────────────────────
(Code → Qty to Order)
  ! 6LK50755000 : 2

```

**Bulk Summary PDF:**
Contains a "Traffic Light" table showing exactly what needs to be ordered for the entire fleet batch, factoring in your current shelf inventory.

---

## 🧾 License

**License:** Business Source License 1.1 (will convert to Apache 2.0 on 2028-11-05)