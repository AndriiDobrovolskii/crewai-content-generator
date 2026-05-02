"""
Entry point for the GEO Content Generator API server.

Usage (from project root, with uv):
    uv run run_server.py

Or directly:
    python run_server.py
"""
import os
import sys

# Ensure backend package is importable from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    print("🚀 GEO Content Generator API")
    print("   API:      http://localhost:8000")
    print("   Docs:     http://localhost:8000/docs")
    print("   Frontend: http://localhost:5173 (run 'npm run dev' in /frontend)")
    print()
    uvicorn.run(
        "backend.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"],
    )
