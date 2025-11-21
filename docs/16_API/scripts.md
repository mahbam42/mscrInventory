# Scripts

Utility scripts that support environment maintenance, backups, and local tooling. These are CLI-oriented modules rather than Django management commands.

| Script | Purpose |
| --- | --- |
| `scripts/export_sqlite_backup.py` | Create a timestamped SQLite backup locally. |
| `scripts/import_sqlite_backup.py` | Restore data from an archived CSV snapshot into SQLite (with optional dry-run). |
| `scripts/load_db_snapshot.py` | Fetch and load the latest pushed snapshot into a local dev environment. |
| `scripts/push_db_snapshot.py` | Dump a sanitized snapshot and copy it to a remote host. |
| `scripts/relink_from_backup.py` | Re-link integer foreign keys from CSV backups after a schema change. |
| `scripts/merge_csv.py` | Merge a directory of CSV files into one combined file while skipping duplicate headers. |
| `scripts/dev_square_matcher.py` | Quick interactive helper to exercise the Square matcher on a sample CSV. |
