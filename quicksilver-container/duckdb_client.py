import duckdb

MINIO_ENDPOINT = "localhost:9000"
S3_ACCESS_KEY = "admin"
S3_SECRET_KEY = "password"
WAREHOUSE = "s3://warehouse/"


def get_connection():
    con = duckdb.connect()

    con.execute(f"""
    INSTALL httpfs;
    LOAD httpfs;

    INSTALL iceberg;
    LOAD iceberg;

    SET s3_endpoint='{MINIO_ENDPOINT}';
    SET s3_access_key_id='{S3_ACCESS_KEY}';
    SET s3_secret_access_key='{S3_SECRET_KEY}';
    SET s3_use_ssl=false;
    SET s3_url_style='path';
    """)

    return con


def create_iceberg_table(table_name: str):
    con = get_connection()

    # location = f"{WAREHOUSE}/default/{table_name}"

    # Step 1: Create in DuckDB
    # con.execute(f"""
    # CREATE TABLE {table_name} AS
    # SELECT 1 AS id, 'initial row' AS name;
    # """)
    #
    # Step 2: Export as Iceberg
    # con.execute(f"""
    # EXPORT DATABASE '{location}'
    # (FORMAT ICEBERG);
    # """)
    #
    # con.execute(f""" COPY {table_name} TO '{location}' (FORMAT ICEBERG); """)
    con.execute(
        """INSERT INTO read_iceberg('s3://warehouse/default/id_series_dim-2d77110d0e7e4d509e4d53b16c539b69') SELECT 1 as id , 'hello' as name"""
    )


if __name__ == "__main__":
    create_iceberg_table("id_series_dim")
    print("Iceberg table created and exported to MinIO!")
