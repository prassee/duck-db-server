#!/bin/sh
set -e

cd /qs

if [ ! -f /duckdb/orders.db ]; then
    echo "==> [quicksilver] orders.db not found, seeding data (first run)..."
    python3 main.py create-orders-table
    echo "==> [quicksilver] Seeding complete."
else
    echo "==> [quicksilver] orders.db already exists, skipping seed."
fi

# python3 main.py create-nyc-taxi-view

echo "==> [quicksilver] Stamping persistent MinIO secret into orders.db..."
python3 -c "
import duckdb
conn = duckdb.connect('/duckdb/orders.db')
conn.execute('INSTALL httpfs; LOAD httpfs;')
conn.execute(\"\"\"
CREATE OR REPLACE PERSISTENT SECRET minio_secret (
    TYPE s3,
    KEY_ID 'admin',
    SECRET 'password',
    ENDPOINT 'minio:9000',
    URL_STYLE 'path',
    USE_SSL false
)
\"\"\")
conn.close()
print('MinIO secret stamped.')
"

echo "==> [cube] Starting Cube.js server..."
cd /cube/conf
exec cubejs server
