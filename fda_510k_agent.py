#!/usr/bin/env python3
"""Query FDA 510(k) device data by product code."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable


API_BASE = "https://api.fda.gov/device/510k.json"
DEFAULT_PAGE_SIZE = 100
USER_AGENT = "RAgent-510k-Search/1.0 (+https://api.fda.gov)"


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
        manufacturer=result.get("applicant", "") or result.get("applicant", ""),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search FDA 510(k) devices by product code.",
    )
    parser.add_argument("product_code", help="FDA product code to search")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to return",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Records fetched per API call (max 100)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "ndjson"),
        default="json",
        help="Output format",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
