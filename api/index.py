"""
Vercel serverless entry point for the FastAPI backend.
Vercel looks for /api/index.py at the project root.
"""

import sys
import os

# ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api.routes import app  # noqa: F401 — Vercel imports `app`
