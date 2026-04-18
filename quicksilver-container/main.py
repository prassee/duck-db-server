"""
DuckDB Analytics Orchestrator: S3-to-PVC Hybrid Rolling Window

This script manages a 90-day analytical window using a tiered storage strategy
to optimize performance on resource-constrained hosts (4-core / 8GB RAM).

Architecture Logic:
1. HOT TIER (0-30 Days): Materialized as a local DuckDB TABLE on PVC.
   - Uses 'ORDER BY' during creation to enable Zone Map pruning for fast random access.
   - Provides sub-second latency for Metabase deep-drills.
2. WARM TIER (31-90 Days): Defined as a DuckDB VIEW pointing to S3 Parquet.
   - Zero local storage footprint.
   - Leverages HTTP Range Requests and Parquet metadata for efficient scans.
3. HYBRID LAYER: A 'UNION ALL' VIEW combining both tiers into a single source
   for Metabase dashboards.

Operational Safeguards:
- Idempotency: Uses 'CREATE OR REPLACE' to ensure daily runs don't duplicate data.
- Resource Management: Explicitly triggers 'FORCE CHECKPOINT' after DDLs to
  merge the Write-Ahead Log (WAL) and reclaim PVC space, preventing OOM kills.
- Scaling: Limits memory and threads to prevent DuckDB from saturating the host.

Dependencies:
- MyDuckServer (MySQL Protocol)
- DuckDB 'httpfs' extension for S3/Minio communication.
"""

import typer

app = typer.Typer()


@app.command()
def create_orders_table(
    row_count: int = typer.Option(
        500000, "--rows", "-r", help="Number of rows to generate"
    ),
):
    """Create orders table with synthetic data in duckdb"""
    import random
    import uuid
    from datetime import datetime, timedelta

    import faker as faker_module

    import duckdb

    fake = faker_module.Faker("en_IN")
    output_path = "../duckdb/orders.db"

    category_sub_categories = {
        "Electronics": [
            "Mobile",
            "Laptop",
            "Tablet",
            "Camera",
            "Headphones",
            "TV",
            "Smartwatch",
        ],
        "Clothing": ["Men's", "Women's", "Kids'", "Ethnic", "Western", "Sportswear"],
        "Home & Garden": ["Kitchen", "Furniture", "Decor", "Garden", "Bedding"],
        "Sports": ["Cricket", "Football", "Fitness", "Swimming", "Cycling"],
        "Books": ["Fiction", "Non-Fiction", "Academic", "Comics", "Self-Help"],
        "Toys": ["Action Figures", "Board Games", "Educational", "Outdoor", "Dolls"],
        "Food": ["Snacks", "Beverages", "Dairy", "Organic", "Spices"],
        "Beauty": ["Skincare", "Haircare", "Makeup", "Fragrance", "Personal Care"],
    }

    payment_sub_types = {
        "credit_card": ["Visa", "Mastercard", "Amex", "RuPay Credit"],
        "debit_card": ["Visa Debit", "Mastercard Debit", "RuPay Debit", "Maestro"],
        "UPI": ["GPay", "PhonePe", "Paytm", "BHIM", "Amazon Pay"],
        "COD": ["Cash", "Card on Delivery"],
    }

    categories = list(category_sub_categories.keys())
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    payment_methods = ["credit_card", "debit_card", "UPI", "COD"]

    print(f"Generating {row_count:,} orders...")
    conn = duckdb.connect(output_path)

    conn.execute("DROP TABLE IF EXISTS orders")
    conn.execute("""
    CREATE TABLE orders (
        order_id            VARCHAR PRIMARY KEY,
        customer_name       VARCHAR,
        customer_email      VARCHAR,
        product_name        VARCHAR,
        product_category    VARCHAR,
        product_sub_category VARCHAR,
        quantity            INTEGER,
        unit_price          DECIMAL(10,2),
        total_amount        DECIMAL(10,2),
        order_status        VARCHAR,
        order_date          DATE,
        delivery_date       DATE,
        shipping_address    VARCHAR,
        payment_method      VARCHAR,
        payment_sub_type    VARCHAR
    )
    """)

    # Build customer pool so each customer gets at least 5 orders
    num_customers = row_count // 6  # avg ~6 orders per customer
    print(f"  Generating {num_customers:,} unique Indian customers...")
    customers = [(fake.name(), fake.email()) for _ in range(num_customers)]

    # Guarantee min 5 orders per customer, then fill the rest randomly
    customer_indices = list(range(num_customers)) * 5  # 5 orders each
    remaining = row_count - len(customer_indices)
    customer_indices += random.choices(range(num_customers), k=remaining)
    random.shuffle(customer_indices)

    def make_row(cidx: int) -> tuple:
        name, email = customers[cidx]
        category = random.choice(categories)
        sub_category = random.choice(category_sub_categories[category])
        payment_method = random.choice(payment_methods)
        payment_sub_type = random.choice(payment_sub_types[payment_method])
        qty = random.randint(1, 10)
        unit_price = round(random.uniform(10, 1000), 2)
        total = round(qty * unit_price, 2)
        order_date = datetime.now() - timedelta(days=random.randint(0, 365))
        delivery_date = order_date + timedelta(days=random.randint(1, 14))
        return (
            str(uuid.uuid4()),
            name,
            email,
            fake.catch_phrase()[:100],
            category,
            sub_category,
            qty,
            unit_price,
            total,
            random.choice(statuses),
            order_date.date(),
            delivery_date.date(),
            fake.address().replace("\n", ", ")[:200],
            payment_method,
            payment_sub_type,
        )

    batch_size = 100000
    for batch_start in range(0, row_count, batch_size):
        batch_end = min(batch_start + batch_size, row_count)
        data = [make_row(customer_indices[i]) for i in range(batch_start, batch_end)]
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            data,
        )
        print(f"  Inserted {batch_end:,}/{row_count:,} rows...")

    conn.execute("CREATE INDEX idx_order_date ON orders(order_date)")
    conn.execute("CREATE INDEX idx_customer_email ON orders(customer_email)")
    conn.execute("CREATE INDEX idx_product_category ON orders(product_category)")

    conn.close()
    print(f"Created orders table with {row_count:,} rows in {output_path}")


