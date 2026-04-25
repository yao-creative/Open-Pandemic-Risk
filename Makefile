SHELL := /bin/bash

.PHONY: test test-unit test-contract test-integration test-live test-ci test-debug-ingest

test:
	cd backend && uv run pytest -m "unit or contract or integration_local"

test-unit:
	cd backend && uv run pytest -m "unit"

test-contract:
	cd backend && uv run pytest -m "contract"

test-integration:
	cd backend && uv run pytest -m "integration_local"

test-live:
	@if [ -z "$$PROMED_API_KEY" ]; then \
		echo "PROMED_API_KEY is required for test-live"; \
		exit 1; \
	fi
	cd backend && uv run pytest -m "integration_live"

test-ci:
	cd backend && uv run pytest -m "unit or contract or integration_local"
	@if [ -z "$$PROMED_API_KEY" ]; then \
		echo "PROMED_API_KEY is required for integration_live in CI"; \
		exit 1; \
	fi
	cd backend && uv run pytest -m "integration_live"

test-debug-ingest:
	cd backend && uv run pytest tests/test_ingest.py -q
