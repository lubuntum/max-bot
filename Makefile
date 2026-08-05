.PHONY: build up down logs clean restart shell

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f bot

clean:
	docker-compose down -v
	rm -f users.db  # Remove database (optional)
	docker system prune -f

restart: down up

shell:
	docker-compose exec bot /bin/bash

status:
	docker-compose ps