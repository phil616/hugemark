# Hugemark

面向大型 Markdown 的 PDF 转换工具。Rust 负责解析和语义分块，独立 Chromium Worker 逐块排版，最后合并 PDF，避免浏览器一次加载整篇文档。

支持 CommonMark/GFM、表格、任务列表、脚注、代码高亮、中文字体、跨块链接与书签；通过内置 MathJax 和 Mermaid 将公式、流程图、时序图和状态图等转换为离线 SVG。

## 快速开始

下载 Release 中对应平台的程序：`hugemark-linux-amd64` 或 `hugemark-windows-amd64.exe`。程序仍需要 Python、Python 依赖及 Chrome/Chromium，详见[安装指南](docs/install.md)。不需要安装 Node.js 来运行。

```bash
hugemark build input.md -o output.pdf
hugemark build input.md -o output.pdf --resume
hugemark build input.md --css theme.css --mermaid-theme neutral
hugemark plan input.md
```

## 文档

- [安装与平台要求](docs/install.md)
- [用法、公式、图表与样式](docs/usage.md)
- [架构、扩展与限制](docs/architecture.md)
- [开发、测试与自动发布](docs/development.md)
- [历史大文档性能基线](docs/benchmarks/README.md)

## License

MIT @phil616