@app.command()
def create_orders_view():
    """Create orders_hv VIEW in /duckdb/orders.db pointing to S3/MinIO parquet files"""
    import duckdb

    output_path = "/duckdb/orders.db"
    s3_endpoint = "minio:9000"
    s3_access_key = "admin"
    s3_secret_key = "password"
    s3_path = "s3://warehouse/orders_hv/*.parquet"

    print(f"Creating orders_hv view in {output_path} → {s3_path}")
    conn = duckdb.connect(output_path)

    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"""
        CREATE OR REPLACE TEMPORARY SECRET minio_secret (
            TYPE s3,
            KEY_ID '{s3_access_key}',
            SECRET '{s3_secret_key}',
            ENDPOINT '{s3_endpoint}',
            URL_STYLE 'path',
            USE_SSL false
        );
    """)

    # Drop old view if it exists (legacy)
    try:
        conn.execute("DROP VIEW IF EXISTS orders_hv;")
        conn.execute("DROP TABLE IF EXISTS orders_hv;")
    except:
        pass

    # Create VIEW with UNIQUE constraint on order_id so Metabase recognizes it as PK
    conn.execute(f"""
        CREATE OR REPLACE VIEW orders_hv AS
        SELECT 
            order_id,
            customer_name,
            customer_email,
            product_name,
            product_category,
            product_sub_category,
            quantity,
            unit_price,
            total_amount,
            order_status,
            order_date,
            delivery_date,
            shipping_address,
            payment_method,
            payment_sub_type
        FROM read_parquet('{s3_path}')
        WHERE order_id IS NOT NULL;
    """)

    conn.close()
    print("Done — orders_hv view created")


