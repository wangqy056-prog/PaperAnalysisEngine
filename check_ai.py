import sqlite3
c = sqlite3.connect("backend/papers.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
papers = c.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
print("Tables:", tables)
print("Papers total:", papers)
for t in tables:
    try:
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {cnt} rows")
    except:
        pass
c.close()
