# Hugemark

面向大型 Markdown 的 PDF 转换工具。Rust 负责解析和语义分块，独立 Chromium Worker 逐块排版，最后合并 PDF，避免浏览器一次加载整篇文档。

支持 CommonMark/GFM、表格、任务列表、脚注、代码高亮、中文字体、跨块链接与书签；通过内置 MathJax 和 Mermaid 将公式、流程图、时序图和状态图等转换为离线 SVG。

## 快速开始

下载 Release 中的 `hugemark-linux-amd64.tar.gz`（Linux）或 `hugemark-windows-amd64.zip`（Windows），完整解压后运行包内 `hugemark-init.sh`（Bash）或 `hugemark-init.ps1`（PowerShell 7）。初始化会创建虚拟环境、重新安装依赖并检查完整渲染链。需预先安装 64 位 Python 3.12+；详见[发行包教程](docs/release-guide.md)。

```bash
hugemark build input.md -o output.pdf
hugemark build input.md -o output.pdf --resume
hugemark build input.md --css theme.css --mermaid-theme neutral
hugemark plan input.md
```

## 图形界面

先执行 `python -m pip install -r requirements-gui.txt`，再运行 `python gui.py` 打开 Qt 6 桌面界面。内置 CJK 字体，支持拖放、队列排序、依赖检查、串行转换和输出文件夹选择。详见[GUI 使用指南](docs/gui.md)。

## 文档

- [安装与平台要求](docs/install.md)
- [用法、公式、图表与样式](docs/usage.md)
- [架构、扩展与限制](docs/architecture.md)
- [开发、测试与自动发布](docs/development.md)
- [历史大文档性能基线](docs/benchmarks/README.md)

## License

MIT @phil616
