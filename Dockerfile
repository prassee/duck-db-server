FROM python:3.11-slim

RUN pip install duckdb

WORKDIR /app

COPY duckdb_server.py .

# Create data directory
RUN mkdir -p /data

CMD ["python", "duckdb_server.py"]
