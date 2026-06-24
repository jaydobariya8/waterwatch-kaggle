# WaterWatch — developer shortcuts.
.PHONY: help setup install run dev test eval mcp docker clean

PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

help:
	@echo "WaterWatch make targets:"
	@echo "  make setup    create venv + install core deps"
	@echo "  make run      run the app at http://localhost:8080"
	@echo "  make test     run the pytest suite"
	@echo "  make eval     run the evaluation harness"
	@echo "  make mcp      run the standalone MCP server (needs 'mcp' extra)"
	@echo "  make docker   build the Cloud Run container image"
	@echo "  make clean    remove caches and the local store"

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

install: setup

run:
	$(BIN)/uvicorn waterwatch.main:app --reload --port 8080

dev: run

test:
	$(BIN)/python -m pytest -q

eval:
	$(BIN)/python -m eval.run_eval

mcp:
	$(BIN)/python -m mcp_server.server

docker:
	docker build -t waterwatch:latest .

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ .waterwatch_store.json
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
