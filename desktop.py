"""Qt 6 desktop UI. Worker signals are delivered on the GUI thread."""
from pathlib import Path
import sys
import threading
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QDesktopServices, QColor, QKeySequence, QShortcut, QPalette
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar, QPlainTextEdit,
    QTabWidget, QSplitter, QFrame)
import gui

ASSETS = Path(__file__).resolve().parent / 'assets'


def configure(app):
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in [(QPalette.Window, '#f3f5fa'), (QPalette.WindowText, '#202c43'),
                        (QPalette.Base, '#ffffff'), (QPalette.Text, '#202c43'),
                        (QPalette.Button, '#ffffff'), (QPalette.ButtonText, '#202c43'),
                        (QPalette.Highlight, '#e4ecff'), (QPalette.HighlightedText, '#263b77')]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    font_path = ASSETS / 'fonts/NotoSansCJKsc-Regular.otf'
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        raise RuntimeError(f'无法加载内置字体，请保留完整 assets 目录：{font_path}')
    families = QFontDatabase.applicationFontFamilies(font_id)
    font = QFont()
    font.setFamilies(families + ['Microsoft YaHei UI', 'Noto Sans CJK SC', 'PingFang SC', 'sans-serif'])
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet((ASSETS / 'desktop.qss').read_text(encoding='utf-8'))


