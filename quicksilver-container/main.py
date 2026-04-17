"""
DuckDB Analytics Orchestrator: S3-to-PVC Hybrid Rolling Window

This script manages a 90-day analytical window using a tiered storage strategy
to optimize performance on resource-constrained hosts (4-core / 8GB RAM).

Architecture Logic:
1. HOT TIER (0-30 Days): Materialized as a local DuckDB TABLE on PVC.
   - Uses 'ORDER BY' during creation to enable Zone Map pruning for fast random access.
   - Provides sub-second latency for Metabase deep-drills.
2. WARM TIER (31-90 Days): Defined as a DuckDB VIEW pointing to S3 Parquet.
   - Zero local storage footprint.
   - Leverages HTTP Range Requests and Parquet metadata for efficient scans.
3. HYBRID LAYER: A 'UNION ALL' VIEW combining both tiers into a single source
   for Metabase dashboards.

Operational Safeguards:
- Idempotency: Uses 'CREATE OR REPLACE' to ensure daily runs don't duplicate data.
- Resource Management: Explicitly triggers 'FORCE CHECKPOINT' after DDLs to
  merge the Write-Ahead Log (WAL) and reclaim PVC space, preventing OOM kills.
- Scaling: Limits memory and threads to prevent DuckDB from saturating the host.

Dependencies:
- MyDuckServer (MySQL Protocol)
- DuckDB 'httpfs' extension for S3/Minio communication.
"""

import typer

app = typer.Typer()


@app.command()
def create_orders_table(
    row_count: int = typer.Option(
        5000, "--rows", "-r", help="Number of rows to generate"
    ),
):
    """Create orders table with synthetic data in duckdb"""
    import random
    import uuid
    from datetime import datetime, timedelta

    import faker

    import duckdb

    fake = faker.Faker()
    output_path = "../duckdb/orders.db"

    print(f"Generating {row_count:,} orders...")
    conn = duckdb.connect(output_path)

    conn.execute("DROP TABLE IF EXISTS orders")

    conn.execute("""
    CREATE TABLE orders (
        order_id VARCHAR PRIMARY KEY,
        customer_name VARCHAR,
        customer_email VARCHAR,
        product_name VARCHAR,
        product_category VARCHAR,
        quantity INTEGER,
        unit_price DECIMAL(10,2),
        total_amount DECIMAL(10,2),
        order_status VARCHAR,
        order_date DATE,
        delivery_date DATE,
        shipping_address VARCHAR,
        payment_method VARCHAR
    )
    """)

    categories = [
        "Electronics",
        "Clothing",
        "Home & Garden",
        "Sports",
        "Books",
        "Toys",
        "Food",
        "Beauty",
    ]
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    payment_methods = ["credit_card", "debit_card", "paypal", "bank_transfer", "cash"]

    batch_size = 100000
    for batch in range(0, row_count, batch_size):
        batch_end = min(batch + batch_size, row_count)
        data = []
        for i in range(batch, batch_end):
            qty = random.randint(1, 10)
            unit_price = round(random.uniform(10, 1000), 2)
            total = round(qty * unit_price, 2)
            order_date = datetime.now() - timedelta(days=random.randint(0, 365))
            delivery_date = order_date + timedelta(days=random.randint(1, 14))

            data.append(
                (
                    str(uuid.uuid4()),
                    fake.name(),
                    fake.email(),
                    fake.catch_phrase()[:100],
                    random.choice(categories),
                    qty,
                    unit_price,
                    total,
                    random.choice(statuses),
                    order_date.date(),
                    delivery_date.date(),
                    fake.address().replace("\n", ", ")[:200],
                    random.choice(payment_methods),
                )
            )

        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            data,
        )

        print(f"  Inserted {batch_end:,}/{row_count:,} rows...")

    conn.execute("CREATE INDEX idx_order_date ON orders(order_date)")
    conn.execute("CREATE INDEX idx_customer_email ON orders(customer_email)")
    conn.execute("CREATE INDEX idx_product_category ON orders(product_category)")

    conn.close()
    print(f"Created orders table with {row_count:,} rows in {output_path}")


@app.command()
def create_nyc_taxi_view():
    """Create nyc_taxi_rides VIEW in ../duckdb/nyc_taxi.db pointing to S3/MinIO parquet files"""
    import duckdb

    output_path = "../duckdb/nyc_taxi.db"
    s3_endpoint = "minio:9000"
    s3_access_key = "admin"
    s3_secret_key = "password"
    s3_path = "s3://nyc-taxi/*.parquet"

    print(f"Creating nyc_taxi_rides view in {output_path} → {s3_path}")
    conn = duckdb.connect(output_path)

    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"""
        CREATE SECRET IF NOT EXISTS minio_secret (
            TYPE s3,
            KEY_ID '{s3_access_key}',
            SECRET '{s3_secret_key}',
            ENDPOINT '{s3_endpoint}',
            URL_STYLE 'path',
            USE_SSL false
        );
    """)

    conn.execute(f"""
        CREATE OR REPLACE VIEW nyc_taxi_rides AS
        SELECT * FROM read_parquet('{s3_path}');
    """)

    conn.close()
    print("Done — nyc_taxi_rides view created")


if __name__ == "__main__":
    app()
