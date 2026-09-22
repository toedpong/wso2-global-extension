import os
from dataclasses import dataclass


@dataclass
class Wso2Config:
    base_url: str
    username: str
    password: str
    verify_tls: bool = True
    gateway_env: str = "Default"
    vhost: str | None = None


@dataclass
class CpiConfig:
    base_url: str
    token_url: str
    client_id: str
    client_secret: str
    runtime_url: str | None = None


def _missing(names):
    return [n for n in names if not os.environ.get(n)]


def load_wso2() -> Wso2Config:
    req = ["WSO2_BASE_URL", "WSO2_USERNAME", "WSO2_PASSWORD"]
    missing = _missing(req)
    if missing:
        raise SystemExit(f"missing env vars: {', '.join(missing)}")
    return Wso2Config(
        base_url=os.environ["WSO2_BASE_URL"].rstrip("/"),
        username=os.environ["WSO2_USERNAME"],
        password=os.environ["WSO2_PASSWORD"],
        verify_tls=os.environ.get("WSO2_VERIFY_TLS", "true").lower() not in ("0", "false", "no"),
        gateway_env=os.environ.get("WSO2_GATEWAY_ENV", "Default"),
        vhost=os.environ.get("WSO2_VHOST") or None,
    )


def load_cpi(require=True) -> CpiConfig | None:
    req = ["CPI_BASE_URL", "CPI_TOKEN_URL", "CPI_CLIENT_ID", "CPI_CLIENT_SECRET"]
    missing = _missing(req)
    if missing:
        if require:
            raise SystemExit(f"missing env vars: {', '.join(missing)}")
        return CpiConfig("", "", "", "", os.environ.get("CPI_RUNTIME_URL") or None)
    return CpiConfig(
        base_url=os.environ["CPI_BASE_URL"].rstrip("/"),
        token_url=os.environ["CPI_TOKEN_URL"],
        client_id=os.environ["CPI_CLIENT_ID"],
        client_secret=os.environ["CPI_CLIENT_SECRET"],
        runtime_url=(os.environ.get("CPI_RUNTIME_URL") or "").rstrip("/") or None,
    )
