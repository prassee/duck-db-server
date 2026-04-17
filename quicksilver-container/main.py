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

import time

import psycopg
import typer
from psycopg import sql

app = typer.Typer()


def get_conn():
    return psycopg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        autocommit=True,
        connect_timeout=5,
    )


def wait_for_server(max_retries: int = 30, retry_interval: int = 2):
    for i in range(max_retries):
        try:
            conn = get_conn()
            conn.close()
            return
        except psycopg.Error:
            if i < max_retries - 1:
                print(f"Waiting for myduck server... ({i + 1}/{max_retries})")
                time.sleep(retry_interval)
            else:
                raise


@app.command()
def export_to_parquet(
    repeat: int = typer.Option(1, "--repeat", "-r", help="Number of batches to export"),
):
    """Export fake data to parquet files in ../parquet-data/"""
    import faker
    import polars as pl

    fake = faker.Faker()
    no_of_rows = 10000
    for i in range(repeat):
        data = {
            "id": [j for j in range(no_of_rows)],
            "name": [fake.name() for _ in range(no_of_rows)],
            "email": [fake.email() for _ in range(no_of_rows)],
            "address": [fake.address() for _ in range(no_of_rows)],
            "phone_number": [fake.phone_number() for _ in range(no_of_rows)],
        }
        df = pl.DataFrame(data)
        print(f"Exporting batch {i + 1}/{repeat} to parquet...")
        file_name = f"../parquet-data/user_entries_{i + 1}.parquet"
        df.write_parquet(file_name)


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
    s3_endpoint = "localhost:9000"
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


@app.command()
def add_table_nyc_taxi():
    """Create nyc_taxi table from S3 parquet files"""
    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        try:
            cur.execute("SET memory_limit = '2GB';")
            cur.execute("SET temp_directory = '/myduck/tmp/';")
            cur.execute("SET preserve_insertion_order = false;")
            cur.execute("""
            CREATE OR REPLACE TABLE nyc_taxi AS
            SELECT * FROM read_parquet('s3://quicksilver/nyctaxi/*.parquet');""")
            print("Created nyc_taxi table")
            cur.execute(" CHECKPOINT;")
        except Exception as e:
            print(f"Error: {e}")
            raise
    print("Done")


@app.command()
def add_table_hot():
    """Create users_hot table from S3 parquet files"""
    wait_for_server()
    conn = get_conn()
    year = [2022, 2023, 2024]
    month = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    i_year = year[0]
    i_month = month[10], month[11]
    with conn.cursor() as cur:
        try:
            # print("Created nyc table")
            # cur.execute("""
            # CREATE OR REPLACE TABLE nyc_taxi_hv AS
            # SELECT * FROM read_parquet(['s3://quicksilver/nyctaxihv/fhvhv_tripdata_2024-01.parquet', 's3://quicksilver/nyctaxihv/fhvhv_tripdata_2024-02.parquet']);""")
            # cur.execute("""checkpoint;""")
            cur.execute("SET memory_limit = '2GB';")
            cur.execute("SET temp_directory = '/myduck/tmp/';")
            cur.execute("SET preserve_insertion_order = false;")
            file_1 = f"s3://quicksilver/nyctaxihv/fhvhv_tripdata_{i_year}-{i_month[0]}.parquet"
            cur.execute(
                """
                INSERT INTO nyc_taxi_hv
                SELECT * FROM read_parquet(%s);
                """,
                (file_1,),
            )
            cur.execute("checkpoint;")

            file_2 = f"s3://quicksilver/nyctaxihv/fhvhv_tripdata_{i_year}-{i_month[1]}.parquet"
            cur.execute(
                """
                INSERT INTO nyc_taxi_hv
                SELECT * FROM read_parquet(%s);
                """,
                (file_2,),
            )
            cur.execute("checkpoint;")

        except Exception as e:
            print(f"Error: {e}")
            raise
    print("Done")


@app.command()
def list_all_tables():
    """List all tables and views in public schema"""
    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, 'BASE TABLE' as table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            UNION ALL
            SELECT table_name, 'VIEW' as table_type
            FROM information_schema.views
            WHERE table_schema = 'public';
            """)
        tables = cur.fetchall()
        if not tables:
            print("No tables/views found in public schema")
        else:
            print("Tables and views in the database:")
            for table in tables:
                print(f"  {table[0]} ({table[1]})")


@app.command()
def drop_and_vacuum(
    object_type: str = typer.Argument(..., help="Object type: table or view"),
    name: str = typer.Argument(..., help="Object name"),
):
    """Drop one table/view by name, then vacuum and checkpoint."""
    obj = object_type.strip().lower()
    if obj not in {"table", "view"}:
        raise typer.BadParameter("object_type must be 'table' or 'view'")

    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        drop_stmt = sql.SQL("DROP {} IF EXISTS {};").format(
            sql.SQL("TABLE" if obj == "table" else "VIEW"),
            sql.Identifier(name),
        )
        cur.execute(drop_stmt)
        print(f"Dropped {obj} {name}")

        cur.execute("VACUUM;")
        print("Vacuum completed")

        cur.execute("FORCE CHECKPOINT;")
        print("Checkpoint completed")

    print("Done")


if __name__ == "__main__":
    app()
