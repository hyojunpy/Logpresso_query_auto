import importlib.util
from pathlib import Path
import unittest
import pytest


pytestmark = pytest.mark.advanced_parser


@unittest.skipIf(importlib.util.find_spec("streamlit.testing.v1") is None, "streamlit testing is not installed")
class StreamlitUiTest(unittest.TestCase):
    def test_main_screen_uses_product_and_schema_selection_instead_of_examples(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(Path("ui") / "streamlit_app.py"), default_timeout=15)
        app.run()

        labels = [item.label for item in app.selectbox]
        self.assertIn("제조사", labels)
        self.assertIn("Syslog 제품", labels)
        self.assertIn("로그 형식", labels)
        self.assertNotIn("예제 요청", labels)
        self.assertNotIn("빠른 테스트", labels)
        self.assertTrue(any(area.label == "쿼리 요청" for area in app.text_area))

        next(item for item in app.selectbox if item.label == "제조사").select("MONITORAPP").run()
        next(item for item in app.selectbox if item.label == "Syslog 제품").select("AIWAF").run()
        next(item for item in app.selectbox if item.label == "로그 형식").select("AIWAF Alert").run()

        self.assertTrue(any(item.label == "선택된 로그 형식 필드 28개" for item in app.expander))
        field_table = next(item for item in app.dataframe if "필드명" in item.value.columns)
        self.assertIn("_time", field_table.value["필드명"].tolist())
        self.assertIn("표시명", field_table.value.columns)
        self.assertIn("유사어", field_table.value.columns)

    def test_clarification_area_clears_after_successful_generation(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path("ui") / "streamlit_app.py"
        app = AppTest.from_file(str(app_path), default_timeout=15)
        app.run()

        app.text_area[0].set_value("에러 로그 보여줘")
        app.button[0].click().run()
        self.assertTrue(any("추가 정보가 필요합니다." in item.value for item in app.warning))
        self.assertTrue(any(area.label == "확인 질문 답변" for area in app.text_area))

        app.text_area[0].set_value("firewall_logs의 src_ip를 할당ip로 rename해줘")
        app.button[0].click().run()
        self.assertFalse(any("추가 정보가 필요합니다." in item.value for item in app.warning))
        self.assertFalse(any(area.label == "확인 질문 답변" for area in app.text_area))
        self.assertTrue(any("rename src_ip as 할당ip" in block.value for block in app.code))

    def test_generated_query_has_download_and_copy_guidance(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path("ui") / "streamlit_app.py"
        app = AppTest.from_file(str(app_path), default_timeout=15)
        app.run()

        app.text_area[0].set_value("firewall_logs의 src_ip를 할당ip로 rename해줘")
        app.button[0].click().run()

        self.assertTrue(any("복사 아이콘" in item.value for item in app.caption))
        query_download = next(item for item in app.get("download_button") if item.label == "쿼리 파일 다운로드")
        self.assertEqual(query_download.label, "쿼리 파일 다운로드")

    def test_validation_and_references_are_rendered_as_readable_sections(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path("ui") / "streamlit_app.py"
        app = AppTest.from_file(str(app_path), default_timeout=15)
        app.run()

        app.text_area[0].set_value("최근 24시간 동안 firewall_logs에서 action=deny인 로그 보여줘")
        next(button for button in app.button if button.label == "쿼리 생성").click().run()

        self.assertTrue(any("문법 검증을 통과했습니다." in item.value for item in app.success))
        self.assertTrue(any("사용 명령:" in item.value for item in app.markdown))
        self.assertGreaterEqual(len(app.expander), 2)
        self.assertTrue(any("table" in item.label for item in app.expander))
        self.assertTrue(any("search" in item.label for item in app.expander))

    def test_clarification_answer_generates_query_without_losing_result(self):
        from streamlit.testing.v1 import AppTest

        app_path = Path("ui") / "streamlit_app.py"
        app = AppTest.from_file(str(app_path), default_timeout=15)
        app.run()

        app.text_area[0].set_value("에러 로그 보여줘")
        next(button for button in app.button if button.label == "쿼리 생성").click().run()

        answer = next(area for area in app.text_area if area.label == "확인 질문 답변")
        answer.set_value("테이블은 firewall_logs, 에러 필드는 message, 기간은 최근 24시간")
        next(button for button in app.button if button.label == "답변을 반영해 다시 생성").click().run()

        self.assertFalse(any("추가 정보가 필요합니다." in item.value for item in app.warning))
        self.assertFalse(any(area.label == "확인 질문 답변" for area in app.text_area))
        self.assertTrue(any("table duration=24h firewall_logs" in block.value for block in app.code))
        self.assertTrue(any('search message == "ERROR"' in block.value for block in app.code))


if __name__ == "__main__":
    unittest.main()
