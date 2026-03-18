.PHONY: install lint typecheck test run docker-up docker-down

PYTHON = python3
VENV = .venv
VENV_BIN = $(VENV)/bin

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -e .[dev]

lint:
	$(VENV_BIN)/ruff check .

typecheck:
	$(VENV_BIN)/mypy app tests

test:
	PYTHONPATH=. $(VENV_BIN)/pytest

run:
	$(VENV_BIN)/uvicorn app.main:create_app --factory --reload

docker-up:
	docker compose up --build

docker-down:
	docker compose down
