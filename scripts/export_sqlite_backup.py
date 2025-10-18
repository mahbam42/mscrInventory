#!/usr/bin/env python3
"""
export_sqlite_backup.py
----------------------------------
Standalone SQLite backup utility for mscrInventory.

✅ Exports all relevant mscrInventory tables to /archive/*.csv
✅ Skips auth/session/migrations tables
✅ Works even if Django can't start (standalone)
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

# ---- CONFIG ----
DB_FILE = Path("db_backup_corrupted.sqlite3")  # or "db.sqlite3"
OUTPUT_DIR = Path("archive/backup_csvs") / f"backup_{datetime.now():%Y%m%d_%H%M%S}"
INCLUDE_PREFIXES = ("mscrInventory_", "auth_", "django_")

# Will uncomment after initial run (also fix comment in line 48)
EXCLUDE_TABLES = {
    "django_migrations",
    #"auth_user",
    #"auth_group",
    #"auth_permission",
    #"auth_user_groups",
    #"auth_user_user_permissions",
    #"auth_group_permissions",
    #"django_admin_log",
    "django_session",
    "django_content_type", 
} 

# ---- MAIN ----
def export_sqlite_tables(db_path: Path, output_dir: Path):
    if not db_path.exists():
        raise FileNotFoundError(f"❌ Database file not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r["name"] for r in cur.fetchall() if r["name"] not in EXCLUDE_TABLES]

    print(f"📦 Found {len(tables)} tables in {db_path.name}")
    exported = 0

    for table in tables:
        if not table.startswith(INCLUDE_PREFIXES):
            continue

        outfile = output_dir / f"{table}.csv"
        print(f"📝 Exporting {table} → {outfile.name}")

        cur.execute(f"PRAGMA table_info({table});")
        headers = [col["name"] for col in cur.fetchall()]
        if not headers:
            print(f"⚠️ Skipping {table} (no columns found)")
            continue

        with open(outfile, "w", encoding="utf-8") as f:
            f.write(",".join(headers) + "\n")
            for row in conn.execute(f"SELECT * FROM {table}"):
                values = []
                for h in headers:
                    val = row[headers.index(h)]
                    if val is None:
                        values.append("")
                    else:
                        s = str(val).replace("\n", "\\n").replace('"', '""')
                        values.append(f'"{s}"')
                f.write(",".join(values) + "\n")

        exported += 1

    conn.close()
    print(f"✅ Export complete: {exported} tables written to {output_dir}")


if __name__ == "__main__":
    try:
        export_sqlite_tables(DB_FILE, OUTPUT_DIR)
    except Exception as e:
        print(f"❌ Error: {e}")
