version: '3.8'

services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: max-schedule-bot
    restart: unless-stopped

    # Environment variables from .env file
    env_file:
      - .env

    # Mount only the SQLite database file
    volumes:
      - ./users.db:/app/users.db  # Persist the SQLite database

    # Network configuration
    networks:
      - bot-network

networks:
  bot-network:
    driver: bridge