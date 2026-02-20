from fastapi.responses import HTMLResponse

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
