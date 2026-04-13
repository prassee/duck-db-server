-- Load extensions (pre-downloaded, mounted at /root/.duckdb/extensions)
LOAD icu;
LOAD httpfs;

-- Configure S3 access to MinIO
CREATE SECRET IF NOT EXISTS minio_secret (
    TYPE s3,
    KEY_ID 'minioadmin',
    SECRET 'minioadmin',
    ENDPOINT 'minio:9000',
    URL_STYLE 'path',
    USE_SSL false
);

-- Memory safety for 4GB container limit
SET memory_limit = '2GB';
SET max_temp_directory_size = '10GB';
SET temp_directory = '/tmp/duckdb_spill';

-- Recreate dashboard source views on every connection.
-- These are lazy parquet scans, so data is not fully loaded into RAM.
CREATE OR REPLACE VIEW nyctaxi AS
    SELECT * FROM read_parquet('s3://quicksilver/nyctaxi/*.parquet');

CREATE OR REPLACE VIEW nyctaxi_hv AS
    SELECT * FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet');
