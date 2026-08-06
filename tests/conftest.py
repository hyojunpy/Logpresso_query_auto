import os


# Local .env may enable a real provider; unit tests stay deterministic and offline.
os.environ.setdefault("LLM_PROVIDER", "mock")
