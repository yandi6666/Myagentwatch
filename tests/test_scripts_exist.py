"""Test that all script references in index.html point to existing files (B3 regression)."""

import os


def test_all_script_sources_exist():
    """Every <script src='...'> in index.html must reference an existing file."""
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static"
    )
    index_path = os.path.join(static_dir, "index.html")

    with open(index_path) as f:
        html = f.read()

    import re
    srcs = re.findall(r'<script\s+src="([^"]+)"', html)

    missing = []
    for src in srcs:
        if src.startswith(("http://", "https://")):
            continue  # CDN URLs, skip
        file_path = os.path.join(static_dir, src.lstrip("/"))
        if not os.path.isfile(file_path):
            missing.append(file_path)

    assert not missing, f"Missing script files referenced in index.html: {missing}"


def test_no_dead_scripts_in_directory():
    """Warn if JS files exist in static/js/ but are not referenced in index.html."""
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static"
    )
    js_dir = os.path.join(static_dir, "js")
    index_path = os.path.join(static_dir, "index.html")

    with open(index_path) as f:
        html = f.read()

    import re
    refs = set()
    for src in re.findall(r'<script\s+src="([^"]+)"', html):
        if not src.startswith(("http://", "https://")):
            refs.add(os.path.basename(src))

    js_files = set(os.listdir(js_dir))
    unreferenced = js_files - refs

    # This is informational — not an error, just visibility
    if unreferenced:
        print(f"INFO: JS files not referenced in index.html: {unreferenced}")
