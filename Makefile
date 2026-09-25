.PHONY: seed run web dev test test-cov lint format format-check typecheck docker-build check clean

seed:
	python -m scripts.seed

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd web && npm install && npm run dev

dev: seed
	@echo "Backend: make run (this shell)  |  Frontend: make web (another shell)"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

format-check:
	ruff format --check src/ tests/

typecheck:
	mypy src/

docker-build:
	docker build -t ai20k-app .

check: lint format-check test-cov

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +