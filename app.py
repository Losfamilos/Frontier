from fastapi import FastAPI
import uvicorn

from config import settings


app = FastAPI(title=settings.app_name)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


def run_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run("app:app", host=host, port=port, reload=False)