def label(text, name=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setObjectName(name)
    return widget


class Worker(QThread):
    event = Signal(object)

    def __init__(self, config, sources, destination, convert, parent=None):
        super().__init__(parent)
        self.config, self.sources, self.destination, self.convert = config, sources, destination, convert
        self.stop = threading.Event()

    def run(self):
        try:
            gui.check_dependencies(*self.config, lambda text: self.event.emit(('log', text)))
            self.event.emit(('checked',))
            if self.convert:
                gui.batch(*self.config, self.sources, self.destination, self.stop,
                          lambda *event: self.event.emit(event))
            self.event.emit(('done', True))
        except Exception as error:
            self.event.emit(('log', str(error)))
            self.event.emit(('done', False))


class Window(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings('Hugemark', 'Desktop')
        self.files, self.results, self.states = [], [], []
        self.worker = None
        self.controls = []
        self.setWindowTitle('Hugemark — 文档工作台')
        self.resize(1160, 850)
        self.setMinimumSize(880, 700)
        self.setAcceptDrops(True)
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label('Hugemark', 'brand'))
        heading.addWidget(label('让 Markdown 成为可分享的 PDF', 'muted'))
        header.addLayout(heading)
        header.addStretch()
        self.badge = label('环境待检查', 'badge')
        header.addWidget(self.badge, 0, Qt.AlignVCenter)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        self.queue_page = QWidget()
        self.environment = QWidget()
        self.tabs.addTab(self.queue_page, '文档队列')
        self.tabs.addTab(self.environment, '运行环境')
        layout.addWidget(self.tabs, 1)
        self.make_queue()
        self.make_environment()
        footer = QHBoxLayout()
        self.summary = label('准备就绪', 'muted')
        footer.addWidget(self.summary, 1)
        self.stop_button = self.button('完成当前文件后停止', self.request_stop, footer, lock=False)
        self.stop_button.setEnabled(False)
        self.start_button = self.button('检查并开始转换', lambda: self.start(True), footer, primary=True)
        layout.addLayout(footer)
        QShortcut(QKeySequence('Ctrl+O'), self, self.choose_files)
        remove_shortcut = QShortcut(QKeySequence('Delete'), self.table, self.remove_selected)
        remove_shortcut.setContext(Qt.WidgetWithChildrenShortcut)

    def busy(self):
        return self.worker is not None

    def button(self, text, callback, row, primary=False, lock=True):
        button = QPushButton(text)
        if primary:
            button.setObjectName('primary')
        button.clicked.connect(callback)
        row.addWidget(button)
        if lock:
            self.controls.append(button)
        return button

    def make_queue(self):
        body = QVBoxLayout(self.queue_page)
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(12)
        tools = QHBoxLayout()
        self.button('添加文件', self.choose_files, tools, primary=True)
        self.button('添加文件夹', self.choose_folder, tools)
        self.button('移除', self.remove_selected, tools)
        self.button('上移', lambda: self.move(-1), tools)
        self.button('下移', lambda: self.move(1), tools)
        self.button('清空', self.clear, tools)
        tools.addStretch()
        self.count = label('0 个文件', 'muted')
        tools.addWidget(self.count)
        body.addLayout(tools)
        self.empty = label('拖入 Markdown 文件，或点击“添加文件”\n按照列表顺序逐个转换 · 同名输出自动编号', 'dropHint')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(82)
        body.addWidget(self.empty)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['文档 / 悬停查看完整路径', '状态', '输出 / 双击打开 PDF'])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self.open_result)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        logs = QWidget()
        log_layout = QVBoxLayout(logs)
        log_layout.setContentsMargins(0, 8, 0, 0)
        log_tools = QHBoxLayout()
        log_tools.addWidget(label('运行日志', 'section'))
        log_tools.addStretch()
        self.button('复制日志', self.copy_logs, log_tools, lock=False)
        self.button('保存日志', self.save_logs, log_tools, lock=False)
        log_layout.addLayout(log_tools)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setPlaceholderText('检查结果和转换详情会显示在这里。')
        log_layout.addWidget(self.log)
        splitter.addWidget(logs)
        splitter.setSizes([300, 145])
        body.addWidget(splitter, 1)
        output = QHBoxLayout()
        output.addWidget(label('输出文件夹'))
        self.output = QLineEdit(str(self.settings.value('output', '')))
        self.output.setPlaceholderText('选择生成 PDF 的保存位置')
        self.controls.append(self.output)
        output.addWidget(self.output, 1)
        self.button('选择…', self.choose_output, output)
        self.button('打开文件夹', self.open_output, output, lock=False)
        body.addLayout(output)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)
        body.addWidget(self.progress)

    def make_environment(self):
        box = QVBoxLayout(self.environment)
        box.setContentsMargins(24, 24, 24, 24)
        box.setSpacing(18)
        box.addWidget(label('配置一次，随时检查', 'section'))
        intro = label('检查会验证 Python 包版本，并实际生成含公式和流程图的 PDF。\n程序路径会保存在本机；界面字体与 PDF 正文字体分别配置。', 'muted')
        intro.setWordWrap(True)
        box.addWidget(intro)
        form = QGridLayout()
        form.setVerticalSpacing(18)
        self.binary = QLineEdit(str(self.settings.value('binary', gui.default_binary())))
        self.python = QLineEdit(str(self.settings.value('python', gui.default_python())))
        self.chrome = QLineEdit(str(self.settings.value('chrome', 'auto')))
        for row, (name, field) in enumerate([('Hugemark 程序', self.binary), ('Python 解释器', self.python), ('Chrome / Edge / Chromium', self.chrome)]):
            form.addWidget(label(name), row, 0)
            form.addWidget(field, row, 1)
            button = QPushButton('浏览…')
            button.clicked.connect(lambda checked=False, f=field: self.choose_executable(f))
            form.addWidget(button, row, 2)
            self.controls.extend([field, button])
            field.textChanged.connect(self.invalidate_check)
        box.addLayout(form)
        box.addWidget(label('浏览器填写 auto 时，使用系统自动发现或 CHROME_PATH。', 'muted'))
        row = QHBoxLayout()
        self.button('检查运行环境', lambda: self.start(False), row, primary=True)
        row.addStretch()
        box.addLayout(row)
        self.font_status = label('界面使用内置 Noto Sans CJK 字体，支持中文、日文、韩文和缩放。', 'muted')
        self.font_status.setWordWrap(True)
        box.addWidget(self.font_status)
        box.addStretch()

    def invalidate_check(self):
        self.badge.setText('环境待检查')

    def choose_executable(self, field):
        name, _ = QFileDialog.getOpenFileName(self, '选择可执行文件')
        if name:
            field.setText(name)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, '选择输出文件夹', self.output.text())
        if path:
            self.output.setText(path)

    def choose_files(self):
        if not self.busy():
            names, _ = QFileDialog.getOpenFileNames(self, '添加 Markdown', '', 'Markdown (*.md *.markdown *.mdown);;所有文件 (*)')
            self.add_files(names)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, '添加文件夹内的 Markdown（不含子目录）')
        if path:
            self.add_files(sorted(p for p in Path(path).iterdir() if p.suffix.lower() in ('.md', '.markdown', '.mdown')))

    def add_files(self, names):
        if self.busy():
            return
        known = {str(Path(p).resolve()).casefold() if sys.platform == 'win32' else p for p in self.files}
        for name in names:
            path = Path(name).resolve()
            key = str(path).casefold() if sys.platform == 'win32' else str(path)
            if path.is_file() and key not in known:
                self.files.append(str(path))
                self.states.append('待处理')
                self.results.append('')
                known.add(key)
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.files))
        colors = {'完成': '#087b60', '失败': '#be354b', '处理中': '#405dde', '未处理': '#777f90'}
        for row, (source, state, output) in enumerate(zip(self.files, self.states, self.results)):
            for col, text in enumerate([Path(source).name, state, Path(output).name if output else '—']):
                item = QTableWidgetItem(text)
                item.setToolTip(source if col == 0 else output if col == 2 else state)
                if col == 1:
                    item.setForeground(QColor(colors.get(state, '#647084')))
                self.table.setItem(row, col, item)
        self.count.setText(f'{len(self.files)} 个文件')
        self.empty.setVisible(not self.files)

    def selected(self):
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def remove_selected(self):
        if self.busy():
            return
        for row in reversed(self.selected()):
            for values in (self.files, self.states, self.results):
                values.pop(row)
        self.refresh()

    def clear(self):
        if not self.busy():
            self.files.clear(); self.states.clear(); self.results.clear()
            self.refresh()

    def move(self, direction):
        if self.busy():
            return
        selected = self.selected()
        if len(selected) != 1:
            self.summary.setText('请选择一个文件调整顺序')
            return
        row, = selected
        target = row + direction
        if 0 <= target < len(self.files):
            for values in (self.files, self.states, self.results):
                values[row], values[target] = values[target], values[row]
            self.refresh()
            self.table.selectRow(target)

    def dragEnterEvent(self, event):
        if not self.busy() and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files(url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile())
        event.acceptProposedAction()

    def open_result(self, row, column):
        if self.results[row]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.results[row]))

    def open_output(self):
        path = Path(self.output.text()).expanduser()
        if self.output.text() and path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        else:
            self.summary.setText('请先选择有效的输出文件夹')

    def copy_logs(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.summary.setText('日志已复制')

    def save_logs(self):
        name, _ = QFileDialog.getSaveFileName(self, '保存日志', 'hugemark.log', '日志 (*.log)')
        if name:
            try:
                Path(name).write_text(self.log.toPlainText(), encoding='utf-8')
            except OSError as error:
                QMessageBox.warning(self, '无法保存日志', str(error))

    def save_settings(self):
        for key in ('binary', 'python', 'chrome', 'output'):
            self.settings.setValue(key, getattr(self, key).text())

    def start(self, convert):
        if self.busy():
            return
        config = tuple(field.text().strip() for field in (self.binary, self.python, self.chrome))
        destination = self.output.text().strip()
        if not config[0] or not config[1] or (convert and (not self.files or not destination)):
            QMessageBox.warning(self, '还差一步', '请配置程序和 Python；转换前还需添加文件并选择输出文件夹。')
            return
        self.save_settings()
        if convert:
            self.states = ['待处理'] * len(self.files)
            self.results = [''] * len(self.files)
            self.refresh()
        self.tabs.setCurrentIndex(0)
        self.progress.setRange(0, 0)
        self.badge.setText('正在检查环境')
        self.summary.setText('正在验证依赖、浏览器和 PDF 渲染…')
        for widget in self.controls:
            widget.setEnabled(False)
        self.stop_button.setEnabled(convert)
        self.worker = Worker(config, list(self.files), destination, convert, self)
        self.worker.event.connect(self.handle_event)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def handle_event(self, event):
        kind, *data = event
        if kind == 'log':
            self.log.appendPlainText(data[0])
        elif kind == 'checked':
            self.badge.setText('环境检查通过')
            self.progress.setRange(0, max(1, len(self.files)))
            self.progress.setValue(0)
        elif kind == 'status':
            row, state, *output = data
            self.states[row] = state
            self.results[row] = output[0] if output else ''
            self.refresh()
            self.table.scrollToItem(self.table.item(row, 0))
            completed = sum(s in ('完成', '失败', '未处理') for s in self.states)
            self.progress.setValue(completed)
            self.summary.setText(f'{row + 1} / {len(self.files)} · {Path(self.files[row]).name} · {state}')
        elif kind == 'done':
            self.progress.setRange(0, max(1, len(self.files)))
            if not data[0]:
                self.badge.setText('检查或任务失败')
                self.summary.setText('未能继续，请查看运行日志')
            elif self.worker.convert:
                self.summary.setText(f'完成 {self.states.count("完成")} · 失败 {self.states.count("失败")} · 未处理 {self.states.count("未处理")}')
            else:
                self.summary.setText('环境检查通过，可以开始转换')
                self.progress.setValue(self.progress.maximum())

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        for widget in self.controls:
            widget.setEnabled(True)
        self.stop_button.setEnabled(False)

    def request_stop(self):
        if self.worker:
            self.worker.stop.set()
            self.stop_button.setEnabled(False)
            self.summary.setText('将在当前检查或文件完成后停止')

    def closeEvent(self, event):
        if self.busy():
            QMessageBox.information(self, '任务正在运行', '请先点击“完成当前文件后停止”，等待当前操作结束后关闭。')
            event.ignore()
        else:
            self.save_settings()
            event.accept()


def launch():
    app = QApplication(sys.argv)
    configure(app)
    window = Window()
    window.show()
    sys.exit(app.exec())
