



# Video Script: Stale Deps

## HOOK (0-3 seconds)
Stop Developers inherit or maintain projects with dozens of dependencies and have no quick way to audit their health. `pip audit` and `npm audit` only flag CVEs — they don't tell you a package hasn't been touched in 3 years, has a major version jump waiting, or is listed in requirements.txt but never actually imported in your code. - here's a free tool that does it in seconds




## DEMO (3-35 seconds)
Here's stale deps in action. A Python CLI that reads requirements.txt / pyproject.toml / package.json, hits the free PyPI and npm registry JSON APIs, and produces a color-coded terminal table: last release date, latest vs pinned version, days since last update, and an "actively imported?" check via AST scan. No auth, no setup — just `stale-deps check` in any project root.. It takes about 3 seconds.

**Show on screen:**

- pip install -r requirements.txt

- python stale_deps.py --help

- python stale_deps.py [your-input]

- Show: output/result

**Tech shown:** requests, rich, ast (stdlib), tomllib (stdlib), packaging, argparse (stdlib)

## CTA (35-45 seconds)
Free download - link in bio

**ManyChat trigger:** Comment **STALE** and I'll DM you the link

---

**LENGTH:** 30-45 seconds
**KEYWORD TRIGGER:** STALE
**FILMING NOTES:**
- Screen recording of terminal/IDE (real dev environment, not slides)
- Big captions mandatory (80% watch on mute)
- Face cam in corner optional but adds authenticity
- Show requests code running in real terminal

- Build context: 2 iterations, 337164 lines of code


**CONTENT ANGLE:** \"I ran this on a client's Django project and 11 of their 47 dependencies hadn't been updated in over 2 years. One of them hasn't had a commit since 2019. This is a ticking clock for every Python project.\"
**DATE:** 2026-02-26