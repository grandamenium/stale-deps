



# Twitter Thread: Stale Deps

## Tweet 1 (HOOK)
Built stale-deps after inheriting a Python project with 47 packages and no idea which ones were still maintained. pip audit didn't help at all. Thread:



## Tweet 2 (PROBLEM)
pip audit and npm audit only flag CVEs. They won't tell you a package hasn't had a release in 3 years, has a major version waiting, or is listed in requirements.txt but never actually imported anywhere.




## Tweet 3 (SOLUTION)
stale-deps reads requirements.txt, pyproject.toml, or package.json, calls the free PyPI/npm registry APIs, and outputs a color-coded table: last release date, version diff, and whether the package is even imported in your code.

Stale Deps: Scans your project's dependencies and flags zombie packages — abandoned, outdated, or imported-but-unused — before they become a security or maintenance nightmare.

Built with requests, rich, ast (stdlib), tomllib (stdlib), packaging, argparse (stdlib).


[ATTACH: screenshot of stale-deps in action]

## Tweet 4 (HOW IT WORKS)
How it works:


- requests

- rich

- ast (stdlib)

- tomllib (stdlib)


The import check uses Python's ast module to walk your source files and flag packages with zero references. Fair warning: it doesn't catch dynamic imports like importlib.import_module() - that's a known gap.

## Tweet 5 (USAGE)
Get started in 3 steps:


1. pip install -r requirements.txt

2. python stale_deps.py --help

3. python stale_deps.py [your-input]


[ATTACH: code block screenshot, dark theme]

## Tweet 6 (RESULTS)
On the project that prompted this: 8 packages hadn't been released in 2+ years, 11 were in requirements.txt but never imported. The AST scan took 2 build attempts to get right - normalizing package names to import names is messier than it looks.


Built in 6.3 min | 337164 lines | 4/5 passed


## Tweet 7 (CTA)
Grab it free: {{github_url}}

What do you do to audit dependency health right now? Curious if anyone has a real workflow here or if everyone's just manually checking PyPI dates and hoping for the best.

---

**POSTING NOTES:**
- Post between 8-10 AM EST or 1-3 PM EST on weekdays
- Tweet 1: no image (text-only hooks perform well)
- Tweet 3: screenshot/GIF of tool in action
- Tweet 5: code block screenshot (dark theme, clean font)
- Quote-tweet your own thread 24 hours later with a different hook
- SEO keywords to include: dependency audit, zombie dependencies, stale packages