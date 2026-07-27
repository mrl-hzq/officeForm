from __future__ import annotations

import pymysql
import pymysql.cursors
from flask import g, current_app


def get_db() -> pymysql.connections.Connection:
    if "db" not in g:
        cfg = current_app.config
        g.db = pymysql.connect(
            host=cfg["DB_HOST"],
            port=cfg["DB_PORT"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            database=cfg["DB_NAME"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    return g.db


def close_db(e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql: str, params=None) -> list[dict]:
    cursor = get_db().cursor()
    cursor.execute(sql, params or ())
    return cursor.fetchall()


def query_one(sql: str, params=None) -> dict | None:
    cursor = get_db().cursor()
    cursor.execute(sql, params or ())
    return cursor.fetchone()


def execute(sql: str, params=None) -> int:
    cursor = get_db().cursor()
    cursor.execute(sql, params or ())
    return cursor.rowcount
