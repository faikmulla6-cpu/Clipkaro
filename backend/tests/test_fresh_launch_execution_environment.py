from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_fresh_launch_execution_environment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("clipkaro_fresh_launch_env", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_github_hosted_disk_policy_fits_ephemeral_runner_without_weakening_heavy_qa() -> None:
    module = _load_module()
    assert module._disk_policy(True) == (10.0, 15.0)
    assert module._disk_policy(False) == (25.0, 40.0)
    assert module.GITHUB_HOSTED_MIN_DISK_GIB < module.SELF_HOSTED_MIN_DISK_GIB


def test_hosted_fresh_launch_does_not_require_pytorch_registry() -> None:
    module = _load_module()
    hosted = module._required_network_hosts(True)
    heavy = module._required_network_hosts(False)
    assert "download.pytorch.org" not in hosted
    assert "download.pytorch.org" in heavy
    assert {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org", "registry-1.docker.io"}.issubset(hosted)
