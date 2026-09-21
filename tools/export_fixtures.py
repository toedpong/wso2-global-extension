#!/usr/bin/env python3
"""Export captured request/response pairs as JSON unit-test fixtures.

Reads rows from public.api_request_log_for_migration (written by the
Custom-DBLogger-In/Out sequences) and writes one JSON file per captured
call under <out-dir>/<API_NAME>/. Fixtures can then be used to drive
CPI iFlow unit tests: send `request` and assert against `expected_response`.

Bodies are decoded according to the captured *_format column:
    json   -> parsed JSON object inline in the fixture
    xml    -> XML string inline + <message_id>.request.xml / .response.xml
    form   -> Synapse <xformValues> converted to a {field: value} dict
    text   -> plain string inline
    binary -> base64 inline + decoded bytes in <message_id>.request.bin / .response.bin

Usage:
    pip install psycopg2-binary
    export PGHOST=... PGPORT=... PGDATABASE=... PGUSER=... PGPASSWORD=...
    python tools/export_fixtures.py --out fixtures [--api OR_HR_ZHRHRI001 ...] [--completed-only]
"""

import argparse
import base64
import binascii
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2
import psycopg2.extras

SELECT_SQL = """
SELECT message_id, api_name, api_version, full_url, resource_path, http_method,
       content_type, client_ip, app_name, user_id, client_id,
       request_headers, request_data, request_format, request_time,
       response_headers, response_data, response_format, response_content_type,
       http_status, response_time, execution_time_ms
FROM public.api_request_log_for_migration
{where}
ORDER BY api_name, request_time
"""


NO_PAYLOAD = (None, "", "No Payload")

RAW_EXTENSIONS = {"xml": ".xml", "binary": ".bin"}


def parse_json_or_text(value):
    if value in NO_PAYLOAD:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def form_to_dict(value):
    try:
        root = ET.fromstring(value)
    except ET.ParseError:
        return value
    return {strip_ns(child.tag): (child.text or "") for child in root}


def guess_format(value):
    """Fallback for rows captured before *_format existed."""
    if value in NO_PAYLOAD:
        return "none"
    stripped = value.lstrip()
    if stripped.startswith(("{", "[")):
        return "json"
    if stripped.startswith("<"):
        return "xml"
    return "text"


def decode_body(value, fmt):
    """Return (inline_body, raw_bytes_or_None)."""
    fmt = fmt or guess_format(value)
    if fmt == "none" or value in NO_PAYLOAD:
        return None, None
    if fmt == "json":
        return parse_json_or_text(value), None
    if fmt == "form":
        return form_to_dict(value), None
    if fmt == "binary":
        try:
            return value, base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return value, None
    if fmt == "xml":
        return value, value.encode("utf-8")
    return value, None


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value or "unknown")


def row_to_fixture(row):
    req_fmt = row["request_format"] or guess_format(row["request_data"])
    resp_fmt = row["response_format"] or guess_format(row["response_data"])
    req_body, req_raw = decode_body(row["request_data"], req_fmt)
    resp_body, resp_raw = decode_body(row["response_data"], resp_fmt)
    raw_files = {"request": (req_fmt, req_raw), "expected_response": (resp_fmt, resp_raw)}
    return raw_files, {
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
            "content_type": row["content_type"],
            "headers": parse_json_or_text(row["request_headers"]) or {},
            "body_format": req_fmt,
            "body": req_body,
        },
        "expected_response": {
            "status": int(row["http_status"]) if row["http_status"] else None,
            "content_type": row["response_content_type"],
            "headers": parse_json_or_text(row["response_headers"]) or {},
            "body_format": resp_fmt,
            "body": resp_body,
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
            raw_files, fixture = row_to_fixture(row)
            api_dir = out_dir / safe_name(row["api_name"])
            api_dir.mkdir(parents=True, exist_ok=True)
            stem = safe_name(row["message_id"])
            for section, (fmt, raw) in raw_files.items():
                if raw is not None and fmt in RAW_EXTENSIONS:
                    side = "request" if section == "request" else "response"
                    raw_name = f"{stem}.{side}{RAW_EXTENSIONS[fmt]}"
                    (api_dir / raw_name).write_bytes(raw)
                    fixture[section]["body_file"] = raw_name
            target = api_dir / f"{stem}.json"
            target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            written += 1

    print(f"wrote {written} fixture(s) to {out_dir}")


if __name__ == "__main__":
    main()
