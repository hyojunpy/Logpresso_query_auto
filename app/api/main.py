from fastapi import FastAPI

from app.api.routes import documents, generate, health
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Logpresso Natural Language Query Assistant",
        version="0.1.0",
        description="Generate validated Logpresso queries from Korean natural language requests.",
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(generate.router, prefix="/api/v1", tags=["query"])
    return app


app = create_app()


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}

