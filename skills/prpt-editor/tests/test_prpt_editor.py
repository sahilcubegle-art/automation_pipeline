import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
EDITOR = ROOT / "prpt_editor.py"
MIME = b"application/vnd.pentaho.reporting.classic"
NS = "http://reporting.pentaho.org/namespaces/engine/classic/bundle/layout/1.0"


def fixture(path: Path) -> Path:
    layout = f'''<?xml version="1.0"?><layout xmlns="{NS}" name="Fixture"><message><value>Net income</value></message><message><value>$([total] * 0.18)</value></message><band name="VAT"><style-expression formula="=IF([taxable];&quot;true&quot;;&quot;false&quot;)"/></band></layout>'''.encode()
    data = b'''<?xml version="1.0"?><data-definition xmlns="http://reporting.pentaho.org/namespaces/engine/classic/bundle/data/1.0"><parameter-definition/><expression name="total" class="ItemSumFunction"><properties><property name="field">Amount</property></properties></expression></data-definition>'''
    untouched = b"binary asset must not change"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", MIME, compress_type=zipfile.ZIP_STORED)
        z.writestr("layout.xml", layout)
        z.writestr("datadefinition.xml", data)
        z.writestr("resources/asset.bin", untouched)
    return path


def run(*args: str, check=True):
    completed = subprocess.run([sys.executable, str(EDITOR), *args], text=True, capture_output=True)
    if check:
        assert completed.returncode == 0, completed.stderr
    return completed, json.loads(completed.stdout) if completed.stdout else json.loads(completed.stderr)


def test_inspect_and_find_are_compact(tmp_path):
    report = fixture(tmp_path / "fixture.prpt")
    _, info = run("inspect", str(report))
    assert info["members"] == 4
    assert info["named"]["variable"] == ["total"]
    _, found = run("find", str(report), "VAT")
    assert found["matches"][0]["identity"]["name"] == "VAT"
    _, expressions = run("find", str(report), "--expression", "total")
    assert len(expressions["matches"]) == 1
    assert expressions["matches"][0]["expression"] == "$([total] * 0.18)"


def test_targeted_expression_edit_preserves_members_and_backup(tmp_path):
    report = fixture(tmp_path / "fixture.prpt")
    before = zipfile.ZipFile(report).read("resources/asset.bin")
    _, found = run("find", str(report), "--expression", "total")
    target = found["matches"][0]["selector"]
    _, change = run("modify-expression", str(report), "--target", target, "--expect", "$([total] * 0.18)", "--expression", "$([total] * 0.20)")
    assert Path(change["backup"]).exists()
    with zipfile.ZipFile(report) as bundle:
        assert bundle.read("resources/asset.bin") == before
        assert b"0.20" in bundle.read("layout.xml")
    _, valid = run("validate", str(report))
    assert valid["valid"] is True


def test_add_plain_parameter_and_reject_duplicate(tmp_path):
    report = fixture(tmp_path / "fixture.prpt")
    _, result = run("add-parameter", str(report), "--name", "VAT_RATE", "--type", "java.lang.Double", "--default", "0.18", "--label", "VAT rate")
    assert result["modified"][0]["parameter"] == "VAT_RATE"
    with zipfile.ZipFile(report) as bundle:
        xml = bundle.read("datadefinition.xml")
        assert b'<plain-parameter name="VAT_RATE" mandatory="false" type="java.lang.Double" default-value="0.18">' in xml
    Path(result["backup"]).unlink()
    completed, error = run("add-parameter", str(report), "--name", "VAT_RATE", check=False)
    assert completed.returncode == 2
    assert "already exists" in error["error"]


def test_missing_or_stale_target_fails_without_mutation(tmp_path):
    report = fixture(tmp_path / "fixture.prpt")
    original = hashlib.sha256(report.read_bytes()).hexdigest()
    completed, error = run("modify-expression", str(report), "--target", "layout.xml#999", "--expression", "x", check=False)
    assert completed.returncode == 2
    assert "Target not found" in error["error"]
    assert hashlib.sha256(report.read_bytes()).hexdigest() == original
    _, found = run("find", str(report), "--expression", "total")
    completed, error = run("modify-expression", str(report), "--target", found["matches"][0]["selector"], "--expect", "wrong", "--expression", "x", check=False)
    assert completed.returncode == 2
    assert "Expected expression" in error["error"]


def test_invalid_bundle_fails_validation(tmp_path):
    bad = tmp_path / "bad.prpt"
    bad.write_bytes(b"not a zip")
    completed, result = run("validate", str(bad), check=False)
    assert completed.returncode == 1
    assert result["valid"] is False
