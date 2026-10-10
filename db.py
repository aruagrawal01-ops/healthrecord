from urllib.parse import parse_qs, urlparse

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
        # Neon requires TLS; a local pgAdmin server usually has none (?sslmode=disable).
        "ssl_context": None if parse_qs(parsed.query).get("sslmode") == ["disable"] else True,
    }


def get_db():
    """Return a request-scoped pg8000 connection (pure-Python driver, no libpq needed)."""
    if "db" not in g:
        conn = pg8000.dbapi.connect(**_connect_params(current_app.config["DATABASE_URL"]))
        # CURRENT_DATE etc. follow the hospital's clock, not the server's (Neon runs in UTC).
        cur = conn.cursor()
        cur.execute("SET TIME ZONE 'Asia/Kolkata'")
        cur.close()
        conn.commit()
        g.db = conn
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


DatabaseError = pg8000.dbapi.DatabaseError


def error_message(exc):
    """The human-readable part of a PostgreSQL error (e.g. a RAISE EXCEPTION from a procedure)."""
    info = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
    return info.get("M", str(exc))


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE/CALL. Commits and returns RETURNING row if present; rolls back on error."""
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
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_app(app):
    app.teardown_appcontext(close_db)
