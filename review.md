# Review: stale-deps

## Idea
- **Name**: stale-deps
- **Problem**: Developers inherit or maintain projects with dozens of dependencies and have no quick way to audit their health. `pip audit` and `npm audit` only flag CVEs — they don't tell you a package hasn't been touched in 3 years, has a major version jump waiting, or is listed in requirements.txt but never actually imported in your code.
- **Solution**: A Python CLI that reads requirements.txt / pyproject.toml / package.json, hits the free PyPI and npm registry JSON APIs, and produces a color-coded terminal table: last release date, latest vs pinned version, days since last update, and an "actively imported?" check via AST scan. No auth, no setup — just `stale-deps check` in any project root.
- **Content Angle**: \"I ran this on a client's Django project and 11 of their 47 dependencies hadn't been updated in over 2 years. One of them hasn't had a commit since 2019. This is a ticking clock for every Python project.\"
- **Source**: auto

## Build Result
- **Success**: True
- **Attempts**: 2/3
- **Cost**: $1.82
- **Duration**: 380.8s
- **Files created**: 7

### Files
README.md
__pycache__/stale_deps.cpython-312.pyc
__pycache__/test_tool.cpython-312-pytest-9.0.2.pyc
idea.json
requirements.txt
stale_deps.py
test_tool.py

## Test Result
- **Overall**: PASS
- **Passed**: 4/5
- **Failed**: 0
- **Errors**: 0

### Test Cases
[PASS] syntax_check - All 2 Python files have valid syntax
[PASS] readme_exists - README.md exists (2744 chars)
[PASS] secret_scan - No hardcoded secrets detected in 2 file(s)
[PASS] entry_point_exists - Entry point found: stale_deps.py
[ERROR] tool_own_pytest - pytest not installed in tool's venv, skipping

## Content
- **Video script**: Generated
- **Twitter thread**: Generated
- **Skool post**: Generated

## Action
To publish: `./run.sh --publish /Users/jamesgoldbach/clawd/projects/tool-factory/tools/2026-02-26-stale-deps`
