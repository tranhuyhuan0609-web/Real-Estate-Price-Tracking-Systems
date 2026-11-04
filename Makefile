# Requires uv (https://docs.astral.sh/uv/). Run from the repository root.
RUN := uv run --frozen
SRC := src tests

.PHONY: help install lock lint format typecheck test cov check clean

help:
	@echo "install    Create .venv from uv.lock"
	@echo "lock       Re-resolve dependencies into uv.lock"
	@echo "lint       ruff check + ruff format --check"
	@echo "format     Apply ruff fixes and formatting"
	@echo "typecheck  mypy (strict)"
	@echo "test       Unit and contract tests"
	@echo "cov        Tests with coverage report"
	@echo "check      lint + typecheck + test (what CI runs)"

install:
	uv sync --frozen

lock:
	uv lock

lint:
	$(RUN) ruff check $(SRC)
	$(RUN) ruff format --check $(SRC)

format:
	$(RUN) ruff check --fix $(SRC)
	$(RUN) ruff format $(SRC)

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest

cov:
	$(RUN) pytest --cov --cov-report=term-missing

check: lint typecheck test

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
