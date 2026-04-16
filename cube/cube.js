const { DuckDBDriver } = require("@cubejs-backend/duckdb-driver");

// S3/MinIO credentials injected into every DuckDB session that needs S3 access.
const MINIO_INIT_SQL = `
  INSTALL httpfs; LOAD httpfs;
  CREATE SECRET IF NOT EXISTS minio_secret (
    TYPE s3,
    KEY_ID 'admin',
    SECRET 'password',
    ENDPOINT 'minio:9000',
    URL_STYLE 'path',
    USE_SSL false
  );
`;

// Map data source names to their .db file paths.
// Add new entries here to register additional DuckDB databases.
const DATA_SOURCES = {
    default: { databasePath: "/duckdb/orders.db" },
    nyc_taxi: { databasePath: "/duckdb/nyc_taxi.db", initSql: MINIO_INIT_SQL },
};

module.exports = {
    dbType: "duckdb",

    driverFactory: ({ dataSource }) => {
        const config = DATA_SOURCES[dataSource] || DATA_SOURCES.default;
        return new DuckDBDriver(config);
    },
};
