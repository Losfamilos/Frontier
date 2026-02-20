from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from config import settings

app = FastAPI(title=settings.app_name)

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
      <head><title>Nordic Banking Frontier Radar</title></head>
      <body style="font-family: Arial; padding: 40px;">
        <h1>Frontier is running ✅</h1>
        <p><a href="/docs">API docs</a></p>
        <p><a href="/health">Health</a></p>
      </body>
    </html>
    """

@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}

def run_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run("app:app", host=host, port=port, reload=False)
