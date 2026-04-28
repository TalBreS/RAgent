# FDA Device Utilities (RAgent)

This repository provides a CLI with two workflows:

1. Search FDA 510(k) records by product code.
2. Build a dashboard from the FDA AI/ML-enabled devices CSV download.

## Installation

```bash
pip install -e .
```

## Usage

### 1) Search FDA 510(k) records

```bash
ragent search-510k <PRODUCT_CODE>
```

Examples:

```bash
ragent search-510k KJZ
ragent search-510k KJZ --limit 25 --format ndjson
```

Output fields:

- `k_number`
- `device_name`
- `manufacturer`
- `indications_for_use`
- `summary_of_technology`

### 2) Build AI/ML dashboard for the last year, grouped by CDRH OHT1-8

1. Go to FDA's **Artificial Intelligence-Enabled Medical Devices** page.
2. Download the **CSV file**.
3. Run:

```bash
ragent aiml-dashboard path/to/artificial-intelligence-enabled-medical-devices.csv
```

Optional arguments:

```bash
ragent aiml-dashboard input.csv --output-html dashboard.html --as-of 2026-04-28
```

The command generates an HTML dashboard with:

- records filtered to the last 365 days from the `--as-of` date (or today),
- count cards for OHT1 through OHT8,
- detailed per-OHT tables with date, submission number, device, company, panel, and product code,
- an `Unmapped` section for any panel values that do not match known OHT panel mappings.

### View the generated dashboard

After running `ragent aiml-dashboard ...`, open the output HTML in a browser:

```bash
# Option 1: open directly as a local file
open dashboard.html   # macOS
xdg-open dashboard.html  # Linux
```

If direct file opening is restricted by your browser, serve it locally:

```bash
python -m http.server 8000
# then visit http://localhost:8000/dashboard.html
```
