#!/bin/sh
set -e

if [ ! -f /duckdb/orders.db ]; then
    echo "==> [quicksilver] orders.db not found, seeding data (first run)..."
    cd /qs
    python3 main.py create-orders-table
    echo "==> [quicksilver] Seeding complete."
else
    echo "==> [quicksilver] orders.db already exists, skipping seed."
fi

echo "==> [cube] Starting Cube.js server..."
exec cubejs server
