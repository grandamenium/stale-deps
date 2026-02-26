# stale-deps

Audit your project's dependency health: staleness, version drift, and packages that aren't even imported.

## Installation

```bash
pip install -r requirements.txt
python stale_deps.py --help
```

## Usage

```bash
# Audit current directory (auto-detects requirements.txt / pyproject.toml / package.json)
python stale_deps.py check

# Audit a specific project folder
python stale_deps.py check /path/to/project

# Point directly at a manifest file
python stale_deps.py check /path/to/requirements.txt

# JSON output (pipe to jq, log to file, etc.)
python stale_deps.py check --json

# Skip the AST import scan
python stale_deps.py check --no-import-check

# Custom staleness threshold (warn at 180 days instead of 365)
python stale_deps.py check --stale-days 180
```

## Examples

**Color-coded terminal table:**

```
╭─────────────────────────────────────────────────────────────────────────────────╮
│                        Dependency Health Report                                 │
├──────────────────────────┬──────────┬─────────┬─────────────┬─────────┬────────┤
│ Package                  │ Pinned   │ Latest  │ Last Release│ Days Old│ Imported│
├──────────────────────────┼──────────┼─────────┼─────────────┼─────────┼────────┤
│ django [PyPI]            │ ==3.2.0  │ 5.0.2   │ 2024-02-06  │    20   │ ✓      │
│ some-old-lib [PyPI]      │ ==0.9.0  │ 0.9.0   │ 2019-03-11  │  1780   │ ✗      │
│ requests [PyPI]          │ ==2.31.0 │ 2.31.0  │ 2023-05-22  │   250   │ ✓      │
╰──────────────────────────┴──────────┴─────────┴─────────────┴─────────┴────────╯

  47 packages scanned · 11 very stale (>730d) · 18 stale (>365d) · 3 major version behind · 4 possibly unused
```

**Color key:**
- 🟢 Green — updated within the last year
- 🟡 Yellow — 1–2 years since last release
- 🔴 Red — over 2 years since last release

**Imported? column (Python only):**
- ✓ — package name found via AST scan of your .py files
- ✗ — not imported anywhere (possible dead dependency)

**JSON output for scripting:**

```bash
python stale_deps.py check --json | jq '[.[] | select(.days_since_update > 730)]'
```

## What it checks

| Column | Source |
|--------|--------|
| Latest version | PyPI JSON API / npm registry |
| Last release date | PyPI upload timestamps / npm `time` object |
| Version status | `packaging` library comparison (detects major jumps) |
| Imported? | AST walk of all `.py` files, skips `venv/`, `.venv/`, `node_modules/` |

Supports: `requirements.txt`, `pyproject.toml` (PEP 621 + Poetry), `package.json`.

No API key. No sign-up. Just run it.

## Requirements

- Python 3.10+
- `requests>=2.28.0`
- `rich>=13.0.0`
- `packaging>=23.0`
- `tomli>=2.0.0` (Python 3.10 only; 3.11+ uses stdlib `tomllib`)

## License

MIT
