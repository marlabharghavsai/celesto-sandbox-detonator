import os
import re
import socket
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@ledger:5432/ledger")

SQLITE_PATH = Path(__file__).resolve().parent.parent.parent / "ledger.db"
SEED_SQL_PATH = Path(__file__).resolve().parent.parent.parent / "seeds" / "01_runs.sql"

_POSTGRES_CHECKED: Optional[bool] = None

def _is_postgres_reachable(db_url: str) -> bool:
    global _POSTGRES_CHECKED
    if _POSTGRES_CHECKED is not None:
        return _POSTGRES_CHECKED

    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        _POSTGRES_CHECKED = False
        return False

    # On Windows host outside Docker, service name 'ledger' will fail DNS resolution and stall
    if os.name == "nt" and "@ledger" in db_url and not os.path.exists("/.dockerenv"):
        _POSTGRES_CHECKED = False
        return False

    match = re.search(r"@([^:/]+)(?::(\d+))?", db_url)
    if not match:
        _POSTGRES_CHECKED = False
        return False

    host = match.group(1)
    port = int(match.group(2)) if match.group(2) else 5432
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect((host, port))
        s.close()
        _POSTGRES_CHECKED = True
        return True
    except Exception:
        _POSTGRES_CHECKED = False
        return False

def get_connection():
    db_url = os.getenv("DATABASE_URL", DATABASE_URL)
    if _is_postgres_reachable(db_url):
        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=1)
            return conn, "postgres"
        except Exception:
            pass

    # Use SQLite fallback
    conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"

def init_db():
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        if engine == "sqlite":
            cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id VARCHAR(64) PRIMARY KEY,
                sandbox_name VARCHAR(64) NOT NULL UNIQUE,
                problem_id VARCHAR(64) NOT NULL,
                state VARCHAR(32) NOT NULL,
                execution_target VARCHAR(32) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs(sandbox_name);")
            cur.execute("""
            INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
            VALUES ('run-seeddemo1', 'sbx-seeddemo1', 'problem-detonator-001', 'deleted', 'celesto_sandbox')
            ON CONFLICT (run_id) DO NOTHING;
            """)
            conn.commit()
        else:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id VARCHAR(64) PRIMARY KEY,
                sandbox_name VARCHAR(64) NOT NULL UNIQUE,
                problem_id VARCHAR(64) NOT NULL,
                state VARCHAR(32) NOT NULL,
                execution_target VARCHAR(32) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs(sandbox_name);")
            cur.execute("""
            INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
            VALUES ('run-seeddemo1', 'sbx-seeddemo1', 'problem-detonator-001', 'deleted', 'celesto_sandbox')
            ON CONFLICT (run_id) DO NOTHING;
            """)
            conn.commit()
    finally:
        conn.close()

# Always ensure db is initialized
init_db()

def get_all_runs() -> List[Dict[str, Any]]:
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT run_id, sandbox_name, problem_id, state, execution_target, created_at FROM runs ORDER BY created_at ASC;")
        rows = cur.fetchall()
        runs = []
        for r in rows:
            if engine == "sqlite":
                runs.append({
                    "run_id": r["run_id"],
                    "sandbox_name": r["sandbox_name"],
                    "problem_id": r["problem_id"],
                    "state": r["state"],
                    "execution_target": r["execution_target"],
                    "created_at": str(r["created_at"]) if r["created_at"] else None
                })
            else:
                runs.append({
                    "run_id": r[0],
                    "sandbox_name": r[1],
                    "problem_id": r[2],
                    "state": r[3],
                    "execution_target": r[4],
                    "created_at": str(r[5]) if r[5] else None
                })
        return runs
    finally:
        conn.close()

def insert_run(run_data: Dict[str, Any]) -> Dict[str, Any]:
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        if engine == "sqlite":
            cur.execute("""
            INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                sandbox_name=excluded.sandbox_name,
                problem_id=excluded.problem_id,
                state=excluded.state,
                execution_target=excluded.execution_target;
            """, (run_data["run_id"], run_data["sandbox_name"], run_data["problem_id"], run_data["state"], run_data["execution_target"]))
            conn.commit()
        else:
            cur.execute("""
            INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                sandbox_name=EXCLUDED.sandbox_name,
                problem_id=EXCLUDED.problem_id,
                state=EXCLUDED.state,
                execution_target=EXCLUDED.execution_target;
            """, (run_data["run_id"], run_data["sandbox_name"], run_data["problem_id"], run_data["state"], run_data["execution_target"]))
            conn.commit()
        return run_data
    finally:
        conn.close()
