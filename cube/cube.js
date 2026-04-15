const { DuckDBDriver } = require("@cubejs-backend/duckdb-driver");

module.exports = {
    dbType: "duckdb",

    driverFactory: () =>
        new DuckDBDriver({
            databasePath: process.env.CUBEJS_DB_DUCKDB_DATABASE_PATH || "/duckdb/orders.db",
        }),
};
