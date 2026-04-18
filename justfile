default:
    @just --list

start:
    docker-compose up -d

build:
    docker-compose build --no-cache

stop:
    docker-compose down

logs:
    docker-compose logs -f

create-orders:
    cd quicksilver-container && uv run main.py create-orders-table

create-orders-view:
    cd quicksilver-container && uv run main.py create-orders-view

generate-parquet:
    cd quicksilver-container && uv run main.py generate-orders-parquet

load-parquet:
    cd quicksilver-container && uv run main.py load-orders-parquet