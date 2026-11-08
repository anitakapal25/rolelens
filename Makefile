# RoleLens developer commands. PYTHON can be overridden, e.g. `make test PYTHON=python3`.
PYTHON ?= ../.venv/bin/python

.PHONY: help test eval eval-private chroma backend frontend

help:
	@echo "make test          backend unit/integration tests (no network)"
	@echo "make eval          golden-set eval on the committed sample documents (real API calls, ~\$$0.2)"
	@echo "make eval-private  same, on your own documents in samples/golden.private.yaml (gitignored)"
	@echo "make chroma        start the vector DB (docker compose)"
	@echo "make backend       run the API on :8000 with reload"
	@echo "make frontend      run the Vite dev server on :5173"

test:
	cd backend && $(PYTHON) -m pytest -q

eval:
	cd backend && $(PYTHON) -m app.eval.run app/eval/golden.yaml

eval-private:
	@test -f samples/golden.private.yaml || (echo "samples/golden.private.yaml not found" && exit 1)
	cd backend && $(PYTHON) -m app.eval.run ../samples/golden.private.yaml

chroma:
	docker compose up -d chroma

backend:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev
