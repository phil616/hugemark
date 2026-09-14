"""Queue safety and preflight contract tests; no display needed."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gui


class QueueTests(unittest.TestCase):
    def test_serial_collision_failure_and_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'output'
            output.mkdir()
            (output / 'same.pdf').write_bytes(b'original')
            sources = []
            for name in ['a', 'b', 'c', 'd']:
                directory = root / name
                directory.mkdir()
                source = directory / 'same.md'
                source.write_text(name)
                sources.append(source)
            calls = []
            stop = threading.Event()
            events = []
            def fake_render(binary, python, chrome, source, target, work, log):
                calls.append(source.parent.name)
                if len(calls) == 2:
                    raise RuntimeError('broken input')
                target.write_bytes(b'pdf')
                if len(calls) == 3:
                    stop.set()
            with patch.object(gui, 'render', side_effect=fake_render):
                gui.batch('bin', 'python', 'auto', sources, output, stop, lambda *e: events.append(e))
            self.assertEqual(calls, ['a', 'b', 'c'])
            self.assertEqual((output / 'same.pdf').read_bytes(), b'original')
            self.assertEqual(len(list(output.glob('*.pdf'))), 3)
            self.assertEqual([e[2] for e in events if e[0] == 'status'],
                             ['处理中', '完成', '处理中', '失败', '处理中', '完成', '未处理'])
            self.assertEqual(len(list((output / '.hugemark-gui').iterdir())), 3)

    def test_dependency_mismatch_blocks_render(self):
        with patch.object(gui, 'capture', side_effect=['hugemark 0.2.1', 'playwright==1.62.0', '{"playwright":"0.0"}']), patch.object(gui, 'render') as render:
            with self.assertRaisesRegex(RuntimeError, 'playwright'):
                gui.check_dependencies('bin', 'python', 'auto', lambda s: None)
            render.assert_not_called()

    def test_missing_input_continues(self):
        with tempfile.TemporaryDirectory() as folder:
            events = []
            gui.batch('bin', 'python', 'auto', [Path(folder)/'missing.md'], folder,
                      threading.Event(), lambda *e: events.append(e))
            self.assertIn(('status', 0, '失败'), events)
            self.assertFalse(list(Path(folder).glob('*.pdf')))


if __name__ == '__main__':
    unittest.main()
