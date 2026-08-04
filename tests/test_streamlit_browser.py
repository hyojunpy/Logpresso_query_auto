import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "browser tests are opt-in")
class StreamlitBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.port = 18502
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "ui/streamlit_app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(cls.port),
                "--server.headless",
                "true",
            ],
            cwd=cls.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        health_url = f"http://127.0.0.1:{cls.port}/_stcore/health"
        for _ in range(60):
            if cls.process.poll() is not None:
                raise RuntimeError("Streamlit exited before the browser test started")
            try:
                with urlopen(health_url, timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.25)
        cls.process.terminate()
        raise RuntimeError("Streamlit did not become healthy")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)

    def test_clarification_widgets_are_removed_after_success(self):
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/", wait_until="networkidle")

            request = page.get_by_label("사용자 요청", exact=True)
            generate = page.get_by_role("button", name="쿼리 생성", exact=True)

            request.fill("에러 로그 보여줘")
            request.press("Control+Enter")
            generate.click()
            expect(page.get_by_text("추가 정보가 필요합니다.", exact=True)).to_be_visible()
            expect(page.get_by_label("확인 질문 답변", exact=True)).to_be_visible()
            expect(page.get_by_text("조회할 로그프레소 테이블 이름은 무엇인가요?", exact=True)).to_be_visible()

            page.get_by_label("확인 질문 답변", exact=True).fill(
                "테이블은 firewall_logs, 에러 필드는 message, 기간은 최근 24시간"
            )
            page.get_by_role("button", name="답변을 반영해 다시 생성", exact=True).click()

            expect(page.get_by_text("추가 정보가 필요합니다.", exact=True)).not_to_be_visible()
            expect(page.get_by_label("확인 질문 답변", exact=True)).not_to_be_visible()
            expect(page.get_by_text("조회할 로그프레소 테이블 이름은 무엇인가요?", exact=True)).not_to_be_visible()
            expect(page.locator("code").filter(has_text="table duration=24h firewall_logs")).to_be_visible()
            expect(page.locator("code").filter(has_text='search message == "ERROR"')).to_be_visible()
            expect(page.get_by_role("button", name="쿼리 파일 다운로드", exact=True)).to_be_visible()
            expect(page.get_by_text("코드 영역 오른쪽 위의 복사 아이콘으로 쿼리를 복사할 수 있습니다.")).to_be_visible()

            page.get_by_role("tab", name="검증", exact=True).click()
            expect(page.get_by_text("문법 검증을 통과했습니다.", exact=True)).to_be_visible()
            page.get_by_role("tab", name="문서 근거", exact=True).click()
            expect(page.get_by_text("생성 쿼리에 사용된 문서 근거", exact=False)).to_be_visible()
            expect(page.locator("details").first).to_be_visible()
            browser.close()
