import duckdb

# connect/create a database file
con = duckdb.connect('data/hmda.db')

# load processed data into the database
con.execute("""
    CREATE OR REPLACE TABLE hmda_ny AS
    SELECT 
        * EXCLUDE (county_code),
        CAST(county_code AS INTEGER) AS county_code
    FROM read_csv_auto('data/processed/2025_processed_NY.txt', delim='|')
""")

# check count of rows
print(con.execute("SELECT COUNT(*) FROM hmda_ny").fetchone())
# look at first 10 rows
print(con.execute("SELECT * FROM hmda_ny LIMIT 10").fetchdf())
# verify the columns that exist
print(con.execute("DESCRIBE hmda_ny").fetchdf())

con.close()