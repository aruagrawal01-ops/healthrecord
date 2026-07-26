from urllib.parse import urlparse

import pg8000.dbapi
from flask import current_app, g


def _connect_params(database_url):
    parsed = urlparse(database_url)
    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
    }


def get_db():
    """Return a request-scoped pg8000 connection (pure-Python driver, no libpq needed)."""
    if "db" not in g:
        g.db = pg8000.dbapi.connect(ssl_context=True, **_connect_params(current_app.config["DATABASE_URL"]))
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _row_to_dict(columns, row):
    return dict(zip(columns, row)) if row is not None else None


def query_all(sql, params=None):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        columns = [col[0] for col in cur.description]
        return [_row_to_dict(columns, row) for row in cur.fetchall()]
    finally:
        cur.close()


def query_one(sql, params=None):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        columns = [col[0] for col in cur.description] if cur.description else []
        return _row_to_dict(columns, cur.fetchone())
    finally:
        cur.close()


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE. Commits and returns RETURNING row if present."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        row = None
        if cur.description:
            columns = [col[0] for col in cur.description]
            row = _row_to_dict(columns, cur.fetchone())
        conn.commit()
        return row
    finally:
        cur.close()


def init_app(app):
    app.teardown_appcontext(close_db)
