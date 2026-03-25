from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.repositories.videos import init_db
from app.routes.api import router as api_router
from app.routes.pages import router as pages_router

app = FastAPI(title="ContentMachine", description="Part Scout operations console")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(api_router)
app.include_router(pages_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
