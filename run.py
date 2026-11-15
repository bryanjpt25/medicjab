"""Arranca el servidor local (o en la nube): python run.py"""
import os
import threading
import webbrowser
import uvicorn

# En la nube (Render) se asigna un puerto dinámico en la variable PORT
PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

if __name__ == "__main__":
    # Solo abre el navegador si estamos en tu PC local
    if HOST == "127.0.0.1":
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    
    uvicorn.run("backend.server:app", host=HOST, port=PORT, reload=False)