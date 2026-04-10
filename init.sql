-- Install httpfs extension for reading parquet files from HTTP/HTTPS endpoints
-- httpfs is required to read remote parquet files via HTTP/HTTPS URLs (e.g., from web servers, HTTP-based object storage, or CDN)
INSTALL httpfs;
LOAD httpfs;

-- Initialize S3-compatible storage (MinIO) for backup/restore
CREATE SECRET IF NOT EXISTS (
    TYPE s3,
    KEY_ID 'minioadmin',
    SECRET 'minioadmin',
    ENDPOINT 'minio:9000',
    URL_STYLE 'path',
    USE_SSL false
);

-- Create a sample parquet table for testing
-- COMMENTED: Moved to Python script for dynamic execution after startup
-- CREATE TABLE IF NOT EXISTS sample_data AS
-- SELECT * FROM read_parquet('s3://myduck-backup/*.parquet');



-- 1. Load Required Extensions
INSTALL ducklake;
LOAD ducklake;
INSTALL httpfs;
LOAD httpfs;

-- 2. Configure S3 Access (Pointed to your MinIO container)
SET s3_endpoint='minio:9000';
SET s3_access_key_id='minioadmin';
SET s3_secret_access_key='minioadmin';
SET s3_use_ssl=false;
SET s3_url_style='path';

-- 3. Attach the DuckLake Catalog (Managed by your Postgres container)
ATTACH 'ducklake:catalog' AS my_lake (
    TYPE DUCKLAKE,
    CATALOG_TYPE 'postgresql',
    CONNECTION_STRING 'host=ducklake-catalog dbname=ducklake_metadata user=postgres password=postgres'
);

-- 4. Set Memory Safety for your 4GB limit
SET memory_limit = '2GB';
SET max_temp_directory_size = '10GB';
SET temp_directory = '/tmp/duckdb_spill';
