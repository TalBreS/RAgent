#!/usr/bin/env python3
"""CLI utilities for FDA medical device data workflows."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Iterable


API_BASE = "https://api.fda.gov/device/510k.json"
DEFAULT_PAGE_SIZE = 100
USER_AGENT = "RAgent-510k-Search/1.0 (+https://api.fda.gov)"


# CDRH OHT groups based on the FDA OPEQ office structure.
PANEL_TO_OHT = {
    "anesthesiology": "OHT1",
    "dental": "OHT1",
    "ear nose & throat": "OHT1",
    "ent": "OHT1",
    "ophthalmic": "OHT1",
    "respiratory": "OHT1",
    "cardiovascular": "OHT2",
    "gastroenterology-urology": "OHT3",
    "general hospital": "OHT3",
    "obstetrics and gynecology": "OHT3",
    "obstetrics & gynecology": "OHT3",
    "general & plastic surgery": "OHT4",
    "general and plastic surgery": "OHT4",
    "infection control": "OHT4",
    "neurology": "OHT5",
    "physical medicine": "OHT5",
    "orthopedic": "OHT6",
    "clinical chemistry": "OHT7",
    "hematology": "OHT7",
    "immunology": "OHT7",
    "microbiology": "OHT7",
    "pathology": "OHT7",
    "toxicology": "OHT7",
    "radiology": "OHT8",
}


@dataclass
class DeviceRecord:
    k_number: str
    device_name: str
    manufacturer: str
    indications_for_use: str
    summary_of_technology: str

    def as_dict(self) -> dict:
        return {
            "k_number": self.k_number,
            "device_name": self.device_name,
            "manufacturer": self.manufacturer,
            "indications_for_use": self.indications_for_use,
            "summary_of_technology": self.summary_of_technology,
        }


@dataclass
class AIMLRecord:
    final_decision_date: date
    submission_number: str
    device: str
    company: str
    panel: str
    primary_product_code: str
    oht: str


class FDAClientError(RuntimeError):
    pass


def build_query(product_code: str, limit: int, skip: int) -> str:
    params = {
        "search": f"product_code:{product_code}",
        "limit": str(limit),
        "skip": str(skip),
    }
    return f"{API_BASE}?{urllib.parse.urlencode(params)}"


def fetch_json(url: str, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise FDAClientError(f"FDA API request failed ({exc.code}): {exc.read().decode()}") from exc
    except urllib.error.URLError as exc:
        raise FDAClientError(f"FDA API connection failed: {exc.reason}") from exc


def extract_record(result: dict) -> DeviceRecord:
    return DeviceRecord(
        k_number=result.get("k_number", ""),
        device_name=result.get("device_name", ""),
        manufacturer=result.get("applicant", ""),
        indications_for_use=result.get("indications_for_use", ""),
        summary_of_technology=result.get("summary_of_technology", "")
        or result.get("device_description", ""),
    )


def iter_devices(product_code: str, page_size: int = DEFAULT_PAGE_SIZE) -> Iterable[DeviceRecord]:
    skip = 0
    while True:
        url = build_query(product_code, limit=page_size, skip=skip)
        payload = fetch_json(url)
        results = payload.get("results", [])
        if not results:
            break
        for result in results:
            yield extract_record(result)
        skip += len(results)
        total = payload.get("meta", {}).get("results", {}).get("total")
        if total is not None and skip >= total:
            break
        time.sleep(0.1)


def infer_oht(panel: str) -> str:
    normalized = " ".join(panel.lower().strip().split())
    return PANEL_TO_OHT.get(normalized, "Unmapped")


def load_aiml_csv(csv_path: Path) -> list[AIMLRecord]:
    records: list[AIMLRecord] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected_columns = {
            "Date of Final Decision",
            "Submission Number",
            "Device",
            "Company",
            "Panel (Lead)",
            "Primary Product Code",
        }
        missing = expected_columns.difference(reader.fieldnames or set())
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

        for row in reader:
            raw_date = (row.get("Date of Final Decision") or "").strip()
            if not raw_date:
                continue
            final_decision_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
            panel = (row.get("Panel (Lead)") or "").strip()
            records.append(
                AIMLRecord(
                    final_decision_date=final_decision_date,
                    submission_number=(row.get("Submission Number") or "").strip(),
                    device=(row.get("Device") or "").strip(),
                    company=(row.get("Company") or "").strip(),
                    panel=panel,
                    primary_product_code=(row.get("Primary Product Code") or "").strip(),
                    oht=infer_oht(panel),
                )
            )
    return records


def filter_last_year(records: list[AIMLRecord], as_of: date) -> list[AIMLRecord]:
    lower_bound = as_of - timedelta(days=365)
    return [record for record in records if lower_bound <= record.final_decision_date <= as_of]


def render_dashboard(records: list[AIMLRecord], as_of: date) -> str:
    counts: dict[str, int] = {f"OHT{i}": 0 for i in range(1, 9)}
    counts["Unmapped"] = 0
    grouped: dict[str, list[AIMLRecord]] = {k: [] for k in counts}

    for record in sorted(records, key=lambda item: item.final_decision_date, reverse=True):
        key = record.oht if record.oht in grouped else "Unmapped"
        grouped[key].append(record)
        counts[key] += 1

    cards = "\n".join(
        f'<div class="card"><h3>{escape(oht)}</h3><p>{count}</p></div>'
        for oht, count in counts.items()
        if oht != "Unmapped"
    )
    if counts["Unmapped"]:
        cards += f'\n<div class="card warning"><h3>Unmapped</h3><p>{counts["Unmapped"]}</p></div>'

    sections = []
    for oht in [f"OHT{i}" for i in range(1, 9)] + (["Unmapped"] if counts["Unmapped"] else []):
        items = grouped.get(oht, [])
        if not items:
            continue

        rows = "\n".join(
            "<tr>"
            f"<td>{item.final_decision_date.isoformat()}</td>"
            f"<td>{escape(item.submission_number)}</td>"
            f"<td>{escape(item.device)}</td>"
            f"<td>{escape(item.company)}</td>"
            f"<td>{escape(item.panel)}</td>"
            f"<td>{escape(item.primary_product_code)}</td>"
            "</tr>"
            for item in items
        )
        sections.append(
            f"""
            <section>
              <h2>{escape(oht)} <span>({len(items)})</span></h2>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Submission</th>
                    <th>Device</th>
                    <th>Company</th>
                    <th>Panel</th>
                    <th>Product Code</th>
                  </tr>
                </thead>
                <tbody>
                  {rows}
                </tbody>
              </table>
            </section>
            """.strip()
        )

    return f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>FDA AI/ML Devices - Last Year by OHT</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1d2433; }}
    h1 {{ margin-bottom: 6px; }}
    .meta {{ color: #4b5563; margin-bottom: 18px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; margin-bottom: 24px; }}
    .card {{ background: #eef5ff; border-radius: 8px; padding: 12px; text-align: center; }}
    .card.warning {{ background: #fff4e5; }}
    .card h3 {{ margin: 0; font-size: 14px; }}
    .card p {{ margin: 8px 0 0; font-size: 22px; font-weight: 700; }}
    section {{ margin-bottom: 26px; }}
    h2 span {{ color: #6b7280; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
  </style>
</head>
<body>
  <h1>FDA AI/ML-Enabled Devices Dashboard</h1>
  <p class=\"meta\">Showing clearances/approvals from {(as_of - timedelta(days=365)).isoformat()} to {as_of.isoformat()} (inclusive).</p>
  <div class=\"cards\">{cards}</div>
  {'\n'.join(sections)}
</body>
</html>
""".strip()


