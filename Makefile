.PHONY: install migrations migrate run test cov lint format check

install:
	pip install -r requirements/dev.txt

migrations:
	python manage.py makemigrations accounts integrations deliveries

migrate:
	python manage.py migrate

run:
	python manage.py runserver

test:
	pytest

cov:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

# What CI runs: lint, migrations up to date, tests.
check: lint
	python manage.py makemigrations --check --dry-run
	pytest
