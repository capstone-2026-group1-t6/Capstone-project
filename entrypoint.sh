#!/bin/sh
set -e

echo "==> Seeding Neo4j graph..."
python scripts/build_graph_index.py || echo "WARN: graph seed failed (non-fatal)"

echo "==> Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
