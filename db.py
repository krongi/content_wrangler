import sqlite3, time, dotenv, os

dotenv.load_dotenv()

DB_PATH = os.getenv("DB_PATH")
def init_db():
    sqlite3
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS processed (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        created_at INTEGER
    ); 
    """)
    cur.execute("""
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
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO potential (id, url, title, score, pull_date) VALUES (?, ?, ?, ?, ?)",
                (uid, url, title, score, int(time.time())))
    con.commit()

def was_processed(con, uid: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT 1 FROM processed WHERE id=?", (uid,))
    return cur.fetchone() is not None

def mark_processed(con, uid: str, url: str, title: str):
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO processed (id, url, title, created_at) VALUES (?, ?, ?, ?)",
                (uid, url, title, int(time.time())))
    con.commit()
