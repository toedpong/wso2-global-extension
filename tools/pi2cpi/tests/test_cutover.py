import json
from types import SimpleNamespace

from tools.pi2cpi.cutover import apply, load_state, rollback


class FakeClient:
    def __init__(self, revisions=0):
        self.config = SimpleNamespace(gateway_env="Default", vhost=None)
        self.calls = []
        self.dto = {"id": "a1", "endpointConfig": {
            "endpoint_type": "http",
            "production_endpoints": {"url": "https://sappi/PI"},
            "sandbox_endpoints": {"url": "https://sand/PI"}}}
        self.revisions = [{"id": f"r{i}"} for i in range(revisions)]
        self.next_rev = len(self.revisions)

    def get_api(self, api_id):
        self.calls.append(("get", api_id))
        return json.loads(json.dumps(self.dto))

    def update_api(self, api_id, dto):
        self.calls.append(("put", api_id, dto))
        self.dto = dto
        return dto

    def list_revisions(self, api_id):
        return list(self.revisions)

    def list_deployments(self, api_id):
        return []

    def delete_revision(self, api_id, rev_id):
        self.calls.append(("del_rev", rev_id))
        self.revisions = [r for r in self.revisions if r["id"] != rev_id]

    def create_revision(self, api_id, description):
        self.calls.append(("create_rev", description))
        rev = {"id": f"r{self.next_rev}"}
        self.next_rev += 1
        self.revisions.append(rev)
        return rev

    def deploy_revision(self, api_id, rev_id, env, vhost, **kw):
        self.calls.append(("deploy", rev_id, env))


def _change(url="https://cpi.it/http/OR_X"):
    return [{"api": {"id": "a1", "name": "OR_X", "version": "1.0"},
             "from_url": "https://sappi/PI", "to_url": url}]


def test_dry_run_no_put(tmp_path):
    c = FakeClient()
    apply(c, _change(), tmp_path / "s.json", dry_run=True)
    assert not any(call[0] == "put" for call in c.calls)


def test_apply_updates_production_only(tmp_path):
    c = FakeClient()
    state_path = tmp_path / "s.json"
    apply(c, _change(), state_path)
    put = next(call for call in c.calls if call[0] == "put")
    cfg = put[2]["endpointConfig"]
    assert cfg["production_endpoints"]["url"] == "https://cpi.it/http/OR_X"
    assert cfg["sandbox_endpoints"]["url"] == "https://sand/PI"
    state = load_state(state_path)
    assert state["a1"]["original_endpointConfig"]["production_endpoints"]["url"] == "https://sappi/PI"
    assert any(call[0] == "create_rev" for call in c.calls)
    assert any(call[0] == "deploy" for call in c.calls)


def test_apply_include_sandbox(tmp_path):
    c = FakeClient()
    apply(c, _change(), tmp_path / "s.json", include_sandbox=True)
    put = next(call for call in c.calls if call[0] == "put")
    cfg = put[2]["endpointConfig"]
    assert cfg["sandbox_endpoints"]["url"] == "https://cpi.it/http/OR_X"


def test_revision_cap(tmp_path):
    c = FakeClient(revisions=5)
    apply(c, _change(), tmp_path / "s.json")
    assert ("del_rev", "r0") in c.calls


def test_rollback(tmp_path):
    c = FakeClient()
    state_path = tmp_path / "s.json"
    apply(c, _change(), state_path)
    rollback(c, state_path)
    state = load_state(state_path)
    assert state == {}
    puts = [call for call in c.calls if call[0] == "put"]
    assert puts[-1][2]["endpointConfig"]["production_endpoints"]["url"] == "https://sappi/PI"
