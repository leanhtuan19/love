"""Checks the exact artifact published to static hosting, without backend dependencies."""
from html.parser import HTMLParser
import json
import unittest

from scripts.build_static import ROOT, build


class StaticBuildTests(unittest.TestCase):
    def test_public_artifact_has_assets_but_no_private_or_server_files(self):
        output = build()
        for path in ("index.html", ".nojekyll", "main/js/letters.js", "main/js/mobile.js",
                     "main/css/effects.css", "fonts/Lora-Variable.ttf", "main/music/nhactinhyeu.mp3"):
            self.assertTrue((output / path).is_file(), path)
        for path in ("server.py", "requirements.txt", ".git", ".env", "tests", "docs",
                     "letters.json", "auth.sqlite3", "secret.key", "vercel.json"):
            self.assertFalse((output / path).exists(), path)
        self.assertNotIn("access_token=", (output / "index.html").read_text(encoding="utf-8"))
        class Avatars(HTMLParser):
            def __init__(self):
                super().__init__()
                self.paths = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "img" and attrs.get("class") == "avt":
                    self.paths.append(attrs["src"])
        parser = Avatars()
        parser.feed((output / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(parser.paths), 2)
        for path in parser.paths:
            self.assertEqual((output / path).read_bytes(), (ROOT / path).read_bytes())

    def test_optional_vercel_proxy_does_not_package_python_or_storage(self):
        output = build("https://backend.example/")
        data = json.loads((output / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(data["rewrites"], [{"source": "/api/:path*", "destination": "https://backend.example/api/:path*"}])
        self.assertIsNone(data["framework"])
        self.assertFalse((output / "server.py").exists())

    def test_invalid_backend_origin_cannot_embed_credentials_or_paths(self):
        for origin in ("http://backend.example", "https://name:credential@backend.example",
                       "https://backend.example/api", "https://backend.example?token=value"):
            with self.assertRaises(ValueError):
                build(origin)


if __name__ == "__main__":
    unittest.main()
