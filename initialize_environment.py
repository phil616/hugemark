"""Post-install checks shared by the release's Bash and PowerShell entry points."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import gui


def find_browser():
    from playwright.sync_api import sync_playwright
    candidates = [os.environ.get('CHROME_PATH')]
    candidates += [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome', 'msedge')]
    if os.name == 'nt':
        for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if os.environ.get(variable):
                for suffix in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'):
                    candidates.append(str(Path(os.environ[variable]) / suffix))
    with sync_playwright() as playwright:
        bundled = playwright.chromium.executable_path
    candidates.append(bundled)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    print('未发现浏览器，正在安装 Playwright Chromium…', flush=True)
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)
    if not Path(bundled).is_file():
        raise RuntimeError('Chromium 安装后仍找不到可执行文件')
    return bundled


def main():
    from PySide6 import QtCore, QtGui, QtWidgets  # Also verifies native libraries can load.
    binary = str(Path(sys.argv[1]).resolve())
    browser = find_browser()
    print(f'Python：{sys.executable}\nQt：{QtCore.qVersion()}\n浏览器：{browser}', flush=True)
    gui.check_dependencies(binary, sys.executable, browser, lambda text: print(text, flush=True))
    destination = Path(__file__).resolve().parent / '.hugemark-browser'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(browser, encoding='utf-8')
    temporary.replace(destination)
    print('完整渲染检查通过；浏览器路径已保存供 GUI 使用。', flush=True)


if __name__ == '__main__':
    main()
