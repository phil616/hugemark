# Hugemark 使用教程

本包包含 Hugemark amd64 二进制、初始化脚本、Qt GUI、必要样式与内置 CJK 字体。`LICENSE.txt` 包含项目及随包资源的许可证。

## 1. 解压

Linux 下载 `hugemark-linux-amd64.tar.gz`；Windows 下载 `hugemark-windows-amd64.zip`。

完整解压到可写目录，保持所有文件的相对位置。不要只复制初始化脚本，也不要在压缩软件中直接运行。安装虚拟环境后不要移动该文件夹；需要移动时请在新位置重新创建 `.venv`。

## 2. 初始化

首先自行安装可用的 **64 位 Python 3.12 或更新版本**。uv 是可选工具，存在时优先使用。初始化需要网络下载 Python 包；没有 Chrome/Edge/Chromium 时还会下载 Chromium。

### Linux Bash

系统需要 x86_64 Linux、glibc 2.35+，在 Bash 中执行：

```bash
cd hugemark-linux-amd64
bash ./hugemark-init.sh
```

脚本只接受同目录的 `hugemark-linux-amd64`，会检查执行权限并实际运行版本命令。

### Windows PowerShell 7

使用 `pwsh`（PowerShell 7），不支持 Windows PowerShell 5.1。先完整解压，再执行：

```powershell
cd hugemark-windows-amd64
pwsh -File .\hugemark-init.ps1
```

脚本只接受同目录的 `hugemark-windows-amd64.exe`。如下载的脚本被文件来源标记阻止，在确认来源后执行 `Unblock-File .\hugemark-init.ps1`，再运行脚本。缺少运行库时安装 Microsoft Visual C++ 2015–2022 x64 Redistributable。

### 脚本会做什么

1. 确认同目录下的指定二进制存在且能运行；缺少或错误时立即终止。
2. 查找可用 Python；不会自行下载解释器。已有的 `.venv` 必须有效，否则报错且不覆盖它。
3. 优先使用 uv 创建 `.venv`；没有 uv 时使用 Python venv。始终明确安装到本包目录的 `.venv`，忽略其他激活环境。
4. 从二进制导出依赖清单，加上 GUI 依赖，每次都重新安装（uv `--reinstall` 或 pip `--force-reinstall`），然后检查依赖关系。已有包也不会跳过此步骤。
5. 检查 Qt、查找或下载浏览器，实际生成一份含公式和流程图的 PDF 验证完整渲染链。浏览器路径保存到 `.hugemark-browser` 供 GUI 默认使用。
6. 打印二进制、虚拟环境、Python、浏览器及安装状态；成功后按任意键退出。非交互运行时不等待按键；错误以非零状态退出，保留具体报错。

Linux 的系统图形库和 PDF 字体不是 Python 包，不会由脚本自动使用 sudo 安装。在精简 Debian/Ubuntu 上，Qt xcb 常用依赖包括 `libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0`；Chromium 的缺失库按错误提示安装。建议安装 `fonts-noto-cjk fonts-noto-core` 改善 PDF 中文字体。内置 GUI 字体不会安装为 PDF 的系统字体。

## 3. 启动 GUI

Linux：

```bash
./.venv/bin/python ./gui.py
```

Windows PowerShell 7：

```powershell
& .\.venv\Scripts\python.exe .\gui.py
```

GUI 的“运行环境”中默认定位本包二进制及 `.venv`。如果以前保存过路径，检查并按需更新；浏览器也可手动选择。界面使用 Qt 6 和内置 Noto CJK 字体，需要正常的桌面会话。

## 4. 批量转换

拖入 Markdown 文件，或点击“添加文件 / 添加文件夹”，选择输出目录，再点击“检查并开始转换”。按队列顺序逐个转换，不并发；可上移、下移调整顺序。

同名或已有 PDF 自动添加编号，不覆盖旧文件。日志显示失败原因；单文件失败后继续下一项。双击完成项打开 PDF。“完成当前文件后停止”会保留当前任务，跳过后续项。

输出目录下 `.hugemark-gui/job-*` 保存日志和缓存，结束后可自行清理。运行中先停止并等待，再关闭窗口。

## 命令行

也可以使用包内二进制直接运行 `build input.md -o output.pdf --python <本包虚拟环境解释器>`。若浏览器由初始化脚本下载，请同时传 `--chrome <.hugemark-browser 文件中的路径>`；该文件由 GUI 读取，CLI 不会自动读取。`--help` 可查看完整参数。
