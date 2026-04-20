"""HTTP server for the React frontend.

Serves:
  /api/*  — JSON API for runs, shorts, uploads, publishing, presets
  /       — static React build from web/dist/ (when it exists)

Entry point is server.py at the project root: `python server.py`.
"""
