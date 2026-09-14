# Qt 图形界面

桌面界面使用 **PySide6 / Qt 6**，运行逻辑与界面分离：`gui.py` 提供依赖检查和串行队列，`desktop.py` 提供 Qt 窗口；样式位于 `assets/desktop.qss`。

## 安装与启动

在包含 GUI 源码的仓库目录执行：

```bash
python -m pip install -r requirements-gui.txt
python gui.py
```

Linux 的命令可能为 `python3`；Windows 可用 `pythonw gui.py` 隐藏终端。GUI 安装只需要 Qt Essentials，不需要 Qt Addons 或 Tkinter。若使用虚拟环境，请使用该环境的 Python 执行上述两条命令。

Hugemark 二进制及渲染用的 Python 依赖仍需按[安装指南](install.md)准备。界面 Python 和渲染 Python 可以不同，在“运行环境”页指定。

请保留 `gui.py`、`desktop.py` 和完整的 `assets/` 目录。Release 的 Linux tar.gz / Windows zip 已包含这些文件，解压后先运行同目录初始化脚本；GUI 仍通过包内虚拟环境的 Python 启动，不是独立 GUI 可执行文件。

Linux 需要桌面会话及 Qt 平台库。在精简 Debian/Ubuntu 系统遇到 xcb 插件加载失败时，可安装 `libegl1 libopengl0 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0`。`QT_QPA_PLATFORM=offscreen` 仅用于无窗口测试，不用于日常启动。

## 字体与布局

随源码提供 Noto Sans CJK SC 字体（SIL OFL 1.1，许可证见 `assets/fonts/OFL.txt`），在 Qt 进程内注册，覆盖中日韩文字。Qt 6 使用高 DPI 坐标与字体缩放。长路径在表格内显示文件名，悬停查看完整路径；表格与日志区域可拖动分隔条调整大小。

界面内置字体不会安装到系统，也不会改变 Chromium 生成 PDF 时使用的正文字体。PDF 字体仍由运行环境决定。

## 操作

- “文档队列”：添加文件、添加文件夹当前层的 Markdown，或将文件拖入窗口；重复文件会去重。
- 选中一行后“上移 / 下移”调整转换顺序；支持多选移除、清空列表，以及 Ctrl+O 添加、Delete 移除。
- 选择输出目录后点击“检查并开始转换”。同名或已有 PDF 自动添加编号，不覆盖原文件。
- 查看状态颜色、总体进度和实时日志；双击完成项打开 PDF，也可打开输出文件夹、复制或保存日志。
- “运行环境”：选择 Hugemark、Python 和浏览器。填写 `auto` 自动查找浏览器。路径配置保存在本机 Qt QSettings 中。

依赖检查验证二进制、Python 3.12+、精确包版本、模块加载，再实际生成含公式和 Mermaid 的 PDF。每次批处理都会重新检查；缺少依赖时在日志中报告，不自动修改环境。检查通过不代表任意输入一定可转换。

## 队列安全

始终只转换一个文件。后台使用 QThread，通过 Qt 信号更新窗口；处理期间禁用输入修改，界面保持响应。单文件失败后继续下一项。

“完成当前文件后停止”让当前检查或转换结束，后续项标记“未处理”。运行中关闭窗口会提示先停止并等待，不强杀正在写入的任务。再次开始会重新处理当前列表，并为已存在输出自动编号。

输出目录下 `.hugemark-gui/job-*` 保存每项独立缓存和日志，任务结束后可自行清理。

## 验证

```bash
python tests/test_gui.py
python tests/test_desktop.py
```

Qt 测试使用 offscreen 平台，覆盖 CJK 字体、拖放、排序、设置、错误恢复、停止与编辑锁定，以及真实串行 PDF 转换。可通过 `HUGEMARK_BIN` 指定测试二进制；若没有二进制则跳过真实转换测试。CI 双平台任务会安装 GUI 依赖并运行这些测试。
