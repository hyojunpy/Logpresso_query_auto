SENSITIVE_KEYS = ("api_key", "token", "password", "secret", "authorization")


def redact(value: str) -> str:
    lowered = value.lower()
    if any(key in lowered for key in SENSITIVE_KEYS):
        return "***REDACTED***"
    return value

