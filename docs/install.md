# 安装与平台要求

## Linux amd64

Release 程序基于 Ubuntu 22.04 构建，面向 glibc 2.35 或更新的 x86_64 Linux；不是 musl 静态程序。下载后：

```bash
chmod +x hugemark-linux-amd64
mv hugemark-linux-amd64 hugemark
./hugemark requirements > requirements.txt
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./hugemark build input.md -o output.pdf
```

安装 Chrome 或 Chromium；Debian/Ubuntu 可另安装 `fonts-noto-cjk fonts-noto-core`。`poppler-utils` 用于检查 PDF，不是生成 PDF 的必要依赖。

## Windows amd64

需要 64 位 Python 3.12 或更新版本，以及 Chrome 或 Edge。将下载的程序改名为 `hugemark.exe`，在 PowerShell 中执行：

```powershell
.\hugemark.exe requirements | Out-File -Encoding utf8 requirements.txt
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\hugemark.exe build input.md -o output.pdf
```

可使用 `--font-sans "Microsoft YaHei" --font-cjk "Microsoft YaHei"` 指定系统字体。发布使用 MSVC 工具链，若系统缺少运行库，请安装 Microsoft Visual C++ 2015–2022 x64 Redistributable。

## 浏览器与 Python

默认优先查找当前目录下的 `.venv`，否则使用 PATH 中的 `python3`（Linux）或 `python`（Windows）。可用 `--python` 指定解释器路径。

浏览器按 `--chrome`、`CHROME_PATH`、常见安装位置自动发现。也可安装 Playwright Chromium，但需将其实际可执行文件路径传给 `--chrome` 或 `CHROME_PATH`。运行不需要联网下载 MathJax/Mermaid，它们与 Python Worker、CSS 一起嵌入主程序。Python 包和浏览器仍为外部依赖，发布二进制并非包含整个运行环境的单文件安装包。

第三方图表库许可证可用 `hugemark licenses` 查看。
