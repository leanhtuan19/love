"""WSGI entry point for PythonAnywhere's Web tab.

Add the project directory to sys.path in PythonAnywhere's generated WSGI file,
then import ``application`` from this module. Private storage keeps server.py's
default path outside the repository, shared with ``python server.py init-password``.
Set LOVEDAYS_PUBLIC_ORIGIN explicitly for EU accounts or a custom hostname.
"""
import os
from pathlib import Path

from server import create_app


os.environ.setdefault("LOVEDAYS_COOKIE_SECURE", "true")
os.environ.setdefault("LOVEDAYS_SQLITE_JOURNAL_MODE", "DELETE")
os.environ.setdefault("LOVEDAYS_PUBLIC_ORIGIN", f"https://{Path.home().name}.pythonanywhere.com")

application = create_app()
