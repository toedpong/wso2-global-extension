import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from .cpi import sender_path
from .pi import extract_endpoints

MAX_REVISIONS = 5


def load_state(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")


def cpi_url(cpi_runtime_url, api_name, path_override=None):
    return f"{cpi_runtime_url.rstrip('/')}/http{sender_path(api_name, path_override)}"


def plan(client, records, cpi_runtime_url, path_fn=None):
    changes = []
    for rec in records:
        override = path_fn(rec) if path_fn else None
        changes.append({
            "api": rec,
            "from_url": rec.get("production_url"),
            "to_url": cpi_url(cpi_runtime_url, rec["name"], override),
        })
    return changes


def _set_endpoint_urls(dto, key, new_url):
    cfg = dto.get("endpointConfig") or {}
    ep = cfg.get(key)
    if isinstance(ep, dict):
        ep["url"] = new_url
    elif isinstance(ep, list):
        for item in ep:
            if isinstance(item, dict):
                item["url"] = new_url
    elif isinstance(ep, str):
        cfg[key] = new_url


def _make_room_for_revision(client, api_id):
    revs = client.list_revisions(api_id)
    if len(revs) < MAX_REVISIONS:
        return
    deployed = {d.get("revisionUuid") for d in client.list_deployments(api_id)}
    candidates = [r for r in revs if r.get("id") not in deployed]
    if not candidates:
        return
    client.delete_revision(api_id, candidates[0]["id"])


def apply(client, changes, state_path, dry_run=False, include_sandbox=False):
    state = load_state(state_path)
    if dry_run:
        for c in changes:
            print(f"[dry-run] {c['api']['name']}: {c['from_url']} -> {c['to_url']}")
        return state
    for c in changes:
        api_id, name = c["api"]["id"], c["api"]["name"]
        dto = client.get_api(api_id)
        original = copy.deepcopy(dto.get("endpointConfig"))
        new_cfg = copy.deepcopy(original)
        new_dto = dict(dto, endpointConfig=new_cfg)
        _set_endpoint_urls(new_dto, "production_endpoints", c["to_url"])
        if include_sandbox:
            _set_endpoint_urls(new_dto, "sandbox_endpoints", c["to_url"])
        client.update_api(api_id, new_dto)
        _make_room_for_revision(client, api_id)
        rev = client.create_revision(api_id, f"pi2cpi cutover -> {c['to_url']}")
        client.deploy_revision(api_id, rev["id"], client.config.gateway_env,
                               client.config.vhost)
        state[api_id] = {
            "name": name,
            "version": c["api"].get("version"),
            "original_endpointConfig": original,
            "new_endpointConfig": new_cfg,
            "revision_id": rev["id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        save_state(state_path, state)
        print(f"{name}: {c['from_url']} -> {c['to_url']} (revision {rev['id']})")
    return state


def rollback(client, state_path, names=None):
    state = load_state(state_path)
    wanted = set(names) if names else None
    for api_id in list(state):
        entry = state[api_id]
        if wanted and entry["name"] not in wanted:
            continue
        dto = client.get_api(api_id)
        dto["endpointConfig"] = copy.deepcopy(entry["original_endpointConfig"])
        client.update_api(api_id, dto)
        _make_room_for_revision(client, api_id)
        rev = client.create_revision(api_id, "pi2cpi rollback")
        client.deploy_revision(api_id, rev["id"], client.config.gateway_env,
                               client.config.vhost)
        del state[api_id]
        save_state(state_path, state)
        print(f"{entry['name']}: rolled back (revision {rev['id']})")
    return state
