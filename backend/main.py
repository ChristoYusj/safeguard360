"""
SafeGuard 360 Backend
Entry point for the FastAPI application
"""
import uvicorn
from app.factory import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
