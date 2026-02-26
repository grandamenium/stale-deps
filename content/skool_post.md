


# Free Tool: Audit every dependency in your Python or Node project for abandoned packages in one command

If you're building agents, you're pip installing half the ecosystem to test integrations — and six months later your requirements.txt is a graveyard of packages nobody's touched in years. pip audit and npm audit only catch CVEs, so the slow rot goes completely unnoticed.

## What it does

Scans your project's dependencies and flags zombie packages — abandoned, outdated, or imported-but-unused — before they become a security or maintenance nightmare.. I built stale-deps to fix this: it reads your requirements.txt, pyproject.toml, or package.json, hits the free PyPI and npm registry JSON APIs (no auth, no setup), and prints a color-coded terminal table with last release date, days since last update, pinned vs latest version, and whether each package is actually imported anywhere in your code via AST scan. I ran it on a client's Django project and 11 of their 47 dependencies hadn't been updated in over 2 years — one of them hasn't had a commit since 2019.

## How to use it


1. pip install -r requirements.txt

2. python stale_deps.py --help

3. python stale_deps.py [your-input]


**Requirements:** Python 3.10+, requests, rich, ast (stdlib), tomllib (stdlib), packaging, argparse (stdlib)

## Get it

GitHub: {{github_url}}


---

*Built it in 2 iterations over 6.3 minutes — fair warning though, the AST import detection is still shaky with dynamic imports like importlib.import_module, so don't treat the 'actively imported' column as definitive for anything doing runtime loading.*


What's the oldest abandoned package you've found lurking in a project you inherited? Genuinely curious whether 2019 is actually bad or just Tuesday.