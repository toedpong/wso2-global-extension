#!/usr/bin/env python3
"""Export captured request/response pairs as JSON unit-test fixtures.

Reads rows from public.api_request_log_for_migration (written by the
Custom-DBLogger-In/Out sequences) and writes one JSON file per captured
call under <out-dir>/<API_NAME>/. Fixtures can then be used to drive
CPI iFlow unit tests: send `request` and assert against `expected_response`.

Usage:
    pip install psycopg2-binary
    export PGHOST=... PGPORT=... PGDATABASE=... PGUSER=... PGPASSWORD=...
    python tools/export_fixtures.py --out fixtures [--api OR_HR_ZHRHRI001 ...] [--completed-only]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

SELECT_SQL = """
SELECT message_id, api_name, api_version, full_url, resource_path, http_method,
       content_type, client_ip, app_name, user_id, client_id,
       request_headers, request_data, request_time,
       response_headers, response_data, http_status, response_time, execution_time_ms
FROM public.api_request_log_for_migration
{where}
ORDER BY api_name, request_time
"""


def parse_json_or_text(value):
    if value is None or value == "" or value == "No Payload":
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value or "unknown")


def row_to_fixture(row):
    return {
        "name": f"{row['api_name']}_{row['message_id']}",
        "api": {
            "name": row["api_name"],
            "version": row["api_version"],
        },
        "captured": {
            "message_id": row["message_id"],
            "request_time": row["request_time"].isoformat() if row["request_time"] else None,
            "response_time": row["response_time"].isoformat() if row["response_time"] else None,
            "execution_time_ms": row["execution_time_ms"],
            "client_ip": row["client_ip"],
            "app_name": row["app_name"],
            "user_id": row["user_id"],
            "client_id": row["client_id"],
        },
        "request": {
            "method": row["http_method"],
            "url": row["full_url"],
            "path": row["resource_path"],
            "headers": parse_json_or_text(row["request_headers"]) or {},
            "body": parse_json_or_text(row["request_data"]),
        },
        "expected_response": {
            "status": int(row["http_status"]) if row["http_status"] else None,
            "headers": parse_json_or_text(row["response_headers"]) or {},
            "body": parse_json_or_text(row["response_data"]),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="fixtures", help="output directory (default: fixtures)")
    parser.add_argument("--api", action="append", help="only export these API names (repeatable)")
    parser.add_argument("--completed-only", action="store_true", help="skip rows with no response yet")
    args = parser.parse_args()

    conditions, params = [], []
    if args.api:
        conditions.append("api_name = ANY(%s)")
        params.append(args.api)
    if args.completed_only:
        conditions.append("http_status IS NOT NULL")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    dsn = {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "dbname": os.environ.get("PGDATABASE", "cpidev"),
        "user": os.environ.get("PGUSER", "cpiadmin"),
        "password": os.environ.get("PGPASSWORD"),
    }
    if not dsn["password"]:
        sys.exit("PGPASSWORD is not set")

    out_dir = Path(args.out)
    written = 0
    with psycopg2.connect(**dsn) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(SELECT_SQL.format(where=where), params)
        for row in cur:
            fixture = row_to_fixture(row)
            api_dir = out_dir / safe_name(row["api_name"])
            api_dir.mkdir(parents=True, exist_ok=True)
            target = api_dir / f"{safe_name(row['message_id'])}.json"
            target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            written += 1

    print(f"wrote {written} fixture(s) to {out_dir}")


if __name__ == "__main__":
    main()
