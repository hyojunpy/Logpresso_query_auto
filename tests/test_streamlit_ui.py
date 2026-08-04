import importlib.util
from pathlib import Path
import unittest


@unittest.skipIf(importlib.util.find_spec("streamlit.testing.v1") is None, "streamlit testing is not installed")
class StreamlitUiTest(unittest.TestCase):
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
        self.assertEqual(len(app.get("download_button")), 1)
        self.assertEqual(app.get("download_button")[0].label, "쿼리 파일 다운로드")


if __name__ == "__main__":
    unittest.main()
