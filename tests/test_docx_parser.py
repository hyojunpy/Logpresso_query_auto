from pathlib import Path
import unittest

from app.services.docx_parser import DocxParser


class DocxParserTest(unittest.TestCase):
    def test_extracts_paragraphs_and_command_candidates(self):
        chunks = DocxParser().parse(Path("docs") / "로그프레소 쿼리.docx")
        self.assertGreater(len(chunks), 50)
        names = {chunk.entry_name for chunk in chunks if chunk.entry_name}
        self.assertIn("table", names)
        self.assertIn("evtx-file", names)
        self.assertIn("eml-file", names)
        self.assertIn("lnk-file", names)
        self.assertIn("parse", names)
        self.assertIn("explode", names)
        self.assertNotIn("where", names)

    def test_extracts_option_and_function_metadata(self):
        chunks = DocxParser().parse(Path("docs") / "로그프레소 쿼리.docx")
        options = {option for chunk in chunks for option in chunk.options}
        functions = {function for chunk in chunks for function in chunk.functions}
        self.assertIn("duration", options)
        self.assertIn("span", options)
        self.assertIn("count", functions)


if __name__ == "__main__":
    unittest.main()
