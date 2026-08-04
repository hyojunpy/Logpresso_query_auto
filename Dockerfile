FROM python:3.12-slim

WORKDIR /app
ENV LLM_PROVIDER=mock \
    RETRIEVAL_LIMIT=8
COPY pyproject.toml requirements.lock README.md ./
COPY app ./app
COPY scripts ./scripts
COPY ui ./ui
RUN mkdir -p docs data
RUN pip install --no-cache-dir -c requirements.lock -e .
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
