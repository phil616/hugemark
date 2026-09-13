# v0.2 验证记录

验证日期：2026-09-13；本地环境为 Linux amd64、Rust 1.94、Python 3.12 和 Google Chrome。

- Rust 常规测试 7 项通过；超大代码、表格、段落专项测试通过。
- 跨平台测试用例 5 项在 Linux 通过，覆盖 MathJax/Mermaid、中文路径、组件缓存恢复、SVG ID、无效源码、CSS、互斥锁和超时清理。
- Linux 集成回归 13 项通过，包含真实浏览器崩溃注入、断点恢复、跨块导航与资源变化检测。
- Linux 与 Windows GNU 目标的 Clippy 无警告；Windows amd64 Release 交叉编译成功。
- GitHub Workflow 通过 actionlint；npm audit 未报告漏洞。
- `tests/fixtures/advanced.md` 输出两页 PDF，已检查页面截图中的公式、中文流程图、时序图和状态图。

Windows 原生执行及 MSVC 构建尚未在本地验证，由工作流的 Windows runner 执行。此记录不代表 GitHub Actions 已经运行或 Release 已经发布。

10/20/50 MiB 大文档数据保留在 [历史基线](benchmarks/README.md)，不是本版高级组件的性能测试结果。
