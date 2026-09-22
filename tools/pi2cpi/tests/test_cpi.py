import io
import re
import xml.etree.ElementTree as ET
import zipfile

from tools.pi2cpi.cpi import iflow_id, render_iflow, sender_path

REC = {"name": "OR_HR_ZHRHRI001", "version": "1.0.0",
       "production_url": "https://sappo.corp:50000/XISOAPAdapter/MessageServlet",
       "pi": {"adapter": "soap", "host": "sappo.corp:50000", "interface": "SI_ZHRHRI001",
              "channel": "CC_SOAP_ZHRHRI001"}}


def _unzip(b):
    return zipfile.ZipFile(io.BytesIO(b))


def test_zip_layout():
    z = _unzip(render_iflow(REC))
    names = set(z.namelist())
    assert names == {
        "META-INF/MANIFEST.MF",
        "src/main/resources/scenarioflows/integrationflow/OR_HR_ZHRHRI001.iflw",
        "src/main/resources/parameters.prop",
        "src/main/resources/parameters.propdef",
        "metainfo.prop",
    }


def test_iflw_placeholders():
    z = _unzip(render_iflow(REC))
    iflw = z.read("src/main/resources/scenarioflows/integrationflow/OR_HR_ZHRHRI001.iflw").decode()
    for key in ["DESCRIPTION", "RECEIVER_NAME", "RECEIVER_ADAPTER_NAME",
                "RECEIVER_ADAPTER_PROPERTIES", "SENDER_URL_PATH",
                "PI_INTERFACE", "API_NAME", "IFLOW_NAME", "IFLOW_ID"]:
        assert "{{" + key + "}}" not in iflw
    assert "{{Receiver_Address}}" in iflw
    ET.fromstring(iflw)


def test_id_sanitization():
    assert iflow_id("OR_HR_ZHRHRI001") == "OR_HR_ZHRHRI001"
    assert iflow_id("1abc-x") == "_1abc_x"


def test_sender_path():
    assert sender_path("My API") == "/My_API"
    assert sender_path("x", "/custom") == "/custom"


def test_component_type():
    z = _unzip(render_iflow(REC, receiver="soap"))
    iflw = z.read("src/main/resources/scenarioflows/integrationflow/OR_HR_ZHRHRI001.iflw").decode()
    assert "<key>ComponentType</key><value>SOAP</value>" in iflw
    z = _unzip(render_iflow(REC, receiver="rfc"))
    iflw = z.read("src/main/resources/scenarioflows/integrationflow/OR_HR_ZHRHRI001.iflw").decode()
    assert "<key>ComponentType</key><value>RFC</value>" in iflw
    assert "{{Receiver_RFC_Destination}}" in iflw


def test_manifest():
    z = _unzip(render_iflow(REC))
    m = z.read("META-INF/MANIFEST.MF").decode()
    assert "Bundle-SymbolicName: OR_HR_ZHRHRI001; singleton:=true" in m
    assert "{{" not in m
