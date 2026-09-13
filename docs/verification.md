# v0.2 验证记录

验证日期：2026-09-13；本地环境为 Linux amd64、Rust 1.94、Python 3.12 和 Google Chrome。

- Rust 常规测试 7 项通过；超大代码、表格、段落专项测试通过。
- 跨平台测试用例 5 项在 Linux 通过，覆盖 MathJax/Mermaid、中文路径、组件缓存恢复、SVG ID、无效源码、CSS、互斥锁和超时清理。
- Linux 集成回归 13 项通过，包含真实浏览器崩溃注入、断点恢复、跨块导航与资源变化检测。
- Linux 与 Windows GNU 目标的 Clippy 无警告；Windows amd64 Release 交叉编译成功。
- GitHub Workflow 通过 actionlint；npm audit 未报告漏洞。
- `tests/fixtures/advanced.md` 输出两页 PDF，已检查页面截图中的公式、中文流程图、时序图和状态图。

Windows 原生 MSVC 构建、路径测试和全部 PDF/进程测试已在 [修复分支 GitHub Actions](https://github.com/phil616/hugemark/actions/runs/34747438792) 通过，Linux 同样通过。本次修复了 Windows 扩展路径 `\\?\C:\...` 转换为浏览器文件 URL 时的错误；新增盘符、UNC、中文及 URL 特殊字符回归测试，并在 PDF 测试失败时输出 Worker 日志。该分支运行未触发 Release 发布。

10/20/50 MiB 大文档数据保留在 [历史基线](benchmarks/README.md)，不是本版高级组件的性能测试结果。
