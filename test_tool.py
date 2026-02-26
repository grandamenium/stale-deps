"""
Tests for stale-deps.

Covers: smoke import, CLI help, core functionality, error handling, edge cases.
"""

import ast
import json
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def test_import_smoke():
    """Module imports without errors."""
    import stale_deps  # noqa: F401
    assert hasattr(stale_deps, "main")
    assert hasattr(stale_deps, "fetch_pypi_info")
    assert hasattr(stale_deps, "collect_imports")


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

def test_help_flag():
    """--help exits 0 and shows usage text."""
    result = subprocess.run(
        [sys.executable, "stale_deps.py", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    assert result.returncode == 0
    assert "stale-deps" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_check_help_flag():
    """check --help exits 0."""
    result = subprocess.run(
        [sys.executable, "stale_deps.py", "check", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    assert result.returncode == 0
    assert "check" in result.stdout.lower()


def test_no_args_exits_cleanly():
    """No arguments prints help and exits 0 (no traceback)."""
    result = subprocess.run(
        [sys.executable, "stale_deps.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr


def test_invalid_flag():
    """Unknown flag exits non-zero without a Python traceback."""
    result = subprocess.run(
        [sys.executable, "stale_deps.py", "--totally-bogus-flag"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_nonexistent_path():
    """Missing directory exits non-zero with a clear error message."""
    result = subprocess.run(
        [sys.executable, "stale_deps.py", "check", "/this/path/does/not/exist/ever"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_empty_directory():
    """Directory with no manifests exits non-zero with a helpful message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "stale_deps.py", "check", tmpdir],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )
        assert result.returncode != 0
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

def test_parse_requirements_txt():
    """Correctly parses pinned and unpinned entries from requirements.txt."""
    from stale_deps import parse_requirements_txt

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("requests==2.28.0\n")
        f.write("flask>=2.0.0\n")
        f.write("# a comment\n")
        f.write("  \n")
        f.write("rich\n")
        fname = f.name

    deps = parse_requirements_txt(Path(fname))
    names = [d["name"].lower() for d in deps]
    assert "requests" in names
    assert "flask" in names
    assert "rich" in names
    assert all(d["ecosystem"] == "pypi" for d in deps)

    # Pinned version should be captured for requests
    requests_dep = next(d for d in deps if d["name"].lower() == "requests")
    assert requests_dep["pinned_version"] == "2.28.0"

    Path(fname).unlink(missing_ok=True)


def test_parse_package_json():
    """Correctly parses npm dependencies from package.json."""
    from stale_deps import parse_package_json

    data = {
        "dependencies": {"express": "^4.18.0", "lodash": "4.17.21"},
        "devDependencies": {"jest": "^29.0.0"},
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        fname = f.name

    deps = parse_package_json(Path(fname))
    names = [d["name"] for d in deps]
    assert "express" in names
    assert "lodash" in names
    assert "jest" in names
    assert all(d["ecosystem"] == "npm" for d in deps)

    Path(fname).unlink(missing_ok=True)


def test_parse_pyproject_toml_pep621():
    """Parses PEP 621 [project.dependencies] from pyproject.toml."""
    from stale_deps import parse_pyproject_toml

    content = textwrap.dedent("""\
        [project]
        name = "myapp"
        dependencies = [
            "requests>=2.28.0",
            "click==8.1.0",
        ]
    """)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        fname = f.name

    deps = parse_pyproject_toml(Path(fname))
    names = [d["name"].lower() for d in deps]
    assert "requests" in names
    assert "click" in names

    click_dep = next(d for d in deps if d["name"].lower() == "click")
    assert click_dep["pinned_version"] == "8.1.0"

    Path(fname).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AST scanner unit tests
# ---------------------------------------------------------------------------

def test_collect_imports_basic():
    """AST scanner collects top-level import names from .py files."""
    from stale_deps import collect_imports

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "app.py"
        src.write_text(
            "import requests\nfrom flask import Flask\nimport os\n",
            encoding="utf-8",
        )
        imports = collect_imports(Path(tmpdir))
    assert "requests" in imports
    assert "flask" in imports
    assert "os" in imports


def test_collect_imports_skips_venv():
    """AST scanner skips virtual environment directories."""
    from stale_deps import collect_imports

    with tempfile.TemporaryDirectory() as tmpdir:
        venv_dir = Path(tmpdir) / "venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "injected.py").write_text("import secret_package\n", encoding="utf-8")

        real = Path(tmpdir) / "main.py"
        real.write_text("import requests\n", encoding="utf-8")

        imports = collect_imports(Path(tmpdir))

    assert "requests" in imports
    assert "secret_package" not in imports


def test_collect_imports_syntax_error():
    """AST scanner silently skips files with syntax errors."""
    from stale_deps import collect_imports

    with tempfile.TemporaryDirectory() as tmpdir:
        bad = Path(tmpdir) / "broken.py"
        bad.write_text("def foo(:\n    pass\n", encoding="utf-8")  # syntax error
        good = Path(tmpdir) / "good.py"
        good.write_text("import requests\n", encoding="utf-8")

        imports = collect_imports(Path(tmpdir))

    assert "requests" in imports  # good file still scanned


# ---------------------------------------------------------------------------
# Version comparison unit tests
# ---------------------------------------------------------------------------

def test_compute_version_status_up_to_date():
    from stale_deps import compute_version_status
    assert compute_version_status("==2.28.0", "2.28.0") == "up-to-date"


def test_compute_version_status_major_behind():
    from stale_deps import compute_version_status
    status = compute_version_status("==1.0.0", "2.0.0")
    assert "major" in status


def test_compute_version_status_patch_behind():
    from stale_deps import compute_version_status
    status = compute_version_status("==2.0.0", "2.0.5")
    assert "patch" in status


def test_compute_version_status_unpinned():
    from stale_deps import compute_version_status
    assert compute_version_status(None, "2.0.0") == "unpinned"


# ---------------------------------------------------------------------------
# Date / staleness helpers
# ---------------------------------------------------------------------------

def test_stale_color_green():
    from stale_deps import _stale_color
    assert _stale_color(30, 365, 730) == "green"


def test_stale_color_yellow():
    from stale_deps import _stale_color
    assert _stale_color(400, 365, 730) == "yellow"


def test_stale_color_red():
    from stale_deps import _stale_color
    assert _stale_color(800, 365, 730) == "red"


def test_stale_color_none():
    from stale_deps import _stale_color
    assert _stale_color(None, 365, 730) == "dim"


# ---------------------------------------------------------------------------
# JSON output integration test
# ---------------------------------------------------------------------------

def test_json_output_with_temp_requirements():
    """JSON output is valid and contains expected keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        req = Path(tmpdir) / "requirements.txt"
        req.write_text("requests\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "stale_deps.py"),
                "check",
                tmpdir,
                "--json",
                "--no-import-check",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # May fail due to network but should not crash with Traceback
        assert "Traceback" not in result.stderr
        if result.returncode == 0:
            data = json.loads(result.stdout)
            assert isinstance(data, list)
            if data:
                assert "name" in data[0]
                assert "ecosystem" in data[0]


# ---------------------------------------------------------------------------
# is_imported alias test
# ---------------------------------------------------------------------------

def test_is_imported_alias():
    """Alias table resolves PIL -> pillow."""
    from stale_deps import is_imported
    assert is_imported("pillow", {"PIL"}) is True


def test_is_imported_direct():
    """Direct match works."""
    from stale_deps import is_imported
    assert is_imported("requests", {"requests", "flask"}) is True


def test_is_imported_false():
    """Returns False when package not in imports."""
    from stale_deps import is_imported
    assert is_imported("numpy", {"requests", "flask"}) is False


def test_normalize_name():
    """Hyphens and dots are normalized to underscores."""
    from stale_deps import normalize_name
    assert normalize_name("my-package") == "my_package"
    assert normalize_name("My.Package") == "my_package"
