from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from scripts.backup_private import backup_private, ROOT


class BackupTests(unittest.TestCase):
    def test_backup_preserves_json_images_keys_and_committed_sqlite(self):
        with tempfile.TemporaryDirectory(prefix="lovedays-backup-test-") as temporary:
            directory = Path(temporary) / "private"
            directory.mkdir()
            (directory / "images").mkdir()
            original = json.dumps({"schemaVersion": 1, "letters": []}, ensure_ascii=False).encode("utf-8")
            (directory / "letters.json").write_bytes(original)
            (directory / "images" / "sample.png").write_bytes(b"image bytes")
            (directory / "secret.key").write_bytes(b"private bytes")
            (directory / "letters.lock").touch()
            (directory / ".pending-aborted").write_bytes(b"incomplete")
            with closing(sqlite3.connect(str(directory / "auth.sqlite3"))) as connection:
                connection.execute("CREATE TABLE sample (content TEXT)")
                connection.execute("INSERT INTO sample VALUES(?)", ("Nhật ký tiếng Việt",))
                connection.commit()
            output = backup_private(directory, Path(temporary) / "backup.zip")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"auth.sqlite3", "letters.json", "images/sample.png", "secret.key"})
                self.assertEqual(archive.read("letters.json"), original)
                snapshot = Path(temporary) / "restored.sqlite3"
                snapshot.write_bytes(archive.read("auth.sqlite3"))
            with closing(sqlite3.connect(str(snapshot))) as connection:
                self.assertEqual(connection.execute("SELECT content FROM sample").fetchone()[0], "Nhật ký tiếng Việt")
            self.assertEqual((directory / "letters.json").read_bytes(), original)
            with self.assertRaises(FileExistsError):
                backup_private(directory, output)

    def test_refuses_public_or_recursive_backup_destinations(self):
        with tempfile.TemporaryDirectory(prefix="lovedays-backup-test-") as temporary:
            directory = Path(temporary)
            with closing(sqlite3.connect(str(directory / "auth.sqlite3"))):
                pass
            for output in (directory / "backup.zip", ROOT / "backup.zip"):
                with self.assertRaises(ValueError):
                    backup_private(directory, output)
            checkout = directory / "checkout"
            checkout.mkdir()
            private = directory / "private"
            private.mkdir()
            with closing(sqlite3.connect(str(private / "auth.sqlite3"))):
                pass
            # A helper downloaded outside the checkout must still protect the
            # actual source directory passed by the deployment instructions.
            with self.assertRaises(ValueError):
                backup_private(private, checkout / "backup.zip", repository=checkout)
            self.assertFalse((checkout / "backup.zip").exists())


if __name__ == "__main__":
    unittest.main()
