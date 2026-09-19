import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.api.strategy_routes import router as strategy_router
from app.config import settings
from app.data.base import AdjustmentChanged, ProviderError
from app.database.repository import Repository
from app.services.market import MarketService

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def create_app(database_path: Path | None = None, providers=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.repo = Repository(database_path or settings.db_path)
        app.state.market = MarketService(app.state.repo, providers)
        yield

    app = FastAPI(title="Local Stock Research", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_origin_only(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method == "POST"
            and origin
            and origin
            not in {
                f"http://localhost:{settings.frontend_port}",
                f"http://127.0.0.1:{settings.frontend_port}",
                f"http://localhost:{settings.api_port}",
                f"http://127.0.0.1:{settings.api_port}",
            }
        ):
            return JSONResponse(status_code=403, content={"detail": "仅允许本地研究工作台发起操作"})
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{settings.frontend_port}",
            f"http://127.0.0.1:{settings.frontend_port}",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse(status_code=422, content={"detail": "; ".join(e["msg"] for e in exc.errors())})

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        return JSONResponse(
            status_code=409 if isinstance(exc, AdjustmentChanged) else 502, content={"detail": str(exc)}
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unexpected API error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "服务器处理失败，请查看后端日志后重试"})

    app.include_router(router)
    app.include_router(strategy_router)
    return app


app = create_app()
