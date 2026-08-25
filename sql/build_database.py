"""
build_database.py
==================
Builds the analytics database from schema.sql and loads the cleaned CSVs
from data/processed/. Ships as SQLite (engineering_analytics.db) so the
project runs anywhere with zero setup — the DDL in schema.sql is written
in PostgreSQL-compatible syntax and documented as such; swapping the
connection here for psycopg2/mysql-connector is a ~5-line change (see
README "How to run on Postgres/MySQL").
"""

import sqlite3
import pandas as pd
import re
import os

DB_PATH = "sql/engineering_analytics.db"
SCHEMA_PATH = "sql/schema.sql"
PROCESSED_DIR = "data/processed"

TABLE_LOAD_ORDER = [
    "teams", "developers", "projects", "sprints", "issues",
    "commits", "pull_requests", "code_reviews", "deployments", "releases",
]


def sqlite_compatible_schema(sql_text: str) -> str:
    """Translate the Postgres-flavored DDL to SQLite-compatible DDL."""
    sql_text = re.sub(r"NUMERIC\(\d+,\d+\)", "REAL", sql_text)
    sql_text = sql_text.replace("SMALLINT", "INTEGER")
    sql_text = sql_text.replace("TIMESTAMP", "TEXT")
    sql_text = sql_text.replace("DATE", "TEXT")
    sql_text = re.sub(r"VARCHAR\(\d+\)", "TEXT", sql_text)
    return sql_text


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    with open(SCHEMA_PATH) as f:
        raw_schema = f.read()
    schema = sqlite_compatible_schema(raw_schema)
    cur.executescript(schema)
    print("Schema created.")

    for table in TABLE_LOAD_ORDER:
        df = pd.read_csv(f"{PROCESSED_DIR}/{table}.csv")
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"Loaded {len(df):,} rows into {table}")

    conn.commit()

    # Sanity check row counts
    print("\nRow counts in database:")
    for table in TABLE_LOAD_ORDER:
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n:,}")

    conn.close()
    print(f"\nDatabase built at {DB_PATH}")


if __name__ == "__main__":
    main()
