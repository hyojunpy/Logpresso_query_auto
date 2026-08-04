import unittest

from app.services.retriever import Retriever
from tests.support import shared_index


class RetrieverTest(unittest.TestCase):
    def test_search_table(self):
        results = Retriever(shared_index()).search("table duration 테이블 조회", limit=5)
        self.assertTrue(results)
        self.assertTrue(any(result.entry_name == "table" for result in results))


if __name__ == "__main__":
    unittest.main()

