.PHONY: setup run build clean test

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

setup-mlx: setup
	$(PIP) install -e ".[local-whisper-mlx]"

run:
	$(PYTHON) -m openmic

build:
	$(PYTHON) setup.py py2app

clean:
	rm -rf build dist .eggs *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

test:
	$(PYTHON) -m pytest tests/ -v
