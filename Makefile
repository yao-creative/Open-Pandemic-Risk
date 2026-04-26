SHELL := /bin/bash

.PHONY: test test-unit test-contract test-integration test-live test-e2e-live test-ci test-debug-ingest

test:
	cd backend && uv run pytest -m "unit or integration_local"

test-unit:
	cd backend && uv run pytest -m "unit"

test-contract:
	cd backend && uv run pytest -m "contract"

test-integration:
	cd backend && uv run pytest -m "integration_local"

test-live:
	cd backend && uv run pytest -m "integration_live"

test-e2e-live:
	cd backend && uv run pytest -m "integration_live" -q

test-ci:
	cd backend && uv run pytest -m "unit or integration_local"

test-debug-ingest:
	cd backend && uv run pytest tests/test_ingest.py -q
