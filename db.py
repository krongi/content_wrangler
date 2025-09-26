import sqlite3, time

def init_db(db_path: str):
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS processed (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS potential (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        score INTEGER,
        pull_date INTEGER
    );
    """)
    con.commit()
    return con

def potential_articles(con, uid: str, url: str, title: str, score: int):
    con.execute(
        "INSERT OR IGNORE INTO potential (id, url, title, score, pull_date) VALUES (?, ?, ?, ?, ?)",
        (uid, url, title, score, int(time.time()))
    )
    con.commit()

def was_processed(con, uid: str) -> bool:
    return con.execute("SELECT 1 FROM processed WHERE id=?", (uid,)).fetchone() is not None

def mark_processed(con, uid: str, url: str, title: str):
    con.execute(
        "INSERT OR IGNORE INTO processed (id, url, title, created_at) VALUES (?, ?, ?, ?)",
        (uid, url, title, int(time.time()))
    )
    con.commit()
