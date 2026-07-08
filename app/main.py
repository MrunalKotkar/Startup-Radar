"""
Minimal API server bridging the React frontend (src/main.jsx) to Person 3's
detail synthesis (detail/synthesis.py).

This closes the integration gap found during review: the React app's detail
panel was calling a client-side mock (buildMockDetail in src/lib/relevance.js)
because nothing exposed get_startup_detail() over HTTP for the browser to call.

Run with: python app/main.py
Vite's dev server proxies /api/* to this on port 8000 (see vite.config.js),
so the frontend can just fetch("/api/detail?...") with no CORS setup needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request
from flask_cors import CORS

from detail.synthesis import get_startup_detail

app = Flask(__name__)
CORS(app)


@app.get("/api/detail")
def detail():
    name = request.args.get("name", "").strip()
    website = request.args.get("website", "").strip()
    if not name or not website:
        return jsonify({"error": "name and website query params are required"}), 400

    return jsonify(get_startup_detail(name, website))


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(port=8000, debug=True)
