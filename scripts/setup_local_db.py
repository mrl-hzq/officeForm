"""
One-time setup: creates the officeform database, user, and tables on local MySQL.
Run: python scripts/setup_local_db.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

ROOT_HOST = os.environ.get("DB_SERVER") or os.environ.get("DB_HOST", "127.0.0.1")
ROOT_PORT = int(os.environ.get("DB_PORT", "3306"))
ROOT_USER = os.environ.get("MYSQL_ROOT_USER", "root")
ROOT_PASS = os.environ.get("MYSQL_ROOT_PASSWORD", "root")

APP_DB = os.environ.get("DB_SCHEMA") or os.environ.get("DB_NAME", "officeform")
APP_USER = os.environ.get("DB_USER", "officeform")
APP_PASS = os.environ.get("DB_PASSWORD", "officeform_pass")


def main():
    print(f"Connecting to MySQL at {ROOT_HOST}:{ROOT_PORT}...")
    conn = pymysql.connect(
        host=ROOT_HOST, port=ROOT_PORT,
        user=ROOT_USER, password=ROOT_PASS,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    cur = conn.cursor()

    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{APP_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    print(f"Database '{APP_DB}' ready.")

    cur.execute(f"CREATE USER IF NOT EXISTS '{APP_USER}'@'%' IDENTIFIED BY '{APP_PASS}'")
    cur.execute(f"GRANT ALL PRIVILEGES ON `{APP_DB}`.* TO '{APP_USER}'@'%'")
    cur.execute("FLUSH PRIVILEGES")
    print(f"User '{APP_USER}' ready.")

    cur.execute(f"USE `{APP_DB}`")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            worker_id     VARCHAR(20) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NULL,
            role          ENUM('worker','admin') NOT NULL DEFAULT 'worker',
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'users'
          AND COLUMN_NAME = 'role'
    """, (APP_DB,))
    if cur.fetchone()["count"] == 0:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN role ENUM('worker','admin') NOT NULL DEFAULT 'worker'
            AFTER password_hash
        """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            worker_id                VARCHAR(20) PRIMARY KEY,
            name                     VARCHAR(255) NOT NULL,
            designation              VARCHAR(255),
            department               VARCHAR(255),
            house_tel                VARCHAR(50),
            other_tel                VARCHAR(50),
            evaluator_name           VARCHAR(255),
            annual_leave_entitlement DECIMAL(5,1) DEFAULT 0,
            annual_leave_taken       DECIMAL(5,1) DEFAULT 0,
            employment_type          ENUM('permanent','contract') DEFAULT 'permanent',
            employment_start_date    DATE,
            employment_end_date      DATE,
            profile_complete         BOOLEAN DEFAULT FALSE,
            updated_at               DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id                  VARCHAR(30) PRIMARY KEY,
            worker_id           VARCHAR(20) NOT NULL,
            form_type           VARCHAR(10) NOT NULL,
            form_name           VARCHAR(100),
            leave_type          VARCHAR(20),
            start_date          DATE,
            end_date            DATE,
            duration_days       DECIMAL(4,1),
            affects_al          BOOLEAN DEFAULT FALSE,
            al_days_applied     DECIMAL(4,1) DEFAULT 0,
            is_half_day         BOOLEAN DEFAULT FALSE,
            half_day_period     VARCHAR(2),
            reason              TEXT,
            kpi_month           VARCHAR(7),
            application_date    DATE,
            kpi_data            JSON,
            worker_snapshot     JSON,
            leave_summary       JSON,
            pdf_file_name       VARCHAR(255),
            workbook_file_name  VARCHAR(255),
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
    """)

    cur.execute("SHOW TABLES")
    tables = [list(r.values())[0] for r in cur.fetchall()]
    print(f"Tables created: {tables}")
    conn.close()
    print("Setup complete.")


if __name__ == "__main__":
    main()
