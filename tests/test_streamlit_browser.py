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
            [sys.executable, "-m", "streamlit", "run", "ui/streamlit_app.py", "--server.address", "127.0.0.1", "--server.port", str(cls.port), "--server.headless", "true"],
            cwd=cls.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            try:
                if urlopen(f"http://127.0.0.1:{cls.port}/_stcore/health", timeout=1).status == 200:
                    return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError("Streamlit did not become healthy")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)

    def test_clarification_then_generation_and_structure_view(self):
        from playwright.sync_api import expect, sync_playwright
        request_label = "\uc0ac\uc6a9\uc790 \uc694\uccad"
        generate_label = "\ucffc\ub9ac \uc0dd\uc131"
        clarification_label = "\ud655\uc778 \uc9c8\ubb38 \ub2f5\ubcc0"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/", wait_until="networkidle")
            page.get_by_label(request_label, exact=True).fill("\uc5d0\ub7ec \ub85c\uadf8 \ubcf4\uc5ec\uc918")
            page.get_by_role("button", name=generate_label, exact=True).click()
            expect(page.get_by_label(clarification_label, exact=True)).to_be_visible()
            page.get_by_label(clarification_label, exact=True).fill("\ud14c\uc774\ube14\uc740 firewall_logs, \uc5d0\ub7ec \ud544\ub4dc\ub294 message, \uae30\uac04\uc740 \ucd5c\uadfc 24\uc2dc\uac04")
            page.get_by_role("button", name="\ub2f5\ubcc0\uc744 \ubc18\uc601\ud574 \ub2e4\uc2dc \uc0dd\uc131", exact=True).click()
            expect(page.locator("code").filter(has_text="table duration=24h firewall_logs")).to_be_visible()
            page.get_by_role("tab", name="\uac80\uc99d", exact=True).click()
            expect(page.get_by_text("\uc2e4\ud589 \uc900\ube44 \uc0c1\ud0dc", exact=True)).to_be_visible()
            page.get_by_role("tab", name="\uad6c\uc870", exact=True).click()
            expect(page.locator("svg").first).to_be_visible()
            browser.close()
