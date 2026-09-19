import sys
import os

# Add backend directory to sys.path
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from api.main import app as backend_app

# Vercel routes API requests to /api/..., so we mount the backend app at /api
app = FastAPI()

@app.get("/")
def read_root():
    return {
        "error": "Vercel routing issue", 
        "message": "The Vercel Serverless Function is handling the root URL (/) instead of serving the Vite frontend. Please ensure the Output Directory in your Vercel Project Settings is set to 'frontend/dist'."
    }

app.mount("/api", backend_app)
