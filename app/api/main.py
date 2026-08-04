from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from time import perf_counter
from uuid import uuid4

from app.api.routes import documents, generate, health
from app.core.config import settings
from app.core.logging import configure_request_logging


logger = configure_request_logging(settings.log_level)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Logpresso Natural Language Query Assistant",
        version="0.1.0",
        description="Generate validated Logpresso queries from Korean natural language requests.",
    )
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.middleware("http")
    async def log_request(request, call_next):
        request_id = uuid4().hex
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            raise
        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(generate.router, prefix="/api/v1", tags=["query"])
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
