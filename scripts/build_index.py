from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.indexer import DocumentIndex


def main() -> None:
    index = DocumentIndex(settings.db_path)
    result = index.rebuild(settings.doc_path)
    print(f"Indexed {result['chunk_count']} chunks from {result['document']}")


if __name__ == "__main__":
    main()
