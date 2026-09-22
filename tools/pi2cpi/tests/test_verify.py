import base64
import json

from tools.pi2cpi.verify import (build_request, compare_body, compare_json,
                                 compare_xml)


def test_json_equal_with_ignore():
    assert compare_json({"a": 1, "b": {"c": 2}}, {"a": 1, "b": {"c": 99}},
                        ["b.c"])


def test_json_differs():
    assert not compare_json({"a": 1}, {"a": 2})


def test_xml_equal_ws_and_prefix():
    e = "<root><a x='1'> hi </a></root>"
    a = "<p:root xmlns:p='urn:u'>\n  <p:a x='1'> hi </p:a>\n</p:root>"
    assert compare_xml(e, a)


def test_xml_differs():
    assert not compare_xml("<r><a>1</a></r>", "<r><a>2</a></r>")


def test_status_and_body():
    assert compare_body("text", "ok ", b" ok")
    assert not compare_body("text", "ok", b"no")
    assert compare_body(None, None, b"")
    assert compare_body("binary", base64.b64encode(b"ab").decode(), b"ab")


def _fixture(tmp_path):
    (tmp_path / "m1.request.xml").write_bytes(b"<req/>")
    fx = {
        "api": {"name": "OR_X"},
        "request": {
            "method": "POST", "path": "/t/1", "url": "http://w/t/1",
            "headers": {"Connection": "close", "X-Mask": "***MASKED***",
                        "Host": "w", "X-Keep": "1"},
            "body_format": "xml", "body": "<req/>", "body_file": "m1.request.xml",
        },
        "expected_response": {"status": 200},
    }
    return fx


def test_build_request_drops_headers_and_uses_body_file(tmp_path):
    fx = _fixture(tmp_path)
    fx["__dir__"] = str(tmp_path)
    method, url, headers, kw = build_request(fx, "https://gw", "wso2",
                                           ["Authorization: Bearer t"])
    assert method == "POST" and url == "https://gw/t/1"
    assert "Connection" not in headers and "Host" not in headers
    assert "X-Mask" not in headers
    assert headers["X-Keep"] == "1"
    assert headers["Authorization"] == "Bearer t"
    assert kw["data"] == b"<req/>"


def test_build_request_cpi_path(tmp_path):
    fx = _fixture(tmp_path)
    fx["__dir__"] = str(tmp_path)
    _, url, _, _ = build_request(fx, "https://cpi.it", "cpi")
    assert url == "https://cpi.it/http/OR_X"