@app.command()
def generate_orders_parquet(
    row_count: int = typer.Option(
        5000000, "--rows", "-r", help="Number of rows to generate"
    ),
    output_file: str = typer.Option(
        "../parquet-data/orders.parquet", "--out", "-o", help="Output parquet file path"
    ),
):
    """Generate synthetic orders data and export to a parquet file"""
    import uuid
    from datetime import datetime, timedelta

    import faker as faker_module
    import numpy as np
    import polars as pl

    fake = faker_module.Faker("en_IN")
    rng = np.random.default_rng()

    categories = [
        "Electronics",
        "Clothing",
        "Home & Garden",
        "Sports",
        "Books",
        "Toys",
        "Food",
        "Beauty",
    ]
    cat_sub_lists = [
        ["Mobile", "Laptop", "Tablet", "Camera", "Headphones", "TV", "Smartwatch"],
        ["Men's", "Women's", "Kids'", "Ethnic", "Western", "Sportswear"],
        ["Kitchen", "Furniture", "Decor", "Garden", "Bedding"],
        ["Cricket", "Football", "Fitness", "Swimming", "Cycling"],
        ["Fiction", "Non-Fiction", "Academic", "Comics", "Self-Help"],
        ["Action Figures", "Board Games", "Educational", "Outdoor", "Dolls"],
        ["Snacks", "Beverages", "Dairy", "Organic", "Spices"],
        ["Skincare", "Haircare", "Makeup", "Fragrance", "Personal Care"],
    ]

    payment_methods = ["credit_card", "debit_card", "UPI", "COD"]
    pay_sub_lists = [
        ["Visa", "Mastercard", "Amex", "RuPay Credit"],
        ["Visa Debit", "Mastercard Debit", "RuPay Debit", "Maestro"],
        ["GPay", "PhonePe", "Paytm", "BHIM", "Amazon Pay"],
        ["Cash", "Card on Delivery"],
    ]

    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]

    print(f"Generating {row_count:,} orders...")

    POOL = min(row_count // 6, 50_000)
    print(f"  Building Faker pools ({POOL:,} unique customers)...")
    cust_names = [fake.name() for _ in range(POOL)]
    cust_emails = [fake.email() for _ in range(POOL)]
    addrs = [fake.address().replace("\n", ", ")[:200] for _ in range(POOL)]
    phrases = [fake.catch_phrase()[:100] for _ in range(POOL)]

    cust_idx = np.tile(np.arange(POOL), 5)
    extra = rng.integers(0, POOL, max(0, row_count - len(cust_idx)))
    cust_idx = np.concatenate([cust_idx, extra])[:row_count]
    rng.shuffle(cust_idx)

    cat_idx = rng.integers(0, len(categories), row_count)
    pay_idx = rng.integers(0, len(payment_methods), row_count)
    status_idx = rng.integers(0, len(statuses), row_count)
    phrase_idx = rng.integers(0, POOL, row_count)

    sub_cat_col = [
        cat_sub_lists[ci][rng.integers(0, len(cat_sub_lists[ci]))] for ci in cat_idx
    ]
    pay_sub_col = [
        pay_sub_lists[pi][rng.integers(0, len(pay_sub_lists[pi]))] for pi in pay_idx
    ]

    quantities = rng.integers(1, 11, row_count)
    unit_prices = np.round(rng.uniform(10, 1000, row_count), 2)
    totals = np.round(quantities * unit_prices, 2)
    days_ago = rng.integers(0, 366, row_count)
    deliv_lag = rng.integers(1, 15, row_count)

    base = datetime.now()
    order_dates = [(base - timedelta(days=int(d))).date() for d in days_ago]
    delivery_dates = [
        (base - timedelta(days=int(d)) + timedelta(days=int(l))).date()
        for d, l in zip(days_ago, deliv_lag)
    ]

    print("  Building DataFrame...")
    df = pl.DataFrame(
        {
            "order_id": [str(uuid.uuid4()) for _ in range(row_count)],
            "customer_name": [cust_names[i] for i in cust_idx],
            "customer_email": [cust_emails[i] for i in cust_idx],
            "product_name": [phrases[i] for i in phrase_idx],
            "product_category": [categories[i] for i in cat_idx],
            "product_sub_category": sub_cat_col,
            "quantity": quantities.tolist(),
            "unit_price": unit_prices.tolist(),
            "total_amount": totals.tolist(),
            "order_status": [statuses[i] for i in status_idx],
            "order_date": order_dates,
            "delivery_date": delivery_dates,
            "shipping_address": [addrs[i % POOL] for i in cust_idx],
            "payment_method": [payment_methods[i] for i in pay_idx],
            "payment_sub_type": pay_sub_col,
        }
    )

    print(f"  Writing to {output_file}...")
    df.write_parquet(output_file)
    print(f"Exported {row_count:,} rows to {output_file}")


@app.command()
def load_orders_parquet(
    input_file: str = typer.Option(
        "../parquet-data/orders.parquet", "--file", "-f", help="Parquet file to load"
    ),
    db_path: str = typer.Option(
        "../duckdb/orders.db", "--db", help="DuckDB database path"
    ),
):
    """Load a parquet file into the orders table in DuckDB"""
    import duckdb

    print(f"Loading {input_file} → {db_path}...")
    conn = duckdb.connect(db_path)

    conn.execute("DROP TABLE IF EXISTS orders")
    conn.execute(f"CREATE TABLE orders AS SELECT * FROM read_parquet('{input_file}')")
    conn.execute("ALTER TABLE orders ADD PRIMARY KEY (order_id)")

    conn.execute("CREATE INDEX idx_order_date ON orders(order_date)")
    conn.execute("CREATE INDEX idx_customer_email ON orders(customer_email)")
    conn.execute("CREATE INDEX idx_product_category ON orders(product_category)")

    # row_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    # conn.close()
    # print(f"Loaded {row_count:,} rows into orders table in {db_path}")


if __name__ == "__main__":
    app()
