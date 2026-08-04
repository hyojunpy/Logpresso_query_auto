from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, generate, health
from app.core.config import settings


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

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(generate.router, prefix="/api/v1", tags=["query"])
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
