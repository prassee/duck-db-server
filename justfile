default:
    @just --list

start:
    docker-compose up -d

stop:
    docker-compose down

logs:
    docker-compose logs -f

mysql:
    mysql -h 127.0.0.1 -P 3306 -u root

psql:
    psql -h 127.0.0.1 -p 5432 -U postgres

run-quicksilver:
    cd quicksilver-container && uv run main.py

drop-vacuum:
    cd quicksilver-container && uv run main.py drop-and-vacuum

list-tables:
    cd quicksilver-container && uv run main.py list-all-tables

add-hot:
    cd quicksilver-container && uv run main.py add-table-hot

add-warm:
    cd quicksilver-container && uv run main.py add-table-warm

create-union:
    cd quicksilver-container && uv run main.py create-union-view

export-parquet:
    cd quicksilver-container && uv run main.py export-to-parquet