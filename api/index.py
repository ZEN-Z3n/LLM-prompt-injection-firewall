import sys
import os

# Add backend directory to sys.path
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from api.main import app as backend_app

# Vercel routes API requests to /api/..., so we mount the backend app at /api
app = FastAPI()
app.mount("/api", backend_app)
