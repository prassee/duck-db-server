# Build context must be the repo root so both directories are accessible:
#   docker build -f quicksilver-cube/Dockerfile .
FROM cubejs/cube:latest

USER root

# cubejs/cube is Debian-based — add Python 3 + pip via apt
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install quicksilver Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    "duckdb>=1.5.2" \
    "faker>=40.13.0" \
    "polars>=1.39.3" \
    "psycopg[binary]>=3.3.3" \
    "typer>=0.24.1"

# Copy quicksilver source
COPY quicksilver-container/ /qs/

# Copy cube schema / config (replaces the volume-mounted /cube/conf at build time)
COPY cube/ /cube/conf/

# Combined entrypoint: seed data with quicksilver, then hand off to cube
COPY quicksilver-cube/entrypoint.sh /entrypoint-combined.sh
RUN chmod +x /entrypoint-combined.sh

ENTRYPOINT ["/entrypoint-combined.sh"]
