from types import SimpleNamespace

from tools.pi2cpi.wso2 import Wso2Client


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = str(data)
        self.request = SimpleNamespace(method="GET", url="x")

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def request(self, method, url, **kw):
        page = self.pages[self.calls]
        self.calls += 1
        return FakeResp(page)


def test_list_apis_pagination():
    cfg = SimpleNamespace(base_url="https://apim", verify_tls=False)
    pages = [
        {"list": [{"id": "1"}], "pagination": {"limit": 100, "next": "/apis?offset=100"}},
        {"list": [{"id": "2"}], "pagination": {"limit": 100, "next": None}},
    ]
    client = Wso2Client(cfg, session=FakeSession(pages))
    apis = client.list_apis()
    assert [a["id"] for a in apis] == ["1", "2"]
