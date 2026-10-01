"""Vercel ASGI entrypoint.

Keep the application implementation in ``server.py`` while exposing a small,
unambiguous top-level FastAPI export for Vercel's Python service detector.
"""
from server import app

