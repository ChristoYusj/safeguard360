import uvicorn
from app.factory import create_app
from app.config.settings import get_settings

app = create_app()
settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=bool(settings.DEBUG),
    )
