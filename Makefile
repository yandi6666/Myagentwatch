# MyAgentWatch — 质量检查与维护命令
# Usage:
#   make check       # lint + test (推荐提交前运行)
#   make lint        # ruff check only
#   make format      # ruff format
#   make test        # run tests
#   make all         # lint + format + test

VENV := /home/openclaw/Desktop/myagentwatch/.venv/bin
PROJECT := /home/openclaw/Desktop/myagentwatch

.PHONY: check lint format test all

check: lint test
	@echo "=== 检查全部通过 ==="

lint:
	$(VENV)/ruff check $(PROJECT)

format:
	$(VENV)/ruff format --check $(PROJECT)

fix:
	$(VENV)/ruff check --fix $(PROJECT)
	$(VENV)/ruff format $(PROJECT)

test:
	$(VENV)/python -m pytest $(PROJECT)/tests/ -v

all: lint format test
	@echo "=== 全部检查通过 ==="
