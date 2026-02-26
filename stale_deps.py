#!/usr/bin/env python3
"""
stale-deps: Audit dependency health across Python and Node.js projects.

Reads requirements.txt, pyproject.toml, or package.json and reports:
- Last release date and days since last update
- Latest vs pinned version (with major-version-jump detection)
- Whether each package is actually imported in your source code (AST scan)

Usage:
    python stale_deps.py check [path] [--json] [--no-import-check] [--stale-days N]
"""

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from packaging.requirements import Requirement
from packaging.version import Version, InvalidVersion
from rich import box
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


console = Console()
err_console = Console(stderr=True)  # for status messages when --json is active

# Staleness thresholds (days)
STALE_DAYS = 365
VERY_STALE_DAYS = 730

# Common import-name → PyPI package-name aliases
IMPORT_ALIASES: dict[str, str] = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "jwt": "pyjwt",
    "Crypto": "pycryptodome",
    "attr": "attrs",
    "pkg_resources": "setuptools",
    "google": "google-cloud",
    "serial": "pyserial",
    "usb": "pyusb",
    "magic": "python-magic",
    "gi": "pygobject",
    "wx": "wxpython",
    "wx": "wxpython",
    "MySQLdb": "mysql-python",
    "psycopg2": "psycopg2-binary",
    "flask": "flask",
    "django": "django",
    "fastapi": "fastapi",
}


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Normalize package/import name for loose comparison."""
    return name.lower().replace("-", "_").replace(".", "_")


# ---------------------------------------------------------------------------
# AST import scanner
# ---------------------------------------------------------------------------

_SKIP_DIRS = frozenset({
    "venv", ".venv", "env", ".env", "node_modules", "__pycache__",
    ".git", "site-packages", "dist", "build", ".tox", ".nox",
    "eggs", ".eggs", "buck-out",
})


def collect_imports(project_path: Path) -> set[str]:
    """
    Walk all .py files under project_path and return top-level module names.
    Skips virtual-environment and build directories.
    """
    imports: set[str] = set()
    for py_file in project_path.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imports.add(node.module.split(".")[0])
    return imports


def is_imported(package_name: str, imports: set[str]) -> bool:
    """
    Return True if package_name appears to be imported anywhere in the project.
    Checks direct name match and common alias table.
    """
    norm_pkg = normalize_name(package_name)
    for imp in imports:
        norm_imp = normalize_name(imp)
        if norm_imp == norm_pkg:
            return True
    # Check alias table
    for alias, pkg in IMPORT_ALIASES.items():
        if normalize_name(pkg) == norm_pkg:
            if normalize_name(alias) in {normalize_name(i) for i in imports}:
                return True
    return False


# ---------------------------------------------------------------------------
# Registry API calls
# ---------------------------------------------------------------------------

def _parse_dt(s: str) -> Optional[datetime]:
    """Parse an ISO-8601 date string into a timezone-aware datetime."""
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def fetch_pypi_info(package_name: str) -> dict:
    """Hit PyPI JSON API and return version + release-date info."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            return {"error": "not found on PyPI"}
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return {"error": f"network error: {exc}"}
    except json.JSONDecodeError:
        return {"error": "bad JSON from PyPI"}

    latest = data["info"]["version"]
    releases = data.get("releases", {})
    last_date: Optional[datetime] = None

    if latest in releases and releases[latest]:
        file_entry = releases[latest][-1]
        raw = file_entry.get("upload_time_iso_8601") or file_entry.get("upload_time")
        if raw:
            last_date = _parse_dt(raw)

    return {
        "latest_version": latest,
        "last_release_date": last_date,
    }


