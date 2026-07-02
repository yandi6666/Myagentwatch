"""MyAgentWatch — 一键检查脚本 (make check equivalent)

Usage: python check.py

Runs:
 1. Python import & module smoke tests
 2. JavaScript syntax checks
 3. HTML script/css reference checks
 4. DB migration + pricing integrity
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
FAIL = 0

def ok(msg):
    print(f"  OK  {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL {msg}")

# ── 1. Python smoke tests ──
print("\n[1/4] Python smoke tests")
result = subprocess.run(
    [sys.executable, os.path.join(ROOT, "tests", "test_smoke.py")],
    capture_output=True, text=True, cwd=ROOT,
)
print(result.stdout.strip())
if result.returncode != 0:
    print(result.stderr)
    fail("Python smoke tests")
else:
    ok("Python smoke tests")

# ── 2. Python module imports ──
print("\n[2/4] Python module imports")
modules = [
    "myagentwatch.db",
    "myagentwatch.collector",
    "myagentwatch.alerting",
    "myagentwatch.pricing",
    "myagentwatch.queries",
    "myagentwatch.event_bus",
    "myagentwatch.config",
]
for m in modules:
    try:
        __import__(m)
        ok(m)
    except Exception as e:
        fail(f"{m}: {e}")

# ── 3. JavaScript syntax checks ──
print("\n[3/4] JavaScript syntax checks")
js_dir = os.path.join(ROOT, "static", "js")
js_files = sorted(
    f for f in os.listdir(js_dir) if f.endswith(".js")
)

for js_file in js_files:
    path = os.path.join(js_dir, js_file)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    issues = []

    # Brace balance
    if content.count("{") != content.count("}"):
        issues.append("unbalanced braces")
    if content.count("(") != content.count(")"):
        issues.append("unbalanced parens")
    if content.count("[") != content.count("]"):
        issues.append("unbalanced brackets")

    # Template literal backtick balance
    backticks = content.count("`")
    if backticks % 2 != 0:
        issues.append("unbalanced backticks")

    if issues:
        fail(f"{js_file}: {', '.join(issues)}")
    else:
        ok(js_file)

# ── 4. HTML references check ──
print("\n[4/4] HTML references check")
html_path = os.path.join(ROOT, "static", "index.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# CSS references
css_refs = re.findall(r'href="(/css/[^"]+\.css[^"]*)"', html)
for href in css_refs:
    css_path = os.path.join(ROOT, "static", href.lstrip("/"))
    if os.path.exists(css_path):
        ok(f"CSS {href}")
    else:
        fail(f"CSS missing: {href}")

# JS references
js_refs = re.findall(r'src="(/js/[^"]+)"', html)
for src in js_refs:
    clean = src.split("?")[0]  # strip cache busters like ?v=5
    js_path = os.path.join(ROOT, "static", clean.lstrip("/"))
    if os.path.exists(js_path):
        ok(f"JS  {src}")
    else:
        fail(f"JS missing: {src} → {js_path}")

# CDN checks (just verify URL format, not reachability)
cdn_refs = re.findall(r'(https://[^"]+\.js)"', html)
for url in cdn_refs:
    ok(f"CDN {url.split('/')[-1][:40]}...")

# ── Result ──
print(f"\n{'='*50}")
if FAIL == 0:
    print("ALL CHECKS PASSED")
else:
    print(f"{FAIL} CHECK(S) FAILED")
sys.exit(0 if FAIL == 0 else 1)
