"""Fix quotes that were normalized to ASCII inside Python strings."""
import re
from pathlib import Path

f = Path("_build_docx.py")
content = f.read_text("utf-8")

# Replace known problematic patterns where Chinese-context quotes
# got converted to ASCII double quotes inside Python double-quoted strings
fixes = [
    ('"干活儿的"', '「干活儿的」'),
    ('"你不知道一个交易策略是经过充分验证的还是草率决定的。"', '「你不知道一个交易策略是经过充分验证的还是草率决定的。」'),
    ('"不是监控"，而是"知道同事在做什么"', '「不是监控」，而是「知道同事在做什么」'),
    ('"今天花了多少钱？哪个 Agent 最费钱？缓存命中率是多少？有没有模型没用定价？"', '「今天花了多少钱？哪个 Agent 最费钱？缓存命中率是多少？有没有模型没用定价？」'),
    ('"让 Agent 不再是你的员工，而是你的同事。"', '「让 Agent 不再是你的员工，而是你的同事。」'),
]

for old, new in fixes:
    if old in content:
        content = content.replace(old, new)
        print(f"Fixed: {old[:40]}...")
    else:
        print(f"Not found: {old[:40]}...")

f.write_text(content, "utf-8")
print("Done.")
