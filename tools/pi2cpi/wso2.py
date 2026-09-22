import requests

DEFAULT_SCOPES = "apim:api_view apim:api_create apim:api_publish apim:api_import_export"


class Wso2Client:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self._token = None

    def _check(self, resp):
        if resp.status_code >= 400:
            raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}")
        return resp

    def _request(self, method, url, **kw):
        kw.setdefault("verify", self.config.verify_tls)
        kw.setdefault("headers", {})
        if self._token:
            kw["headers"]["Authorization"] = f"Bearer {self._token}"
        return self._check(self.session.request(method, url, **kw))

    def authenticate(self, scopes=DEFAULT_SCOPES):
        cfg = self.config
        r = self.session.post(
            f"{cfg.base_url}/client-registration/v0.17/register",
            json={"callbackUrl": "www.google.lk", "clientName": "pi2cpi",
                  "owner": cfg.username, "grantType": "password refresh_token", "saasApp": True},
            auth=(cfg.username, cfg.password), verify=cfg.verify_tls)
        self._check(r)
        dcr = r.json()
        t = self.session.post(
            f"{cfg.base_url}/oauth2/token",
            data={"grant_type": "password", "username": cfg.username,
                  "password": cfg.password, "scope": scopes},
            auth=(dcr["clientId"], dcr["clientSecret"]), verify=cfg.verify_tls)
        self._check(t)
        self._token = t.json()["access_token"]
        return self._token

    def _api_url(self, api_id, suffix=""):
        return f"{self.config.base_url}/api/am/publisher/v3/apis/{api_id}{suffix}"

    def list_apis(self, query=None):
        url = f"{self.config.base_url}/api/am/publisher/v3/apis"
        apis, offset = [], 0
        while True:
            params = {"limit": 100, "offset": offset}
            if query:
                params["query"] = query
            data = self._request("GET", url, params=params).json()
            apis.extend(data.get("list", []))
            nxt = (data.get("pagination") or {}).get("next")
            if not nxt:
                break
            offset += data["pagination"].get("limit", 100)
        return apis

    def get_api(self, api_id):
        return self._request("GET", self._api_url(api_id)).json()

    def get_swagger(self, api_id):
        return self._request("GET", self._api_url(api_id, "/swagger")).text

    def update_api(self, api_id, dto):
        return self._request("PUT", self._api_url(api_id), json=dto).json()

    def create_revision(self, api_id, description):
        return self._request("POST", self._api_url(api_id, "/revisions"),
                             json={"description": description}).json()

    def list_revisions(self, api_id):
        return self._request("GET", self._api_url(api_id, "/revisions")).json().get("list", [])

    def delete_revision(self, api_id, revision_id):
        return self._request("DELETE", self._api_url(api_id, f"/revisions/{revision_id}"))

    def deploy_revision(self, api_id, revision_id, env, vhost, display_on_devportal=True):
        body = [{"name": env, "vhost": vhost, "displayOnDevportal": display_on_devportal}]
        return self._request("POST", self._api_url(api_id, "/deploy-revision"),
                             params={"revisionId": revision_id}, json=body).json()

    def list_deployments(self, api_id):
        return self._request("GET", self._api_url(api_id, "/deployments")).json().get("list", [])

    def find_api_by_name(self, name, version=None):
        hits = [a for a in self.list_apis(query=f'name:"{name}"') if a.get("name") == name]
        if version:
            hits = [a for a in hits if a.get("version") == version]
        return hits
