"""Scalable DDL and incremental loader via Metabase API.

Usage examples:
  uv run metabase_loader.py bootstrap-models
  uv run metabase_loader.py init-incremental-hv
  uv run metabase_loader.py incremental-load-hv
  uv run metabase_loader.py list-relations

Environment variables:
  METABASE_URL        default: http://localhost:3000
  METABASE_USER       default: admin@example.com
  METABASE_PASSWORD   default: password
  METABASE_DB_ID      default: 2
"""

from __future__ import annotations

import os
import time
from textwrap import dedent

import requests
import typer

app = typer.Typer()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
METABASE_USER = os.getenv("METABASE_USER", "admin@example.com")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD", "password")
METABASE_DB_ID = int(os.getenv("METABASE_DB_ID", "2"))


def wait_for_metabase(max_retries: int = 30, retry_interval: int = 3) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(f"{METABASE_URL}/api/health", timeout=5)
            if resp.ok and resp.json().get("status") == "ok":
                return
        except requests.RequestException:
            pass

        if attempt == max_retries:
            raise RuntimeError("Metabase did not become ready in time")

        print(f"Waiting for Metabase... ({attempt}/{max_retries})")
        time.sleep(retry_interval)


def get_session() -> str:
    resp = requests.post(
        f"{METABASE_URL}/api/session",
        json={"username": METABASE_USER, "password": METABASE_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def run_sql(session: str, sql: str) -> dict:
    payload = {
        "database": METABASE_DB_ID,
        "type": "native",
        "native": {"query": dedent(sql).strip()},
    }
    resp = requests.post(
        f"{METABASE_URL}/api/dataset",
        headers={"X-Metabase-Session": session},
        json=payload,
        timeout=900,
    )
    resp.raise_for_status()

    body = resp.json()
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body


@app.command()
def bootstrap_models() -> None:
    """Create or refresh persistent semantic views for dashboards."""
    wait_for_metabase()
    session = get_session()

    statements = [
        """
        CREATE OR REPLACE VIEW nyctaxi AS
        SELECT *
        FROM read_parquet('s3://quicksilver/nyctaxi/*.parquet');
        """,
        """
        CREATE OR REPLACE VIEW nyctaxi_hv AS
        SELECT *
        FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet');
        """,
    ]

    for sql in statements:
        run_sql(session, sql)

    print("Bootstrapped: nyctaxi, nyctaxi_hv")


@app.command()
def init_incremental_hv() -> None:
    """Create table + manifest used for file-level incremental loads."""
    wait_for_metabase()
    session = get_session()

    run_sql(
        session,
        """
        CREATE TABLE IF NOT EXISTS nyctaxi_hv_fact AS
        SELECT *
        FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet', filename=true)
        LIMIT 0;
        """,
    )

    run_sql(
        session,
        """
        CREATE TABLE IF NOT EXISTS nyctaxi_hv_ingested_files (
          file_path VARCHAR PRIMARY KEY,
          ingested_at TIMESTAMP DEFAULT NOW()
        );
        """,
    )

    run_sql(
        session,
        """
        CREATE OR REPLACE VIEW nyctaxi_hv AS
        SELECT * EXCLUDE (filename)
        FROM nyctaxi_hv_fact;
        """,
    )

    print("Initialized incremental objects for nyctaxi_hv")


@app.command()
def incremental_load_hv() -> None:
    """Load only unseen parquet files into nyctaxi_hv_fact."""
    wait_for_metabase()
    session = get_session()

    run_sql(
        session,
        """
        INSERT INTO nyctaxi_hv_fact
        SELECT src.*
        FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet', filename=true) AS src
        LEFT JOIN nyctaxi_hv_ingested_files f
          ON src.filename = f.file_path
        WHERE f.file_path IS NULL;
        """,
    )

    run_sql(
        session,
        """
        INSERT INTO nyctaxi_hv_ingested_files (file_path)
        SELECT DISTINCT src.filename
        FROM read_parquet('s3://quicksilver/nyctaxihv/*.parquet', filename=true) AS src
        LEFT JOIN nyctaxi_hv_ingested_files f
          ON src.filename = f.file_path
        WHERE f.file_path IS NULL;
        """,
    )

    print("Incremental load complete for nyctaxi_hv_fact")


@app.command()
def list_relations() -> None:
    """List tables and views in main schema."""
    wait_for_metabase()
    session = get_session()

    result = run_sql(
        session,
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY table_type, table_name;
        """,
    )

    for row in result.get("data", {}).get("rows", []):
        print(f"{row[0]} ({row[1]})")


if __name__ == "__main__":
    app()
