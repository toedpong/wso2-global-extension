import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .pi import classify_endpoint, extract_endpoints

SYN_NS = "{http://ws.apache.org/ns/synapse}"


def parse_migration_list(path):
    root = ET.parse(path).getroot()
    names = []
    for el in root.iter():
        if el.tag in ("api", f"{SYN_NS}api") and el.text:
            names.append(el.text.strip())
    return names


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value or "unknown")


def api_record(client, summary, fetch_swagger=False):
    dto = client.get_api(summary["id"])
    cfg = dto.get("endpointConfig") or {}
    ep = extract_endpoints(cfg)
    pi = classify_endpoint(ep.get("production") or "") or classify_endpoint(ep.get("sandbox") or "")
    ops = [{"verb": o.get("verb"), "target": o.get("target")}
           for o in (dto.get("operations") or dto.get("uriTemplates") or [])]
    security = (cfg.get("endpoint_security") or {})
    record = {
        "id": dto.get("id") or summary["id"],
        "name": dto.get("name") or summary.get("name"),
        "version": dto.get("version") or summary.get("version"),
        "context": dto.get("context"),
        "lifeCycleStatus": dto.get("lifeCycleStatus"),
        "type": dto.get("type"),
        "production_url": ep["production"],
        "sandbox_url": ep["sandbox"],
        "endpoint_type": ep["endpoint_type"],
        "additional_urls": ep["additional"],
        "pi": pi.to_dict() if pi else None,
        "operations": ops,
        "auth_type": (security.get("production") or {}).get("type"),
        "mediation_policies": [m.get("name") for m in (dto.get("mediationPolicies") or [])],
        "wsdl_available": bool(dto.get("wsdlUrl")) or dto.get("type") == "SOAP",
        "has_swagger": False,
    }
    if fetch_swagger:
        try:
            record["swagger"] = client.get_swagger(record["id"])
            record["has_swagger"] = True
        except Exception:
            record["swagger"] = None
    return record


def build_inventory(client, names=None, only_pi=True, out_dir=".", swagger_dir=None,
                    migration_list=None):
    if migration_list:
        names = parse_migration_list(migration_list)
    summaries = client.list_apis()
    if names:
        wanted = set(names)
        summaries = [s for s in summaries if s.get("name") in wanted]
    records = []
    for s in summaries:
        rec = api_record(client, s, fetch_swagger=bool(swagger_dir))
        if swagger_dir and rec.get("swagger"):
            d = Path(swagger_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{safe_name(rec['name'])}.json").write_text(rec["swagger"], encoding="utf-8")
        if only_pi and not rec["pi"]:
            continue
        records.append(rec)
    for rec in records:
        rec.pop("swagger", None)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "inventory.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    cols = ["id", "name", "version", "context", "lifeCycleStatus", "type",
            "production_url", "sandbox_url", "endpoint_type", "adapter", "pi_host",
            "service", "channel", "interface", "namespace", "auth_type",
            "mediation_policies", "wsdl_available", "has_swagger"]
    with (out / "inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            pi = r.get("pi") or {}
            w.writerow({
                "id": r["id"], "name": r["name"], "version": r["version"],
                "context": r["context"], "lifeCycleStatus": r["lifeCycleStatus"],
                "type": r["type"], "production_url": r["production_url"],
                "sandbox_url": r["sandbox_url"], "endpoint_type": r["endpoint_type"],
                "adapter": pi.get("adapter"), "pi_host": pi.get("host"),
                "service": pi.get("service"), "channel": pi.get("channel"),
                "interface": pi.get("interface"), "namespace": pi.get("namespace"),
                "auth_type": r["auth_type"],
                "mediation_policies": ";".join(r["mediation_policies"]),
                "wsdl_available": r["wsdl_available"], "has_swagger": r["has_swagger"],
            })
    pi_recs = [r for r in records if r["pi"]]
    by_adapter = {}
    for r in pi_recs:
        a = r["pi"]["adapter"]
        by_adapter[a] = by_adapter.get(a, 0) + 1
    print(f"total={len(records)} pi={len(pi_recs)} non_pi={len(records) - len(pi_recs)} "
          f"by_adapter={by_adapter}")
    return records
