from tools.pi2cpi.pi import classify_endpoint, extract_endpoints

SOAP_URL = ("https://sappo.corp:50000/XISOAPAdapter/MessageServlet"
            "?channel=:BS_WSO2:CC_SOAP_ZHRHRI001&interface=SI_ZHRHRI001"
            "&interfaceNamespace=urn:pttor:hr")


def test_soap_adapter():
    ep = classify_endpoint(SOAP_URL)
    assert ep.adapter == "soap"
    assert ep.host == "sappo.corp:50000"
    assert ep.party == ""
    assert ep.service == "BS_WSO2"
    assert ep.channel == "CC_SOAP_ZHRHRI001"
    assert ep.interface == "SI_ZHRHRI001"
    assert ep.namespace == "urn:pttor:hr"


def test_rest_adapter():
    ep = classify_endpoint("https://sappi.corp:443/RESTAdapter/HR/EmployeeSvc")
    assert ep.adapter == "rest"
    assert ep.channel == "HR/EmployeeSvc"


def test_adapter_plain():
    ep = classify_endpoint(
        "http://sappi.corp:8000/sap/xi/adapter_plain?namespace=urn:x&interface=SI_A&service=BS_X")
    assert ep.adapter == "plain"
    assert ep.namespace == "urn:x"
    assert ep.interface == "SI_A"


def test_engine():
    ep = classify_endpoint("http://sappi.corp:8000/sap/xi/engine?type=entry")
    assert ep.adapter == "engine"


def test_non_pi():
    assert classify_endpoint("https://api.example.com/v1") is None
    assert classify_endpoint("") is None
    assert classify_endpoint(None) is None


def test_host_pattern_fallback():
    ep = classify_endpoint("https://xi-prod.corp/some/path")
    assert ep.adapter == "unknown"
    assert ep.host == "xi-prod.corp"
    ep = classify_endpoint("https://sappid.corp:50000/foo")
    assert ep.adapter == "unknown"


def test_extract_single():
    ep = extract_endpoints({"endpoint_type": "http",
                            "production_endpoints": {"url": SOAP_URL},
                            "sandbox_endpoints": {"url": "https://box/v1"}})
    assert ep["production"] == SOAP_URL
    assert ep["sandbox"] == "https://box/v1"
    assert ep["additional"] == []


def test_extract_load_balance():
    ep = extract_endpoints({"endpoint_type": "load_balance",
                            "production_endpoints": [{"url": "a"}, {"url": "b"}]})
    assert ep["production"] == "a"
    assert ep["additional"] == ["b"]


def test_extract_missing_and_unknown():
    ep = extract_endpoints({"endpoint_type": "http"})
    assert ep["production"] is None
    ep = extract_endpoints({"endpoint_type": "prototyped",
                            "production_endpoints": {"url": "a"}})
    assert ep["production"] is None
    ep = extract_endpoints(None)
    assert ep["production"] is None