def run_search_mode(args: argparse.Namespace) -> int:
    limit = args.limit
    output = []
    count = 0
    try:
        for record in iter_devices(args.product_code, page_size=args.page_size):
            output.append(record.as_dict())
            count += 1
            if limit is not None and count >= limit:
                break
    except FDAClientError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "ndjson":
        for item in output:
            print(json.dumps(item, ensure_ascii=False))
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def run_aiml_dashboard_mode(args: argparse.Namespace) -> int:
    try:
        records = load_aiml_csv(Path(args.input_csv))
    except (OSError, ValueError) as exc:
        print(f"Error reading input CSV: {exc}", file=sys.stderr)
        return 1

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else datetime.now(UTC).date()
    filtered = filter_last_year(records, as_of=as_of)

    dashboard_html = render_dashboard(filtered, as_of=as_of)
    output_path = Path(args.output_html)
    output_path.write_text(dashboard_html, encoding="utf-8")

    print(
        json.dumps(
            {
                "input_records": len(records),
                "records_last_year": len(filtered),
                "as_of": as_of.isoformat(),
                "output_html": str(output_path),
            },
            indent=2,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FDA device tooling utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search-510k", help="Search FDA 510(k) devices by product code")
    search_parser.add_argument("product_code", help="FDA product code to search")
    search_parser.add_argument("--limit", type=int, default=None, help="Maximum number of records to return")
    search_parser.add_argument(
        "--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Records fetched per API call (max 100)"
    )
    search_parser.add_argument("--format", choices=("json", "ndjson"), default="json", help="Output format")
    search_parser.set_defaults(func=run_search_mode)

    dashboard_parser = subparsers.add_parser(
        "aiml-dashboard",
        help="Create an HTML dashboard from downloaded FDA AI/ML devices CSV",
    )
    dashboard_parser.add_argument("input_csv", help="Path to FDA CSV download")
    dashboard_parser.add_argument(
        "--output-html",
        default="aiml_last_year_dashboard.html",
        help="Output HTML path",
    )
    dashboard_parser.add_argument(
        "--as-of",
        default=None,
        help="Reference date in YYYY-MM-DD (defaults to today's UTC date)",
    )
    dashboard_parser.set_defaults(func=run_aiml_dashboard_mode)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
