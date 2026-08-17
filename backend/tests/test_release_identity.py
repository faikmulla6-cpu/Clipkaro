from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.core.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_backend_frontend_and_live_qa_report_target_same_release() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    qa_report = (ROOT / "docs" / "QA_REPORT.md").read_text(encoding="utf-8")

    assert APP_VERSION == "7.8.0"
    assert package["version"] == APP_VERSION
    assert qa_report.startswith(f"# QA report — Launch Edition {APP_VERSION}")
    assert "# QA report — Launch Edition 2.0.1" not in qa_report
    assert "Status: PENDING FRESH RUN" in qa_report or "Status: CERTIFIED" in qa_report


def test_legacy_qa_report_is_archived_and_cannot_pose_as_current() -> None:
    archive = ROOT / "docs" / "archive" / "QA_REPORT_2.0.1.md"
    text = archive.read_text(encoding="utf-8")
    assert text.startswith("# QA report — Launch Edition 2.0.1")
    assert "Historical archive" in text


def test_launch_qa_evidence_generator_compiles_and_rejects_bad_check_syntax() -> None:
    script = ROOT / "scripts" / "generate_launch_qa_report.py"
    source = script.read_text(encoding="utf-8")
    compile(source, str(script), "exec")

    spec = importlib.util.spec_from_file_location("launch_qa_report", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._parse_checks(["backend_tests=success", "frontend_build=failure"]) == {
        "backend_tests": "success",
        "frontend_build": "failure",
    }
    try:
        module._parse_checks(["missing-separator"])
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed launch-QA check syntax must fail closed")
