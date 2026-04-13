-- Views are lazy — DuckDB only scans what Metabase requests (filters/limits pushed down to parquet)
CREATE OR REPLACE VIEW nyctaxi_hv AS
    SELECT * FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet');