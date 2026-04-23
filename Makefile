.PHONY: test test-python test-go test-ts lint up down build clean

test: test-python test-go test-ts
	@echo "All tests passed!"

test-python:
	cd gateway && pip install -r requirements.txt -q && pytest -v

test-go:
	cd processor && go test -v ./...

test-ts:
	cd dashboard && npm install --silent && npm test

lint: lint-python lint-go lint-ts
	@echo "All lints passed!"

lint-python:
	cd gateway && flake8 --max-line-length=120 --exclude=__pycache__ .

lint-go:
	cd processor && go vet ./...

lint-ts:
	cd dashboard && npx eslint src/

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local
	rm -rf dashboard/node_modules dashboard/dist
	rm -rf gateway/__pycache__ gateway/.pytest_cache
	rm -f processor/processor
