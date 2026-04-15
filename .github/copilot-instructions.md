# Copilot Context: DuckDB → Iceberg → Trino Lakehouse

## Purpose

This repository implements a local lakehouse stack where:

* DuckDB is used for ELT / ingestion
* Iceberg is the table format
* MinIO is the object storage (S3-compatible)
* Hive Metastore stores metadata
* Trino serves queries via JDBC
* Metabase is used for analytics

The goal is to:

* Allow programmatic ingestion (Python / Go)
* Ensure all data lands in Iceberg tables
* Make data immediately queryable via Trino and BI tools

---

## Architecture Principles

1. DuckDB is NOT a storage system

   * It is used as a compute engine only
   * Avoid persistent `.duckdb` files unless explicitly required

2. All tables must be Iceberg tables

   * No local DuckDB-managed tables
   * No raw Parquet-only datasets without Iceberg metadata

3. Storage is externalized

   * All data must be written to MinIO (S3)
   * Bucket: `s3://warehouse/`

4. Trino is the serving layer

   * All BI tools connect via Trino
   * Views must be created in Trino, NOT DuckDB

---

## Required DuckDB Session Setup

Every DuckDB session (Python / Go / CLI) MUST execute:

INSTALL httpfs;
LOAD httpfs;

INSTALL iceberg;
LOAD iceberg;

SET s3_endpoint='minio:9000';
SET s3_access_key_id='admin';
SET s3_secret_access_key='password';
SET s3_use_ssl=false;
SET s3_url_style='path';

---

## Table Creation Rules

### ✅ Correct (Iceberg table)

CREATE TABLE default.table_name AS
SELECT * FROM source;

### ❌ Incorrect (local DuckDB table)

CREATE TABLE table_name AS SELECT ...

### ❌ Incorrect (raw parquet without Iceberg)

COPY (SELECT ...) TO 's3://.../file.parquet';

---

## Data Ingestion Pattern

Preferred pattern:

INSERT INTO default.table_name
SELECT * FROM read_parquet('s3://...');

or

CREATE TABLE default.table_name AS
SELECT * FROM read_csv_auto('file.csv');

---

## View Creation Rules

Views must be created using Trino:

Example:
CREATE VIEW iceberg.default.sales_summary AS
SELECT date, SUM(amount) FROM sales GROUP BY date;

Do NOT create views in DuckDB if they need to be shared.

---

## Python Guidelines

* Use duckdb.connect(":memory:") unless persistence is required
* Always initialize S3 + Iceberg before queries
* Avoid staging large datasets locally
* Stream data directly into Iceberg tables

---

## Go Guidelines

* Use go-duckdb driver
* Execute session initialization before any query
* Avoid local file-backed databases

---

## Storage & Disk Safety

* Do not create large local DuckDB tables
* Always write to Iceberg tables in MinIO
* Use temp directories for spill if needed
* Clean up unused `.duckdb` files

---

## Trino Usage

* Catalog: iceberg
* Schema: default (or domain-specific)
* All analytics queries should go through Trino

---

## Naming Conventions (recommended)

* schema = domain (e.g., finance, risk, marketing)
* table = lowercase, underscore separated
* avoid spaces or mixed casing

---

## Common Mistakes to Avoid

* Mixing DuckDB local tables with Iceberg tables
* Forgetting to load Iceberg extension
* Writing data to S3 without Iceberg metadata
* Creating views in DuckDB expecting Trino to see them
* Using different S3 paths between DuckDB and Trino

---

## Expected Behavior

When a table is created via DuckDB:

* Data files are written to MinIO
* Iceberg metadata is created
* Table is registered in Hive Metastore
* Table becomes immediately queryable via Trino

---

## Copilot Instructions

When generating code:

* Always assume Iceberg-backed tables
* Always include DuckDB S3 + Iceberg setup
* Prefer INSERT INTO or CREATE TABLE AS patterns
* Avoid local storage unless explicitly asked
* Generate production-safe, scalable patterns
* Prefer streaming over staging

If unsure:
→ default to writing data into Iceberg tables via DuckDB

---

## Future Extensions (optional)

* Iceberg compaction jobs
* Schema evolution handling
* Partitioning strategies
* Data quality checks before ingestion
* Integration with LakeGPT for SQL generation

---

