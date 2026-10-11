# One command each for backend and frontend (see README.md).
PY := backend/.venv/bin/python

.PHONY: install backend frontend test e2e docs clean

install:
	python3 -m venv backend/.venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r backend/requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest -q

e2e:
	cd frontend && npm run e2e

docs:
	cd backend && .venv/bin/python -m app.docs.generate

clean:
	rm -rf backend/.numba_cache backend/.pytest_cache backend/data
