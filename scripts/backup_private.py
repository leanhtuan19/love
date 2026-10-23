"""Make a consistent private archive without importing or migrating the application.

Run in the application's virtualenv. Output must be outside the repository and
the data directory. The archive contains credentials and must stay private.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
import zipfile

from filelock import FileLock


ROOT = Path(__file__).resolve().parents[1]


def backup_private(directory, output, repository=None):
    directory = Path(directory).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    repositories = {ROOT}
    if repository is not None:
        repository = Path(repository).expanduser().resolve()
        if not repository.is_dir():
            raise ValueError("Choose the existing application repository directory")
        repositories.add(repository)
    if not directory.is_dir() or not (directory / "auth.sqlite3").is_file():
        raise ValueError("Choose the existing private data directory containing auth.sqlite3")
    if any(directory == root or root in directory.parents for root in repositories):
        raise ValueError("Private data must be outside the repository")
    if output == directory or directory in output.parents or any(output == root or root in output.parents for root in repositories):
        raise ValueError("Backup output must be outside the repository and private data directory")
    if output.exists():
        raise FileExistsError("Choose a new backup filename; existing backups are preserved")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, pending = tempfile.mkstemp(prefix=".lovedays-backup-", dir=str(output.parent))
    os.close(descriptor)
    try:
        # A separate SQLite reader can back up the committed snapshot while the
        # writer reservation stops changes to journal/account/settings tables.
        with FileLock(str(directory / "letters.lock"), timeout=15):
            with closing(sqlite3.connect(str(directory / "auth.sqlite3"), timeout=15, isolation_level=None)) as freeze:
                freeze.execute("BEGIN IMMEDIATE")
                try:
                    with tempfile.TemporaryDirectory(prefix="lovedays-snapshot-") as temporary:
                        snapshot = Path(temporary) / "auth.sqlite3"
                        with closing(sqlite3.connect(str(directory / "auth.sqlite3"), timeout=15)) as source:
                            with closing(sqlite3.connect(str(snapshot))) as destination:
                                source.backup(destination)
                        with zipfile.ZipFile(pending, "w", compression=zipfile.ZIP_STORED) as archive:
                            archive.write(snapshot, "auth.sqlite3")
                            for path in sorted(directory.rglob("*")):
                                if path.is_symlink():
                                    raise ValueError("Private store contains a symbolic link; inspect it before backup")
                                if not path.is_file():
                                    continue
                                if path.name.startswith(("auth.sqlite3", ".pending-")) or path.name.endswith(".lock"):
                                    continue
                                archive.write(path, path.relative_to(directory).as_posix())
                finally:
                    freeze.rollback()
        with open(pending, "r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(pending, output)
        return output
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, help="Existing private directory, never the repository")
    parser.add_argument("--output", help="New ZIP path outside public/source/data directories")
    parser.add_argument("--repository", help="Application checkout; required when this helper is copied outside it")
    arguments = parser.parse_args()
    default_output = Path.home() / "lovedays-backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8] + ".zip")
    print(backup_private(arguments.data_dir, arguments.output or default_output, arguments.repository))
