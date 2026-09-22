import base64
import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import requests

from .cpi import sender_path

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}


def iter_fixtures(fixtures_dir, names=None):
    wanted = set(names) if names else None
    base = Path(fixtures_dir)
    for api_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if wanted and api_dir.name not in wanted:
            continue
        for f in sorted(api_dir.glob("*.json")):
            yield api_dir.name, f


def _clean_headers(headers, extra):
    out = {}
    for k, v in (headers or {}).items():
        kl = k.lower()
        if kl in HOP_HEADERS or v == "***MASKED***":
            continue
        out[k] = v
    for kv in extra or []:
        k, _, v = kv.partition(":")
        out[k.strip()] = v.strip()
    return out


def build_request(fixture, base_url, path_mode="wso2", extra_headers=None):
    req = fixture["request"]
    api_name = fixture.get("api", {}).get("name", "api")
    if path_mode == "cpi":
        path = "/http" + sender_path(api_name)
    else:
        path = req.get("path") or "/"
    url = base_url.rstrip("/") + path
    headers = _clean_headers(req.get("headers"), extra_headers)
    fmt = req.get("body_format")
    body = req.get("body")
    kwargs = {}
    sidecar = req.get("body_file")
    if sidecar:
        kwargs["data"] = (Path(fixture["__dir__"]) / sidecar).read_bytes()
    elif body is None or fmt == "none":
        pass
    elif fmt == "json":
        kwargs["json"] = body if not isinstance(body, str) else json.loads(body)
    elif fmt == "form":
        kwargs["data"] = urlencode(body) if isinstance(body, dict) else body
    elif fmt == "binary":
        kwargs["data"] = base64.b64decode(body) if isinstance(body, str) else body
    else:
        kwargs["data"] = body if isinstance(body, str) else str(body)
    return req.get("method", "GET"), url, headers, kwargs


def _remove_path(obj, dotted):
    parts = dotted.split(".")
    cur = obj
    for p in parts[:-1]:
        if not isinstance(cur, dict):
            return
        cur = cur.get(p)
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def compare_json(expected, actual, ignore_paths=None):
    try:
        actual_obj = json.loads(actual) if isinstance(actual, str) else actual
    except (TypeError, ValueError):
        return False
    e = json.loads(json.dumps(expected))
    a = json.loads(json.dumps(actual_obj))
    for p in ignore_paths or []:
        _remove_path(e, p)
        _remove_path(a, p)
    return e == a


def _xml_tree(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    root = ET.fromstring(value)
    for el in root.iter():
        if el.text and not el.text.strip():
            el.text = None
        if el.tail and not el.tail.strip():
            el.tail = None
    return root


def _local(tag):
    return tag.split("}", 1)[-1]


def _elem_equal(a, b):
    if _local(a.tag) != _local(b.tag):
        return False
    if (a.text or "") != (b.text or ""):
        return False
    if {_local(k): v for k, v in a.attrib.items()} != {_local(k): v for k, v in b.attrib.items()}:
        return False
    ca, cb = list(a), list(b)
    return len(ca) == len(cb) and all(_elem_equal(x, y) for x, y in zip(ca, cb))


def compare_xml(expected, actual):
    try:
        return _elem_equal(_xml_tree(expected), _xml_tree(actual))
    except ET.ParseError:
        return False


def compare_body(expected_fmt, expected_body, actual_bytes, ignore_paths=None):
    if expected_body is None:
        return not actual_bytes
    fmt = expected_fmt or "text"
    if fmt == "binary":
        exp = base64.b64decode(expected_body) if isinstance(expected_body, str) else expected_body
        return exp == actual_bytes
    if fmt == "json":
        return compare_json(expected_body, actual_bytes.decode("utf-8", errors="replace"), ignore_paths)
    if fmt == "xml":
        return compare_xml(expected_body, actual_bytes)
    return expected_body.strip() == actual_bytes.decode("utf-8", errors="replace").strip()


def run_fixture(fixture_path, base_url, path_mode, extra_headers, ignore_paths, timeout):
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["__dir__"] = str(fixture_path.parent)
    method, url, headers, kwargs = build_request(fixture, base_url, path_mode, extra_headers)
    resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    expected = fixture.get("expected_response") or {}
    exp_status = expected.get("status")
    status_ok = exp_status is None or resp.status_code == exp_status
    body_ok = compare_body(expected.get("body_format"), expected.get("body"),
                           resp.content, ignore_paths)
    diff = ""
    if not body_ok:
        diff = f"expected={json.dumps(expected.get('body'))[:250]} actual={resp.text[:250]}"
    elif not status_ok:
        diff = f"status expected={exp_status} actual={resp.status_code}"
    return {
        "api": fixture.get("api", {}).get("name"),
        "fixture": fixture_path.name,
        "status_expected": exp_status,
        "status_actual": resp.status_code,
        "status_match": bool(status_ok),
        "body_match": bool(body_ok),
        "diff": diff[:500],
        "passed": bool(status_ok and body_ok),
    }


def verify(fixtures_dir, base_url, names=None, path_mode="wso2", extra_headers=None,
           ignore_paths=None, concurrency=4, timeout=60, out_dir="."):
    jobs = [(api, f) for api, f in iter_fixtures(fixtures_dir, names)]
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = {pool.submit(run_fixture, f, base_url, path_mode, extra_headers,
                            ignore_paths, timeout): (api, f) for api, f in jobs}
        for fut in futs:
            try:
                results.append(fut.result())
            except Exception as e:
                api, f = futs[fut]
                results.append({"api": api, "fixture": f.name, "status_expected": None,
                                "status_actual": None, "status_match": False,
                                "body_match": False, "diff": str(e)[:500], "passed": False})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verify-report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["| api | fixture | status expected | status actual | body match | diff |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['api']} | {r['fixture']} | {r['status_expected']} | "
                     f"{r['status_actual']} | {r['body_match']} | {r['diff'][:100]} |")
    (out / "verify-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = [r for r in results if not r["passed"]]
    print(f"verified={len(results)} failed={len(failed)}")
    return results
