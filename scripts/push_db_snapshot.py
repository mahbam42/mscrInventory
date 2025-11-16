#!/usr/bin/env python3
"""
Create a sanitized mscrInventory data snapshot and copy it to staging.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shlex
import subprocess
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
MANAGE_PY = BASE_DIR / "manage.py"


class StepError(RuntimeError):
    """Raised when a step fails."""


def run(cmd: list[str], *, cwd: pathlib.Path | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command and raise on failure."""
    cwd = cwd or BASE_DIR
    print(f"$ {' '.join(shlex.quote(part) for part in cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=capture, text=True)
    if result.returncode != 0:
        if capture:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
        raise StepError(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")
    return result


def ensure_paths(snapshot_path: pathlib.Path) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not MANAGE_PY.exists():
        raise StepError(f"manage.py not found at {MANAGE_PY}")


def purge_import_data(python_bin: str) -> None:
    run([python_bin, str(MANAGE_PY), "purge_import_data", "--include-logs"])


def dump_snapshot(python_bin: str, snapshot_path: pathlib.Path) -> None:
    with snapshot_path.open("w", encoding="utf-8") as handle:
        print(f"Writing snapshot to {snapshot_path}")
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
        raise StepError("dumpdata failed")
    if snapshot_path.stat().st_size == 0:
        raise StepError("Snapshot file is empty")


def transfer_snapshot(snapshot_path: pathlib.Path, remote: str, remote_path: str) -> None:
    remote_target = f"{remote}:{remote_path.rstrip('/')}/"
    run(["scp", str(snapshot_path), remote_target])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-name",
        default=f"mscr_snapshot_{dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json",
        help="Destination file name inside snapshot directory",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(BASE_DIR / "archive" / "snapshots"),
        help="Directory for local snapshots",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter to use for Django management commands",
    )
    parser.add_argument(
        "--remote",
        default="staging",
        help="SSH host alias for staging server",
    )
    parser.add_argument(
        "--remote-path",
        default="~/projects/mscrInventory",
        help="Directory on staging to copy the snapshot into",
    )
    parser.add_argument(
        "--skip-purge",
        action="store_true",
        help="Skip purge_import_data step",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_path = pathlib.Path(os.path.expanduser(args.snapshot_dir)) / args.snapshot_name

    print("== Preparing snapshot path ==")
    ensure_paths(snapshot_path)

    if not args.skip_purge:
        print("== Step 1/3: Purging import data ==")
        purge_import_data(args.python_bin)
    else:
        print("== Step 1/3: Purge skipped ==")

    print("== Step 2/3: Dumping mscrInventory data ==")
    dump_snapshot(args.python_bin, snapshot_path)

    print("== Step 3/3: Copying snapshot to staging ==")
    transfer_snapshot(snapshot_path, args.remote, args.remote_path)

    print(
        "Snapshot ready:\n"
        f"  local: {snapshot_path}\n"
        f"  remote: {args.remote}:{args.remote_path.rstrip('/')}/{snapshot_path.name}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StepError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
