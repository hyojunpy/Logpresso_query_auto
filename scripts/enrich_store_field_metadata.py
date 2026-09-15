from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.store_field_metadata import enrich_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill Store schema display names and aliases")
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    enrich_payload(payload)
    args.catalog.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
