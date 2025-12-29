# FDA 510(k) Search Agent

This repository provides a simple agent/CLI to query the FDA 510(k) database for all devices matching a product code.

## Usage

```bash
python fda_510k_agent.py <PRODUCT_CODE>
```

Examples:

```bash
python fda_510k_agent.py KJZ
python fda_510k_agent.py KJZ --limit 25 --format ndjson
```

Output fields:

- `k_number`
- `device_name`
- `manufacturer`
- `indications_for_use`
- `summary_of_technology`

The script paginates through the FDA `device/510k` endpoint and returns JSON output with all matching records (or up to the `--limit`).
