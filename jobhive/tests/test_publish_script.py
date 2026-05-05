"""Tests for the standalone publish_to_cloudflare.py script.

Verifies arg parsing, dry-run behavior, and the .env loader without ever
actually creating an R2 client.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "publish_to_cloudflare.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("publish_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_dotenv_sets_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        '\n'.join(
            [
                "# comment",
                "FOO_TEST_VAR=bar",
                'QUOTED_VAR="quoted value"',
                "EMPTY_LINE_BELOW=ok",
                "",
                "INDENTED_VAR  =  spaced  ",
            ]
        )
    )
    try:
        for var in ("FOO_TEST_VAR", "QUOTED_VAR", "EMPTY_LINE_BELOW", "INDENTED_VAR"):
            os.environ.pop(var, None)
        module = _load_script_module()
        module._load_dotenv(env_file)
        assert os.environ["FOO_TEST_VAR"] == "bar"
        assert os.environ["QUOTED_VAR"] == "quoted value"
        assert os.environ["EMPTY_LINE_BELOW"] == "ok"
    finally:
        for var in ("FOO_TEST_VAR", "QUOTED_VAR", "EMPTY_LINE_BELOW", "INDENTED_VAR"):
            os.environ.pop(var, None)


def test_load_dotenv_does_not_overwrite_existing_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_TEST_OVERRIDE=from_file")
    monkeypatch.setenv("FOO_TEST_OVERRIDE", "from_shell")
    module = _load_script_module()
    module._load_dotenv(env_file)
    assert os.environ["FOO_TEST_OVERRIDE"] == "from_shell"


def test_load_dotenv_silent_when_file_missing(tmp_path: Path) -> None:
    module = _load_script_module()
    module._load_dotenv(tmp_path / "nonexistent.env")  # should not raise


def test_dry_run_against_fixture_layout(tmp_path: Path) -> None:
    """Run the script as a subprocess in --dry-run mode against a tiny fixture
    repo. Confirms it discovers ATS slices and exits 0."""
    for ats in ("greenhouse", "lever"):
        ats_dir = tmp_path / ats
        ats_dir.mkdir()
        pd.DataFrame(
            [{"url": f"https://x/{ats}/1", "title": "T", "company": "C"}]
        ).to_csv(ats_dir / "jobs.csv", index=False)

    snap = tmp_path / "ai-03-05-2026.csv"
    pd.DataFrame([{"url": "https://x/1", "title": "T", "company": "C"}]).to_csv(
        snap, index=False
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(tmp_path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Found 2 ATS slices" in result.stderr
    assert "ai-03-05-2026.csv" not in result.stderr or "1 dated snapshots" in result.stderr
