"""浏览器交互验收：用真实浏览器把界面走一遍，并顺手生成 README 用的截图。

用法::

    # 1. 先起服务
    python src/web/server.py
    # 2. 再跑本脚本（另开一个窗口）
    pip install playwright            # 只需一次
    python tests/ui_check.py
    python tests/ui_check.py --base http://127.0.0.1:9000 --headed

覆盖的 12 项：页面加载、无 JS 报错、页脚版本号、文件卡片、转换成功、
下载链接、产物真的是有效 JPEG、转换记录渲染、刷新后记录仍在（持久化）、
坏文件给出中文错误、移动端宽度可用、全流程无 JS 报错。

需要 playwright（可选依赖：`pip install -e ".[ui]"`）；默认用 Playwright 自带的
Chromium，想用本机浏览器可加 `--browser-path "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"`。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))  # 保证未安装也能 import fconv

from fconv import __version__  # noqa: E402

SHOTS = ROOT / "docs" / "screenshots"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="fconv 浏览器交互验收")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="服务地址")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True)
    parser.add_argument("--headed", dest="headless", action="store_false", help="显示浏览器窗口")
    parser.add_argument("--browser-path", default=None, help="指定浏览器可执行文件（如本机 Edge）")
    parser.add_argument("--no-shots", action="store_true", help="不写 docs/screenshots")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[错误] 未安装 playwright。安装：pip install playwright  （或 pip install -e \".[ui]\"）")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("[错误] 未安装 Pillow（造测试样本要用）。")
        return 1

    SHOTS.mkdir(parents=True, exist_ok=True)
    work = ROOT / "benchmarks" / "_ui"
    work.mkdir(parents=True, exist_ok=True)
    sample = work / "界面验证样例.png"
    broken = work / "坏文件.png"
    Image.new("RGB", (640, 420), (37, 99, 235)).save(sample)
    broken.write_bytes(b"this is not an image")

    def shot(page, name: str) -> None:
        if not args.no_shots:
            page.screenshot(path=str(SHOTS / name))

    with sync_playwright() as playwright:
        launch_kwargs = {"headless": args.headless}
        if args.browser_path:
            launch_kwargs["executable_path"] = args.browser_path
        browser = playwright.chromium.launch(**launch_kwargs)
        errors: list[str] = []
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(args.base, wait_until="networkidle")
        check("页面加载", page.title().startswith("fconv"), page.title())
        check("无 JS 报错", not errors, "; ".join(errors)[:120])

        version = page.inner_text("#app-version")
        check("页脚版本号与代码一致", version == __version__, f"页面 {version} / 代码 {__version__}")
        shot(page, "01-首页.png")

        # --- 单文件转换（真交互）---
        page.set_input_files("#file-input", str(sample))
        page.wait_for_selector("#file-card.visible", timeout=8000)
        check("选中文件后出现文件卡片", page.inner_text("#file-name") == sample.name, page.inner_text("#file-name"))

        page.select_option("#output-format", "jpg")
        page.wait_for_timeout(300)
        page.click("#convert-btn")
        page.wait_for_selector("#result.success", timeout=60000)
        check("转换成功提示", "转换成功" in page.inner_text("#result-text"), page.inner_text("#result-text"))

        href = page.get_attribute("#download-btn", "href")
        check("下载链接生成", bool(href) and "api/download/" in href, href or "")
        shot(page, "02-转换完成.png")

        response = page.request.get(urljoin(args.base + "/", href or ""))
        body = response.body()
        check("下载产物是有效 JPEG", body[:2] == b"\xff\xd8", f"{len(body)}B")

        # --- 页面底部：格式表 + 转换记录 ---
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        shot(page, "03-格式与转换记录.png")
        history_text = page.inner_text("#history-summary")
        check("转换记录已渲染", "共" in history_text, history_text)

        # --- 刷新后记录仍在（持久化）---
        page.goto(args.base, wait_until="networkidle")
        page.wait_for_timeout(900)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        refreshed = page.inner_text("#history-summary")
        check("刷新后记录仍在", "共" in refreshed, refreshed)

        # --- 错误路径 ---
        page.evaluate("window.scrollTo(0,0)")
        page.set_input_files("#file-input", str(broken))
        page.wait_for_selector("#file-card.visible", timeout=8000)
        page.select_option("#output-format", "jpg")
        page.wait_for_timeout(300)
        page.click("#convert-btn")
        page.wait_for_selector("#result.error", timeout=60000)
        error_text = page.inner_text("#result-text")
        check("坏文件给出中文错误", "转换失败" in error_text, error_text[:80])
        shot(page, "04-错误提示.png")

        # --- 移动端宽度 ---
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mobile.goto(args.base, wait_until="networkidle")
        mobile.wait_for_timeout(800)
        if not args.no_shots:
            mobile.screenshot(path=str(SHOTS / "05-移动端.png"))
        check("移动端页面可用", "fconv" in mobile.inner_text(".brand"), "")

        check("全流程无 JS 报错", not errors, "; ".join(errors)[:160])
        browser.close()

    shutil.rmtree(work, ignore_errors=True)

    print("-" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"浏览器交互验收：{passed}/{len(results)} 通过")
    for name, ok, detail in results:
        if not ok:
            print(f"  失败：{name} {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
