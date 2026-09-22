import base64
import io
import re
import zipfile
from pathlib import Path

import requests

TEMPLATES = Path(__file__).parent / "templates"

RECEIVER_PARAMS = {
    "soap": ["Receiver_Address", "Receiver_ProxyType", "Receiver_LocationID", "Receiver_Credential"],
    "rfc": ["Receiver_RFC_Destination"],
}

IFLOW_KEYS = ["DESCRIPTION", "RECEIVER_NAME", "RECEIVER_ADAPTER_NAME",
              "RECEIVER_ADAPTER_PROPERTIES", "SENDER_URL_PATH",
              "PI_INTERFACE", "API_NAME", "IFLOW_NAME", "IFLOW_ID"]


def iflow_id(api_name):
    i = re.sub(r"[^A-Za-z0-9_]", "_", api_name or "iflow")
    if not i[0].isalpha():
        i = "_" + i
    return i


def sender_path(api_name, override=None):
    if override:
        return override if override.startswith("/") else f"/{override}"
    return "/" + re.sub(r"[^A-Za-z0-9_-]", "_", api_name or "api")


def render_iflow(api_record, receiver="soap", cpi_path=None):
    name = api_record["name"]
    iid = iflow_id(name)
    pi = api_record.get("pi") or {}
    interface = pi.get("interface") or pi.get("channel") or "unknown"
    desc = (f"Migrated from SAP PI interface {interface} "
            f"behind WSO2 API {name} v{api_record.get('version')}")
    if receiver == "rfc":
        receiver_name, adapter_name = "SAP ECC", "RFC"
    else:
        receiver_name, adapter_name = (pi.get("host") or "SAP PI/PO"), "SOAP"
    props = (TEMPLATES / f"receiver_{receiver}.xml").read_text(encoding="utf-8").rstrip("\n")
    iflw = (TEMPLATES / "iflow.iflw.xml").read_text(encoding="utf-8")
    values = {
        "DESCRIPTION": desc,
        "RECEIVER_NAME": receiver_name,
        "RECEIVER_ADAPTER_NAME": adapter_name,
        "RECEIVER_ADAPTER_PROPERTIES": props,
        "SENDER_URL_PATH": sender_path(name, cpi_path),
        "PI_INTERFACE": interface,
        "API_NAME": name,
        "IFLOW_NAME": name,
        "IFLOW_ID": iid,
    }
    iflw = iflw.replace("{{RECEIVER_ADAPTER_PROPERTIES}}", props)
    for k, v in values.items():
        iflw = iflw.replace("{{" + k + "}}", v)
    manifest = (TEMPLATES / "MANIFEST.MF").read_text(encoding="utf-8")
    manifest = manifest.replace("{{IFLOW_NAME}}", name).replace("{{IFLOW_ID}}", iid)
    params = {p: "" for p in RECEIVER_PARAMS[receiver]}
    if "Receiver_Address" in params:
        params["Receiver_Address"] = api_record.get("production_url") or ""
        params["Receiver_ProxyType"] = "Internet"
    prop = "".join(f"{k}={v}\n" for k, v in params.items())
    pdefs = "".join(f'<parameter><name>{k}</name><type>xsd:string</type></parameter>'
                    for k in params)
    propdef = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
               f"<parameters><param_references/>{pdefs}</parameters>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/MANIFEST.MF", manifest)
        z.writestr(f"src/main/resources/scenarioflows/integrationflow/{iid}.iflw", iflw)
        z.writestr("src/main/resources/parameters.prop", prop)
        z.writestr("src/main/resources/parameters.propdef", propdef)
        z.writestr("metainfo.prop", f"#Store metainfo properties\ndescription={desc}\n")
    return buf.getvalue()


class CpiClient:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self._token = None
        self._csrf = None

    def _check(self, resp):
        if resp.status_code >= 400:
            raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}")
        return resp

    def authenticate(self):
        cfg = self.config
        r = self.session.post(cfg.token_url,
                              data={"grant_type": "client_credentials"},
                              auth=(cfg.client_id, cfg.client_secret))
        self._check(r)
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self, extra=None):
        h = {"Authorization": f"Bearer {self._token}"}
        if self._csrf:
            h["X-CSRF-Token"] = self._csrf
        h.update(extra or {})
        return h

    def fetch_csrf(self):
        r = self.session.get(f"{self.config.base_url}/api/v1/",
                             headers={**self._headers(), "X-CSRF-Token": "Fetch"})
        self._csrf = r.headers.get("X-CSRF-Token")
        return self._csrf

    def _post(self, url, **kw):
        kw.setdefault("headers", {})
        kw["headers"] = {**self._headers(kw["headers"])}
        return self._check(self.session.post(url, **kw))

    def ensure_package(self, package_id, name):
        base = self.config.base_url
        r = self.session.get(f"{base}/api/v1/IntegrationPackages('{package_id}')",
                             headers=self._headers({"Accept": "application/json"}))
        if r.status_code == 404:
            self._post(f"{base}/api/v1/IntegrationPackages",
                       json={"Id": package_id, "Name": name, "ShortText": name},
                       headers={"Accept": "application/json", "Content-Type": "application/json"})
            return {"Id": package_id, "Name": name}
        self._check(r)
        return r.json().get("d", r.json())

    def upload_iflow(self, package_id, iid, name, zip_bytes):
        body = {"Name": name, "Id": iid, "PackageId": package_id,
                "ArtifactContent": base64.b64encode(zip_bytes).decode()}
        return self._post(f"{self.config.base_url}/api/v1/IntegrationDesigntimeArtifacts",
                          json=body,
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/json"}).json()

    def deploy_iflow(self, iid):
        return self._post(f"{self.config.base_url}/api/v1/DeployIntegrationDesigntimeArtifact"
                          f"?Id='{iid}'&Version='active'").text
