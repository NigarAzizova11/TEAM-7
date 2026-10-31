import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import get_settings
from .db import get_engine
from .routers import demo, operator, passenger
from .services.ticker import tick_loop

logging.basicConfig(level=logging.INFO)
WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    task = asyncio.create_task(tick_loop()) if s.sim_autostart else None
    try:
        yield
    finally:
        if task:
            task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="BakuFlow API",
        version="0.1.0",
        description="Hackathon prototipi. Dayanacaqlar REAL; marşrutlar, GPS və demo bildirişləri SİMULYASİYADIR.",
        lifespan=lifespan,
    )
    if s.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origin_list,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.get("/health", tags=["meta"])
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    # Brauzer üçün demo veb səhifə (sərnişin / operator / demo). Mobil tətbiqin əvəzi deyil.
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/web/")

    app.include_router(passenger.router)
    app.include_router(operator.router)
    app.include_router(demo.router)
    return app


app = create_app()
