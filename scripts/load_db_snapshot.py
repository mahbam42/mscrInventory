#!/usr/bin/env python3
"""
Load a pushed snapshot on staging and restart the local dev server.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time

BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
MANAGE_PY = BASE_DIR / "manage.py"


class StepError(RuntimeError):
    """Raised when an operation fails."""


def run(cmd: list[str], *, cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cwd = cwd or BASE_DIR
    print(f"$ {' '.join(shlex.quote(part) for part in cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if check and result.returncode != 0:
        raise StepError(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")
    return result


def stop_server(port: int) -> None:
    """Terminate any Django runserver process bound to the port."""
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, check=False)
    except FileNotFoundError:  # pragma: no cover
        raise StepError("lsof is required to detect running server processes")

    pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]
    if not pids:
        print(f"No process found on port {port}")
        return
    print(f"Stopping processes on port {port}: {', '.join(pids)}")
    for pid in pids:
        run(["kill", "-TERM", pid], check=False)
    # Give processes a moment to exit gracefully.
    time.sleep(2)


def backup_current_db(python_bin: str, backup_path: pathlib.Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with backup_path.open("w", encoding="utf-8") as handle:
        print(f"Backing up current data to {backup_path}")
        proc = subprocess.run(
            [
                python_bin,
                str(MANAGE_PY),
                "dumpdata",
                "mscrInventory",
                "--natural-foreign",
                "--indent",
                "2",
            ],
            cwd=str(BASE_DIR),
            stdout=handle,
        )
    if proc.returncode != 0:
        raise StepError("Failed to dump current database")


def load_snapshot(python_bin: str, snapshot_path: pathlib.Path) -> None:
    if not snapshot_path.exists():
        raise StepError(f"Snapshot {snapshot_path} does not exist")
    run([python_bin, str(MANAGE_PY), "loaddata", str(snapshot_path)])


def run_tests(pytest_bin: str) -> None:
    run([pytest_bin, "-v"])


def archive_snapshot(snapshot_path: pathlib.Path, archive_dir: pathlib.Path) -> pathlib.Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = archive_dir / snapshot_path.name
    print(f"Archiving snapshot to {archived}")
    shutil.move(str(snapshot_path), archived)
    return archived


def restart_server(python_bin: str, host: str, port: int, log_path: pathlib.Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [python_bin, str(MANAGE_PY), "runserver", f"{host}:{port}"]
    print(f"Starting Django server on {host}:{port} (logs -> {log_path})")
    log_file = open(log_path, "a", encoding="utf-8")
    subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp,  # detach so the server keeps running
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="Path to snapshot file to load")
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter for manage.py commands",
    )
    parser.add_argument(
        "--pytest-bin",
        default="pytest",
        help="Pytest executable",
    )
    parser.add_argument(
        "--archive-dir",
        default=str(BASE_DIR / "archive" / "loaded_snapshots"),
        help="Directory where loaded snapshots should be archived",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(BASE_DIR / "archive"),
        help="Directory where current DB backups should be stored",
    )
    parser.add_argument(
        "--host",
        default="10.0.0.109",
        help="Host/IP for runserver",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for runserver",
    )
    parser.add_argument(
        "--log-file",
        default=str(BASE_DIR / "archive" / "logs" / "runserver_staging.log"),
        help="Location for runserver stdout/stderr",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest run (not recommended)",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Load data without restarting Django runserver",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_path = pathlib.Path(os.path.expanduser(args.snapshot)).resolve()
    archive_dir = pathlib.Path(os.path.expanduser(args.archive_dir))
    backup_dir = pathlib.Path(os.path.expanduser(args.backup_dir))
    log_path = pathlib.Path(os.path.expanduser(args.log_file))

    print("== Step 1/7: Stop any running Django server ==")
    stop_server(args.port)

    print("== Step 2/7: Pull latest code ==")
    run(["git", "pull", "--ff-only"])

    print("== Step 3/7: Backup current database ==")
    backup_name = f"preload_{dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    backup_path = backup_dir / backup_name
    backup_current_db(args.python_bin, backup_path)

    print("== Step 4/7: Load snapshot ==")
    load_snapshot(args.python_bin, snapshot_path)

    print("== Step 5/7: Archive snapshot ==")
    archived_path = archive_snapshot(snapshot_path, archive_dir)

    if args.skip_tests:
        print("== Step 6/7: Tests skipped ==")
    else:
        print("== Step 6/7: Run pytest ==")
        run_tests(args.pytest_bin)

    if args.no_restart:
        print("== Step 7/7: Restart skipped ==")
    else:
        print("== Step 7/7: Restart Django ==")
        restart_server(args.python_bin, args.host, args.port, log_path)

    print("Load complete.")
    print(f"Backup stored at: {backup_path}")
    print(f"Snapshot archived at: {archived_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StepError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
