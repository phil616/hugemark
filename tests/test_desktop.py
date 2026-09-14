"""Qt interaction, font coverage, thread lifecycle and actual render smoke tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings, Qt, QMimeData, QUrl, QPointF
from PySide6.QtGui import QFontMetrics, QDropEvent
from PySide6.QtTest import QTest
from desktop import QApplication, Window, configure
import gui


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qt-中文-')
        self.root = Path(self.temp.name)
        self.window = Window(QSettings(str(self.root / 'settings.ini'), QSettings.IniFormat))
        self.window.show()
        self.sources = [self.root / name for name in ['中文 空格.md', '日本語한국어.md']]
        for source in self.sources:
            source.write_text('# 中文\n\n$x^2$\n\n```mermaid\nflowchart LR\nA --> B\n```', encoding='utf-8')

    def tearDown(self):
        self.assertFalse(self.window.busy())
        self.window.close()
        self.temp.cleanup()

    def wait_done(self):
        deadline = time.monotonic() + 90
        while self.window.busy():
            self.app.processEvents()
            QTest.qWait(20)
            if time.monotonic() > deadline:
                self.fail('Worker did not finish')
        self.app.processEvents()

    def test_fonts_drop_reorder_and_settings(self):
        metrics = QFontMetrics(self.app.font())
        for character in '中文日本語한국어':
            self.assertTrue(metrics.inFont(character), character)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in self.sources])
        event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        self.window.dropEvent(event)
        self.window.add_files(self.sources)  # Deduplicate.
        self.assertEqual(len(self.window.files), 2)
        self.window.table.selectRow(1)
        self.window.move(-1)
        self.assertEqual(self.window.files[0], str(self.sources[1].resolve()))
        self.assertEqual(self.window.table.item(0, 0).toolTip(), str(self.sources[1].resolve()))
        self.window.output.setText(str(self.root / '输出'))
        self.window.save_settings()
        self.assertEqual(self.window.settings.value('output'), str(self.root / '输出'))
        self.window.table.selectRow(0)
        self.window.remove_selected()
        self.assertEqual(len(self.window.files), 1)

    def test_preflight_error_restores_controls(self):
        with patch.object(gui, 'check_dependencies', side_effect=RuntimeError('缺少组件')):
            self.window.binary.setText('fake')
            self.window.python.setText('python')
            self.window.start(False)
            self.assertFalse(self.window.start_button.isEnabled())
            self.wait_done()
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertIn('缺少组件', self.window.log.toPlainText())
        self.assertIn('失败', self.window.badge.text())

    def test_stop_and_edit_lock(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        calls = []
        def render(binary, python, chrome, source, output, work, log):
            calls.append(source)
            entered.set()
            release.wait(5)
            output.write_bytes(b'pdf')
        self.window.binary.setText('fake')
        self.window.python.setText('python')
        self.window.output.setText(str(self.root / 'output'))
        self.window.add_files(self.sources)
        with patch.object(gui, 'check_dependencies'), patch.object(gui, 'render', side_effect=render):
            self.window.start(True)
            self.assertTrue(entered.wait(5))
            self.window.clear()
            self.assertEqual(len(self.window.files), 2)
            self.window.request_stop()
            release.set()
            self.wait_done()
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.window.states, ['完成', '未处理'])

    def test_real_serial_conversion(self):
        binary = Path(os.environ.get('HUGEMARK_BIN', gui.default_binary())).resolve()
        if not binary.is_file():
            self.skipTest('Build Hugemark before running the PDF smoke test')
        self.window.binary.setText(str(binary))
        self.window.python.setText(sys.executable)
        self.window.output.setText(str(self.root / '输出'))
        self.window.add_files(self.sources)
        self.window.start(True)
        self.assertFalse(self.window.output.isEnabled())
        self.wait_done()
        self.assertEqual(self.window.states, ['完成', '完成'], self.window.log.toPlainText())
        self.assertTrue(all(Path(p).is_file() for p in self.window.results))
        self.assertEqual(self.window.progress.value(), 2)
        self.assertTrue(self.window.start_button.isEnabled())


if __name__ == '__main__':
    unittest.main(verbosity=2)
