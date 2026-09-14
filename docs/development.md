# 开发、测试与发布

## 本地构建

需要 Rust 1.94+、Python 3.12+ 及安装指南中的运行环境。

```bash
cargo build --release --locked
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
cargo build
.venv/bin/python tests/portable.py
.venv/bin/python tests/integration.py
cargo test --release oversized_acceptance -- --ignored
```

Windows 使用 `.venv/Scripts/python.exe tests/portable.py`；`integration.py` 含 Linux 专用故障注入，仅在 Linux 运行。可用 `HUGEMARK_BIN` 指向待测发布程序。跨平台测试覆盖公式、图表、中文路径、PDF 书签、损坏缓存、CSS 变更、互斥锁和超时后的后代进程清理。

## 更新嵌入依赖

Node.js 22 仅用于维护依赖。构建 Rust 程序时直接使用已提交的 `assets/vendor/`，无需 Node.js。

```bash
npm ci --ignore-scripts
npm run vendor
npm audit
```

更新版本时同时提交 `package.json`、锁文件、生成的 JS、manifest 与 LICENSES。CI 会重新生成并检查差异。主程序的 `requirements` 和 `licenses` 子命令输出嵌入的 Python 依赖清单和图表库许可证。

## GitHub Actions

[build-release.yml](../.github/workflows/build-release.yml) 在 push、PR 和手动触发时检查 Linux/Windows amd64；所有测试通过后保留两个完整平台压缩包。Windows 使用 MSVC，Linux 使用 Ubuntu 22.04 GNU 工具链。

发布步骤：修改 Cargo.toml 版本并用 Cargo 更新 Cargo.lock，提交后推送同版本标签，例如：

```bash
git tag v0.2.0
git push origin v0.2.0
```

标签必须精确等于 `v` 加 Cargo 版本。只有标签 push 会创建 GitHub Release；带连字符版本标为预发布。两平台任一失败都会阻止发布。自定义上传资产仅有：

- `hugemark-linux-amd64.tar.gz`
- `hugemark-windows-amd64.zip`

不提供 ARM、macOS 或额外裸二进制资产。每包包含本平台二进制与初始化脚本、GUI、样式、字体、依赖清单、统一许可证和教程。GitHub 自带的 Source code 下载项由平台生成，不属于工作流上传产物。工作流使用内置 GITHUB_TOKEN，发布 Job 具有 contents:write 权限，无需额外发布密钥。

## 性能证据

历史 10/20/50 MiB 完整转换记录见 [benchmarks](benchmarks/README.md)，属于加入高级组件前的基线。重新测量使用 `scripts/benchmark.py`，不得将该基线视为公式/图表密集文档的性能结果。

当前开发环境可实际测试 Linux，且可交叉编译 Windows GNU 版本；Windows 原生进程行为和 MSVC Release 由 GitHub Windows runner 的测试把关。

本轮验证范围与结果见 [v0.2 验证记录](verification.md)。

## 发行包验证

`python scripts/package_release.py --platform linux --binary target/release/hugemark` 生成 Linux tar.gz；Windows 使用 `--platform windows` 和 MSVC exe。`HUGEMARK_ARCHIVE` 指向当前平台压缩包后运行 `tests/test_release.py`，会真实解压、从不同工作目录执行初始化，检查缺失文件/损坏环境，并执行新建及已有虚拟环境的重复安装。Linux 还验证无 Python 报错和无 uv 的 pip 路径。测试需要网络及浏览器环境，CI 已集成。
