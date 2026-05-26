import os
import duckdb

# Start from a clean file each run — DuckDB doesn't shrink files after
# DROP TABLE / CREATE OR REPLACE, so re-running on an existing file would
# accumulate dead space. Deleting first guarantees the output matches the
# actual data size and makes the script idempotent.
DB_PATH = 'data/hmda.db'
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# connect/create a database file
con = duckdb.connect(DB_PATH)

# Step 1: Load CSV as-is (everything stays VARCHAR per read_csv_auto)
con.execute("""
    CREATE OR REPLACE TABLE hmda_raw AS
    SELECT * FROM read_csv_auto('data/processed/2025_processed_NY.txt', delim='|')
""")

# Step 2: For each VARCHAR column, check whether most of its non-null values
# look numeric. If yes, cast it to DOUBLE; otherwise leave it as VARCHAR.
columns_info = con.execute("DESCRIBE hmda_raw").fetchall()

select_parts = []
for row in columns_info:
    col_name, col_type = row[0], row[1]

    if col_type != 'VARCHAR':
        select_parts.append(f'"{col_name}"')
        continue

    stats = con.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE "{col_name}" IS NOT NULL AND "{col_name}" != '') AS non_null,
            COUNT(*) FILTER (WHERE TRY_CAST("{col_name}" AS DOUBLE) IS NOT NULL) AS castable
        FROM hmda_raw
    """).fetchone()
    non_null, castable = stats

    # Treat as numeric if >=90% of non-null values cast cleanly
    if non_null > 0 and castable / non_null >= 0.9:
        select_parts.append(f'TRY_CAST("{col_name}" AS DOUBLE) AS "{col_name}"')
    else:
        select_parts.append(f'"{col_name}"')

# Step 3: Rebuild the final table with proper types,
# and still cast county_code to INTEGER as before.
con.execute(f"""
    CREATE OR REPLACE TABLE hmda_ny AS
    SELECT
        * EXCLUDE (county_code),
        CAST(county_code AS INTEGER) AS county_code
    FROM (
        SELECT {', '.join(select_parts)} FROM hmda_raw
    )
""")

# Cleanup the staging table
con.execute("DROP TABLE hmda_raw")


# Quick sanity checks, counts, and peek at the data
print(con.execute("SELECT COUNT(*) FROM hmda_ny").fetchone())
print(con.execute("SELECT * FROM hmda_ny LIMIT 10").fetchdf())
print(con.execute("DESCRIBE hmda_ny").fetchdf())

con.execute("CHECKPOINT")
con.close()