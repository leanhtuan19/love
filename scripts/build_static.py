"""Build an allowlisted static artifact; never publish backend code or private data."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
MARKER = ".lovedays-static-build"
EXTENSIONS = {".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
              ".ico", ".mp3", ".ogg", ".wav", ".ttf", ".woff", ".woff2"}


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("script", "img", "audio", "source") and values.get("src"):
            self.urls.append(values["src"])
        if tag == "link" and values.get("href"):
            self.urls.append(values["href"])


def validate_references():
    parser = References()
    parser.feed((OUTPUT / "index.html").read_text(encoding="utf-8"))
    references = [(OUTPUT / "index.html", url) for url in parser.urls]
    for css in OUTPUT.rglob("*.css"):
        references.extend((css, value) for value in re.findall(
            r"url\(\s*['\"]?([^)'\"\s]+)", css.read_text(encoding="utf-8")))
    for source, url in references:
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            continue
        if parts.path.startswith("/"):
            raise ValueError("Absolute asset URL breaks repository subpaths: " + parts.path)
        target = (source.parent / unquote(parts.path)).resolve()
        if OUTPUT not in target.parents or not target.is_file():
            raise ValueError("Missing or unsafe asset: " + str(source.relative_to(OUTPUT)) + " -> " + url)


def build(backend_origin=None):
    if backend_origin:
        parsed = urlsplit(backend_origin)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("--backend-origin must be an HTTPS origin without credentials, path or query")
        backend_origin = backend_origin.rstrip("/")
    # Only our generated directory can be replaced. Never remove user source.
    if OUTPUT.is_symlink() or OUTPUT.resolve().parent != ROOT:
        raise ValueError("Unsafe output directory")
    if OUTPUT.exists():
        if not (OUTPUT / MARKER).is_file():
            raise ValueError("_site exists without the build marker; move it before building")
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    (OUTPUT / MARKER).write_text("Generated public assets only.\n", encoding="utf-8")
    (OUTPUT / ".nojekyll").touch()
    shutil.copyfile(ROOT / "index.html", OUTPUT / "index.html")
    for folder in ("main", "fonts"):
        for source in (ROOT / folder).rglob("*"):
            relative = source.relative_to(ROOT)
            if source.is_symlink() or not source.is_file() or any(part.startswith(".") for part in relative.parts):
                continue
            if source.suffix.lower() not in EXTENSIONS and relative.as_posix() != "fonts/OFL-Lora.txt":
                continue
            destination = OUTPUT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    validate_references()
    if backend_origin:
        config = {"version": 2, "framework": None, "rewrites": [{
            "source": "/api/:path*", "destination": backend_origin + "/api/:path*"
        }]}
        (OUTPUT / "vercel.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-origin", help="Optional HTTPS backend for Vercel external API rewrites")
    args = parser.parse_args()
    print("Public artifact:", build(args.backend_origin))
