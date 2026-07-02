import ast, sys

with open("_build_docx.py", "r", encoding="utf-8") as f:
    source = f.read()

try:
    ast.parse(source)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    lines = source.split('\n')
    if e.lineno:
        for offset in range(-2, 3):
            ln = e.lineno + offset
            if 1 <= ln <= len(lines):
                marker = ">>>" if offset == 0 else "   "
                print(f"{marker} {ln}: {lines[ln-1][:150]}")
