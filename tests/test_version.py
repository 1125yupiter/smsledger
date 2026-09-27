"""One version number, and no way to declare a second one that disagrees.

Nothing here checks what the version *is*. It checks that a release cannot be cut
with two answers to "which version is this", because that is the failure a person
notices only after uploading -- and an upload cannot be taken back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import smsledger

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _project_table(text: str) -> str:
    """The [project] table alone, up to whatever table comes next."""
    start = text.index("\n[project]\n") + 1
    rest = text[start + len("[project]\n") :]
    end = re.search(r"^\[", rest, re.M)
    return rest[: end.start()] if end else rest


def test_the_package_declares_a_release_number() -> None:
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?([ab]\d+|rc\d+|\.dev\d+)?", smsledger.__version__), (
        smsledger.__version__
    )


def test_pyproject_takes_the_version_from_the_package_and_does_not_restate_it() -> None:
    """A literal `version = "..."` in [project] is the second copy. Bumping one and
    forgetting the other ships a wheel whose metadata contradicts what the tool
    prints in its own diagnostic file."""
    text = PYPROJECT.read_text(encoding="utf-8")
    project = _project_table(text)
    assert not re.search(r'^\s*version\s*=\s*"', project, re.M), (
        "pyproject declares its own version; delete it and keep the dynamic one"
    )
    assert re.search(r'^\s*dynamic\s*=\s*\[[^\]]*"version"', project, re.M)
    assert re.search(
        r'^version\s*=\s*\{\s*attr\s*=\s*"smsledger\.__version__"\s*\}', text, re.M
    )


def test_installed_metadata_agrees_with_the_package() -> None:
    """The build backend resolved the attr, rather than silently shipping 0.0.0."""
    metadata = pytest.importorskip("importlib.metadata")
    try:
        installed = metadata.version("smsledger")
    except metadata.PackageNotFoundError:
        pytest.skip("running from a source tree, not an install")
    assert installed == smsledger.__version__


def test_the_readme_install_line_names_no_version() -> None:
    """Pinning a version in the line a beginner pastes means editing prose on every
    release, and prose is what gets forgotten."""
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if "pip3 install" in line or "pip install" in line:
            assert "smsledger==" not in line, line
