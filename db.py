import psycopg2
import psycopg2.extras
from flask import current_app, g


def get_db():
    """Return a request-scoped psycopg2 connection (rows come back as dicts)."""
    if "db" not in g:
        g.db = psycopg2.connect(
            current_app.config["DATABASE_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_all(sql, params=None):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql, params=None):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE. Commits and returns RETURNING row if present."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = None
        if cur.description:
            row = cur.fetchone()
        conn.commit()
        return row


def init_app(app):
    app.teardown_appcontext(close_db)
