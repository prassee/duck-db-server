import duckdb

DB_PATH = "/data/analytics.duckdb"

con = duckdb.connect(DB_PATH)

# Load pgwire server
con.execute("INSTALL postgres;")
con.execute("LOAD postgres;")

# Start server
con.execute("""
CALL postgres_start(
    host := '0.0.0.0',
    port := 5432
);
""")

print("DuckDB PostgreSQL server running on port 5432")

# Keep process alive
import time

while True:
    time.sleep(3600)
