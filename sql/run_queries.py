"""
run_queries.py
===============
Executes every query in analytical_queries.sql against the SQLite build of
the database and prints/validates results. Used both as a smoke test
(does every query run without error?) and to generate sample output for
the README.
"""
import sqlite3
import re

DB_PATH = "sql/engineering_analytics.db"
QUERIES_PATH = "sql/analytical_queries.sql"


def split_statements(sql_text):
    # Strip full-line comments, then split on ';' while keeping statements together
    lines = [ln for ln in sql_text.splitlines()]
    cleaned = []
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("--"):
            continue
        cleaned.append(ln)
    joined = "\n".join(cleaned)
    statements = [s.strip() for s in joined.split(";") if s.strip()]
    return statements


def main():
    with open(QUERIES_PATH) as f:
        sql_text = f.read()

    statements = split_statements(sql_text)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    n_select = 0
    n_error = 0
    sample_outputs = []

    for i, stmt in enumerate(statements, 1):
        try:
            cur.execute(stmt)
            if stmt.strip().upper().startswith(("SELECT", "WITH")):
                n_select += 1
                rows = cur.fetchmany(5)
                cols = [d[0] for d in cur.description]
                sample_outputs.append((i, cols, rows))
                print(f"[OK] Query block {i}: {len(rows)} sample rows, cols={cols}")
            else:
                conn.commit()
                print(f"[OK] Statement {i}: {stmt.strip().splitlines()[0][:60]}...")
        except Exception as e:
            n_error += 1
            print(f"[ERROR] Statement {i} failed: {e}\n  --> {stmt[:120]}")

    print(f"\nTotal statements executed: {len(statements)}")
    print(f"SELECT/WITH queries: {n_select}")
    print(f"Errors: {n_error}")

    with open("reports/sql_query_sample_output.txt", "w") as f:
        for i, cols, rows in sample_outputs:
            f.write(f"\n--- Query block {i} ---\n")
            f.write(" | ".join(cols) + "\n")
            for r in rows:
                f.write(" | ".join(str(x) for x in r) + "\n")
    print("\nSample output written to reports/sql_query_sample_output.txt")

    conn.close()


if __name__ == "__main__":
    main()
