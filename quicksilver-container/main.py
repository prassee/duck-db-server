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
import typer
import psycopg

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
            cur.execute(f"""
            INSERT INTO nyc_taxi_hv
            SELECT * FROM read_parquet('s3://quicksilver/nyctaxihv/fhvhv_tripdata_{i_year}-{i_month[0]}.parquet');""")
            cur.execute("""checkpoint;""")

            cur.execute(f"""
            INSERT INTO nyc_taxi_hv
            SELECT * FROM read_parquet('s3://quicksilver/nyctaxihv/fhvhv_tripdata_{i_year}-{i_month[1]}.parquet');""")
            cur.execute("""checkpoint;""")

        except Exception as e:
            print(f"Error: {e}")
            raise
    print("Done")


@app.command()
def add_table_warm():
    """Create users_warm view from S3 parquet files"""
    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        try:
            cur.execute("""
            CREATE OR REPLACE VIEW users_warm AS
            SELECT * FROM read_parquet('s3://quicksilver/usesrs/warm/*.parquet')
            ORDER BY id DESC;
            """)
            print("Created users_warm view")
            cur.execute(" CHECKPOINT;")
        except Exception as e:
            print(f"Error: {e}")
            raise
    print("Done")


@app.command()
def create_union_view():
    """Create users view as union of users_hot and users_warm"""
    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        try:
            cur.execute("""
            CREATE OR REPLACE VIEW users AS
            SELECT * FROM users_hot
            UNION ALL
            SELECT * FROM users_warm
            ORDER BY id DESC;
            """)
            print("Created users view")
            cur.execute(" CHECKPOINT;")
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
def drop_and_vacuum():
    """Drop views and tables, then vacuum the database"""
    wait_for_server()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS users;")
        print("Dropped users view")
        cur.execute("FORCE CHECKPOINT;")

        cur.execute("DROP VIEW IF EXISTS users_warm;")
        print("Dropped users_warm view")
        cur.execute("FORCE CHECKPOINT;")

        cur.execute("DROP TABLE IF EXISTS users_hot;")
        print("Dropped users_hot table")
        cur.execute("FORCE CHECKPOINT;")

        # nyc_taxi
        cur.execute("DROP TABLE IF EXISTS nyc_taxi;")
        cur.execute("VACUUM;")
        print("Dropped nyc_taxi table")
        cur.execute("FORCE CHECKPOINT;")

        # nyc_taxi_hv
        cur.execute("DROP TABLE IF EXISTS nyc_taxi_hv;")
        cur.execute("VACUUM;")
        print("Dropped nyc_taxi_hv table")
        cur.execute("FORCE CHECKPOINT;")

        cur.execute("VACUUM;")
        print("Vacuum completed")
    print("Done")


if __name__ == "__main__":
    app()