def fetch_npm_info(package_name: str) -> dict:
    """Hit npm registry and return version + release-date info."""
    url = f"https://registry.npmjs.org/{package_name}"
    try:
        resp = requests.get(url, timeout=10, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return {"error": "not found on npm"}
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return {"error": f"network error: {exc}"}
    except json.JSONDecodeError:
        return {"error": "bad JSON from npm"}

    latest = data.get("dist-tags", {}).get("latest", "unknown")
    last_date: Optional[datetime] = None
    time_data = data.get("time", {})
    if latest in time_data:
        last_date = _parse_dt(time_data[latest])

    return {
        "latest_version": latest,
        "last_release_date": last_date,
    }


# ---------------------------------------------------------------------------
# Manifest parsers
# ---------------------------------------------------------------------------

def _req_from_str(line: str) -> dict:
    """Parse a PEP 508 dependency string into {name, pinned_version}."""
    line = line.split(";")[0].strip()  # drop env markers
    line = line.split("#")[0].strip()  # drop inline comments
    if not line:
        return {}
    try:
        req = Requirement(line)
        pinned: Optional[str] = None
        specs = list(req.specifier)
        for spec in specs:
            if spec.operator == "==":
                pinned = spec.version
                break
        if pinned is None and specs:
            best = sorted(specs, key=lambda s: ("==" not in s.operator, s.operator))[0]
            pinned = f"{best.operator}{best.version}"
        return {"name": req.name, "pinned_version": pinned}
    except Exception:
        m = re.match(r"^([A-Za-z0-9_\-\.]+)", line)
        if m:
            return {"name": m.group(1), "pinned_version": None}
        return {}


def parse_requirements_txt(path: Path) -> list[dict]:
    """Return [{name, pinned_version, ecosystem}] from requirements.txt."""
    deps = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", "-", "git+", "http")):
            continue
        parsed = _req_from_str(line)
        if parsed.get("name"):
            deps.append({**parsed, "ecosystem": "pypi"})
    return deps


def parse_pyproject_toml(path: Path) -> list[dict]:
    """Return [{name, pinned_version, ecosystem}] from pyproject.toml."""
    if tomllib is None:
        console.print("[yellow]Warning: tomllib unavailable. Install tomli for Python < 3.11.[/yellow]")
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[yellow]Warning: could not parse pyproject.toml: {exc}[/yellow]")
        return []

    deps = []

    # PEP 621 / setuptools style
    for raw in data.get("project", {}).get("dependencies", []):
        parsed = _req_from_str(raw)
        if parsed.get("name"):
            deps.append({**parsed, "ecosystem": "pypi"})

    # Poetry style
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for pkg, ver_spec in poetry_deps.items():
        if pkg.lower() == "python":
            continue
        pinned: Optional[str] = None
        if isinstance(ver_spec, str) and ver_spec not in ("*", ""):
            pinned = ver_spec
        deps.append({"name": pkg, "pinned_version": pinned, "ecosystem": "pypi"})

    # Optional deps groups (PEP 621)
    for group_extras in data.get("project", {}).get("optional-dependencies", {}).values():
        for raw in group_extras:
            parsed = _req_from_str(raw)
            if parsed.get("name"):
                deps.append({**parsed, "ecosystem": "pypi"})

    return deps


def parse_package_json(path: Path) -> list[dict]:
    """Return [{name, pinned_version, ecosystem}] from package.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[yellow]Warning: could not parse package.json: {exc}[/yellow]")
        return []
    deps = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for pkg, ver in data.get(section, {}).items():
            pinned = ver if ver and ver not in ("*", "latest") else None
            deps.append({"name": pkg, "pinned_version": pinned, "ecosystem": "npm"})
    return deps


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

def compute_version_status(pinned: Optional[str], latest: str) -> str:
    """Compare pinned spec vs latest version string."""
    if not pinned:
        return "unpinned"
    m = re.search(r"[\d][\d.]*", pinned)
    if not m:
        return "unpinned"
    try:
        pv = Version(m.group())
        lv = Version(latest)
        if pv == lv:
            return "up-to-date"
        if pv < lv:
            if lv.major > pv.major:
                return f"major ({m.group()} → {latest})"
            if lv.minor > pv.minor:
                return f"minor ({m.group()} → {latest})"
            return f"patch ({m.group()} → {latest})"
        return "up-to-date"  # pinned newer than released (pre-release)
    except InvalidVersion:
        clean = m.group()
        return "up-to-date" if clean == latest else f"behind ({clean} → {latest})"


# ---------------------------------------------------------------------------
# Rich table
# ---------------------------------------------------------------------------

def _stale_color(days: Optional[int], stale: int, very_stale: int) -> str:
    if days is None:
        return "dim"
    if days >= very_stale:
        return "red"
    if days >= stale:
        return "yellow"
    return "green"


def build_table(
    results: list[dict],
    show_imported: bool,
    stale: int,
    very_stale: int,
) -> Table:
    """Assemble the Rich dependency health table."""
    table = Table(
        title="[bold white]Dependency Health Report[/bold white]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_header=True,
        padding=(0, 1),
    )
    table.add_column("Package", min_width=22, no_wrap=True)
    table.add_column("Pinned", no_wrap=True)
    table.add_column("Latest", no_wrap=True)
    table.add_column("Last Release", no_wrap=True)
    table.add_column("Days Old", justify="right", no_wrap=True)
    table.add_column("Version Status", no_wrap=True)
    if show_imported:
        table.add_column("Imported?", justify="center", no_wrap=True)

    # Sort: errors last, then by days descending (stalest first)
    def sort_key(r: dict) -> tuple:
        has_err = 1 if "error" in r else 0
        days = r.get("days_since_update") or 0
        return (has_err, -days)

    for r in sorted(results, key=sort_key):
        name = r["name"]
        ecosystem = r.get("ecosystem", "pypi")
        eco_tag = "[dim][PyPI][/dim]" if ecosystem == "pypi" else "[dim][npm][/dim]"
        pinned_str = r.get("pinned_version") or "[dim]none[/dim]"

        if "error" in r:
            row = [
                f"{name} {eco_tag}",
                str(pinned_str),
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                "[dim]—[/dim]",
                f"[dim]{r['error']}[/dim]",
            ]
            if show_imported:
                row.append("[dim]?[/dim]")
            table.add_row(*row)
            continue

        days = r.get("days_since_update")
        color = _stale_color(days, stale, very_stale)
        last_date: Optional[datetime] = r.get("last_release_date")
        date_str = last_date.strftime("%Y-%m-%d") if last_date else "unknown"
        days_str = str(days) if days is not None else "?"
        latest = r.get("latest_version", "?")

        # Version status formatting
        vstatus = r.get("version_status", "unknown")
        if vstatus == "up-to-date":
            vstatus_fmt = "[green]✓ up-to-date[/green]"
        elif vstatus == "unpinned":
            vstatus_fmt = f"[dim]unpinned (latest: {latest})[/dim]"
        elif vstatus.startswith("major"):
            vstatus_fmt = f"[red]⚠ {vstatus}[/red]"
        elif vstatus.startswith("minor"):
            vstatus_fmt = f"[yellow]↑ {vstatus}[/yellow]"
        elif vstatus.startswith("patch"):
            vstatus_fmt = f"[cyan]↑ {vstatus}[/cyan]"
        else:
            vstatus_fmt = f"[dim]{vstatus}[/dim]"

        row = [
            f"[{color}]{name}[/{color}] {eco_tag}",
            str(pinned_str),
            latest,
            f"[{color}]{date_str}[/{color}]",
            f"[{color}]{days_str}[/{color}]",
            vstatus_fmt,
        ]
        if show_imported:
            imp = r.get("imported")
            if imp is True:
                row.append("[green]✓[/green]")
            elif imp is False:
                row.append("[yellow]✗[/yellow]")
            else:
                row.append("[dim]?[/dim]")
        table.add_row(*row)

    return table


# ---------------------------------------------------------------------------
# Command: check
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    """Run the dependency audit."""
    project_path = Path(args.path).resolve()

    if not project_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {project_path}")
        return 1

    if project_path.is_file():
        manifest_files = [project_path]
        project_root = project_path.parent
    else:
        project_root = project_path
        manifest_files = [
            f for name in ("requirements.txt", "pyproject.toml", "package.json")
            if (f := project_path / name).exists()
        ]

    if not manifest_files:
        console.print(
            f"[red]Error:[/red] No requirements.txt, pyproject.toml, or package.json "
            f"found in [bold]{project_path}[/bold]"
        )
        return 1

    # Use stderr for status when JSON output is requested
    status = err_console if args.json else console

    # Parse manifests
    deps: list[dict] = []
    for manifest in manifest_files:
        status.print(f"[dim]Reading {manifest.name}...[/dim]")
        if manifest.name == "requirements.txt":
            deps.extend(parse_requirements_txt(manifest))
        elif manifest.name == "pyproject.toml":
            deps.extend(parse_pyproject_toml(manifest))
        elif manifest.name == "package.json":
            deps.extend(parse_package_json(manifest))

    if not deps:
        status.print("[yellow]No dependencies found in manifests.[/yellow]")
        return 0

    # Deduplicate
    seen: set[tuple] = set()
    unique: list[dict] = []
    for d in deps:
        key = (normalize_name(d["name"]), d["ecosystem"])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    deps = unique

    # AST import scan
    has_py = any(d["ecosystem"] == "pypi" for d in deps)
    imports: set[str] = set()
    if has_py and not args.no_import_check:
        status.print("[dim]Scanning .py files for imports (AST)...[/dim]")
        imports = collect_imports(project_root)
        status.print(f"[dim]Found {len(imports)} unique top-level imports.[/dim]")

    # Fetch registry info
    stale = args.stale_days
    very_stale = args.stale_days * 2
    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=status,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Fetching {len(deps)} packages…", total=len(deps))
        for dep in deps:
            name = dep["name"]
            ecosystem = dep["ecosystem"]
            progress.update(task, description=f"Fetching [bold]{name}[/bold]…")

            info = fetch_pypi_info(name) if ecosystem == "pypi" else fetch_npm_info(name)

            result: dict = {
                "name": name,
                "ecosystem": ecosystem,
                "pinned_version": dep.get("pinned_version"),
            }

            if "error" in info:
                result["error"] = info["error"]
            else:
                last_date: Optional[datetime] = info.get("last_release_date")
                latest = info.get("latest_version", "unknown")
                now = datetime.now(timezone.utc)
                days: Optional[int] = None
                if last_date:
                    ld = last_date if last_date.tzinfo else last_date.replace(tzinfo=timezone.utc)
                    days = (now - ld).days

                result["latest_version"] = latest
                result["last_release_date"] = last_date
                result["days_since_update"] = days
                result["version_status"] = compute_version_status(dep.get("pinned_version"), latest)

                if ecosystem == "pypi" and not args.no_import_check and imports:
                    result["imported"] = is_imported(name, imports)

            results.append(result)
            progress.advance(task)

    # Output
    if args.json:
        output = []
        for r in results:
            row = dict(r)
            if isinstance(row.get("last_release_date"), datetime):
                row["last_release_date"] = row["last_release_date"].isoformat()
            output.append(row)
        print(json.dumps(output, indent=2))
        return 0

    show_imported = has_py and not args.no_import_check and bool(imports)
    table = build_table(results, show_imported, stale, very_stale)
    console.print()
    console.print(table)

    # Summary line
    total = len(results)
    errors = sum(1 for r in results if "error" in r)
    stale_count = sum(
        1 for r in results
        if r.get("days_since_update") is not None and r["days_since_update"] >= stale
    )
    very_stale_count = sum(
        1 for r in results
        if r.get("days_since_update") is not None and r["days_since_update"] >= very_stale
    )
    major_behind = sum(
        1 for r in results
        if r.get("version_status", "").startswith("major")
    )
    not_imported = sum(1 for r in results if r.get("imported") is False)

    parts = [
        f"[bold]{total}[/bold] packages scanned",
        f"[red]{very_stale_count} very stale[/red] (>{very_stale}d)",
        f"[yellow]{stale_count} stale[/yellow] (>{stale}d)",
    ]
    if major_behind:
        parts.append(f"[red]{major_behind} major version behind[/red]")
    if show_imported and not_imported:
        parts.append(f"[yellow]{not_imported} possibly unused[/yellow]")
    if errors:
        parts.append(f"[dim]{errors} fetch error(s)[/dim]")

    console.print()
    console.print("  " + " · ".join(parts))
    console.print()

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="stale-deps",
        description=(
            "Audit dependency health: staleness, version drift, and unused packages.\n"
            "Supports requirements.txt, pyproject.toml, and package.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="stale-deps 1.0.0")

    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser(
        "check",
        help="Audit dependencies in a project directory or manifest file",
        description="Check dependencies for staleness, version drift, and import usage.",
    )
    check.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory or manifest file path (default: current directory)",
    )
    check.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of a table",
    )
    check.add_argument(
        "--no-import-check",
        action="store_true",
        dest="no_import_check",
        help="Skip AST scan for import usage",
    )
    check.add_argument(
        "--stale-days",
        type=int,
        default=365,
        dest="stale_days",
        metavar="DAYS",
        help="Days threshold for 'stale' (default: 365; 'very stale' = 2×)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
