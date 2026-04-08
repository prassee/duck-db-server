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
