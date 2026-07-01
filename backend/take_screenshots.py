#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""截取 4 张 Demo 截图"""

import os
import sys
import time

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "images")
FRONTEND_URL = "http://localhost:5173"

def take_screenshots():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        screenshots = [
            ("dashboard.png", "/", "仪表盘"),
            ("detail.png", "/paper/1", "论文详情"),
            ("graph.png", "/graph", "知识图谱"),
            ("scorecard.png", "/scorecard", "评分卡"),
        ]

        for filename, path, name in screenshots:
            url = f"{FRONTEND_URL}{path}"
            print(f"  截图: {name} ({url})...", end=" ", flush=True)
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
                time.sleep(2)  # 等待图表渲染
                filepath = os.path.join(OUTPUT_DIR, filename)
                page.screenshot(path=filepath, full_page=False)
                print(f"[OK] {filepath}")
            except Exception as e:
                print(f"[FAIL] {e}")

        browser.close()

    print(f"\n  截图保存到: {OUTPUT_DIR}")

if __name__ == "__main__":
    print("\n  === Demo 截图工具 ===\n")
    take_screenshots()
