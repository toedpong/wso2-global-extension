import os
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST_PATTERN = r"(?i)sap-?(pi|po|xi)|(^|[^a-z])(pi|po|xi)([^a-z]|$)"


def _host_pattern():
    return re.compile(os.environ.get("PI_HOST_PATTERN", DEFAULT_HOST_PATTERN))


@dataclass
class PiEndpoint:
    adapter: str
    host: str
    path: str
    party: str = ""
    service: str = ""
    channel: str = ""
    receiver_party: str = ""
    receiver_service: str = ""
    interface: str = ""
    namespace: str = ""
    raw_url: str = ""

    def to_dict(self):
        return asdict(self)


def classify_endpoint(url):
    if not url:
        return None
    p = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(p.query).items()}
    host = p.netloc
    base = dict(host=host, path=p.path, raw_url=url,
                receiver_party=q.get("receiverParty", ""),
                receiver_service=q.get("receiverService", ""),
                interface=q.get("interface", ""),
                namespace=q.get("interfaceNamespace", "") or q.get("namespace", ""))
    if "/XISOAPAdapter/MessageServlet" in p.path:
        channel = q.get("channel", "")
        parts = channel.split(":")
        party, service, ch = (parts + ["", "", ""])[:3]
        return PiEndpoint(adapter="soap", party=party, service=service, channel=ch, **base)
    if p.path.startswith("/RESTAdapter/"):
        return PiEndpoint(adapter="rest", channel=p.path[len("/RESTAdapter/"):], **base)
    if "/sap/xi/adapter_plain" in p.path:
        return PiEndpoint(adapter="plain", **base)
    if "/sap/xi/engine" in p.path:
        return PiEndpoint(adapter="engine", **base)
    if _host_pattern().search(host):
        return PiEndpoint(adapter="unknown", **base)
    return None


def _first_url(entry):
    if not entry:
        return None, []
    if isinstance(entry, str):
        return entry, []
    if isinstance(entry, list):
        urls = [e.get("url") if isinstance(e, dict) else e for e in entry]
        urls = [u for u in urls if u]
        return (urls[0] if urls else None), urls[1:]
    if isinstance(entry, dict):
        return entry.get("url"), []
    return None, []


def extract_endpoints(endpoint_config):
    result = {"production": None, "sandbox": None, "endpoint_type": None, "additional": []}
    if not isinstance(endpoint_config, dict):
        return result
    etype = endpoint_config.get("endpoint_type")
    result["endpoint_type"] = etype
    if etype not in ("http", "address", "load_balance", "failover"):
        return result
    prod, prod_extra = _first_url(endpoint_config.get("production_endpoints"))
    sand, sand_extra = _first_url(endpoint_config.get("sandbox_endpoints"))
    result["production"] = prod
    result["sandbox"] = sand
    result["additional"] = prod_extra + sand_extra
    return result
