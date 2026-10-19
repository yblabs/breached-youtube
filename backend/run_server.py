#!/usr/bin/env python
from pathlib import Path
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
        app_dir=str(APP_DIR.parent),
    )
