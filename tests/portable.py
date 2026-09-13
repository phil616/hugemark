"""Release gates that run unchanged on Linux and Windows amd64."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from lxml import html
import pikepdf

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / os.environ.get('HUGEMARK_BIN', 'target/debug/hugemark' + ('.exe' if os.name == 'nt' else ''))

class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hugemark-中文-')
        self.directory = Path(self.temporary.name)
        self.source = self.directory / '文档.md'
        self.output = self.directory / '输出.pdf'
        self.build = self.directory / '构建'

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *extra):
        return [str(BIN), 'build', str(self.source), '-o', str(self.output), '--build-dir', str(self.build), '--python', sys.executable, *extra]

    def run_build(self, *extra, success=True):
        result = subprocess.run(self.command(*extra), capture_output=True, text=True, encoding='utf-8', timeout=120)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def manifest(self):
        return json.loads((self.build / 'manifest.json').read_text(encoding='utf-8'))

    def test_math_mermaid_unicode_and_resume(self):
        self.source.write_text((ROOT / 'tests/fixtures/advanced.md').read_text(encoding='utf-8'), encoding='utf-8')
        self.run_build()
        m = self.manifest()
        self.assertTrue(all(c['complete'] and c['peak_rss_kib'] > 0 for c in m['chunks']))
        markup = ''.join((self.build / (c['id'] + '.ready.html')).read_text(encoding='utf-8') for c in m['chunks'])
        tree = html.fromstring(markup)
        self.assertGreaterEqual(len(tree.xpath('//svg')), 7)
        self.assertFalse(tree.xpath('//*[@data-math-style] | //code[@class="language-mermaid"] | //script | //mjx-assistive-mml'))
        with pikepdf.Pdf.open(self.output) as pdf:
            self.assertGreater(len(pdf.pages), 0)
            self.assertEqual(str(pdf.docinfo['/Title']), '文档')
            with pdf.open_outline() as outline:
                self.assertEqual(outline.root[0].title, '公式与图表')
        times = {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')}
        self.run_build('--resume')
        self.assertEqual(times, {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')})

    def test_formula_cache_integrity_and_duplicate_svg_ids(self):
        self.source.write_text('$x^2$ 和 $x^2$\n\n$$x^2$$', encoding='utf-8')
        self.run_build()
        cache = list((self.build / 'components').glob('*.svg.html'))
        self.assertEqual(len(cache), 2)
        for p in cache:
            p.write_text('corrupt', encoding='utf-8')
        self.run_build()  # Rebuild PDF while recovering corrupt component cache.
        for p in cache:
            self.assertIn('<svg', p.read_text(encoding='utf-8'))
        text = next(self.build.glob('*.ready.html')).read_text(encoding='utf-8')
        ids = html.fromstring(text).xpath('//*[@id]/@id')
        self.assertEqual(len(ids), len(set(ids)))

    def test_invalid_components_fail_and_source_mode_recovers(self):
        for source in ('$$\\notARealCommand{x}$$', '```mermaid\nflowchart ???\n```'):
            self.source.write_text(source, encoding='utf-8')
            self.run_build('--retries', '0', '--max-split-depth', '0', success=False)
            self.assertFalse(any(c['complete'] for c in self.manifest()['chunks']))
            self.run_build('--no-advanced')

    def test_custom_css_and_resume_invalidation(self):
        self.source.write_text('# Styled\n\nText.', encoding='utf-8')
        css = self.directory / '样式.css'
        css.write_text('@page{size:A5} h1{color:#773388}', encoding='utf-8')
        self.run_build('--css', str(css))
        with pikepdf.Pdf.open(self.output) as pdf:
            self.assertLess(float(pdf.pages[0].MediaBox[2]), 450)
        css.write_text('@page{size:A4}', encoding='utf-8')
        self.assertIn('settings changed', self.run_build('--css', str(css), '--resume', success=False).stderr)

    def test_lock_and_timeout_cleanup(self):
        self.source.write_text('Worker lifecycle.', encoding='utf-8')
        # A portable fake Python interpreter launches a detached descendant then waits.
        # Use a Python shim with an executable launcher on each platform.
        shim = self.directory / 'shim.py'
        pid_file = self.directory / 'pid.txt'
        shim.write_text('import subprocess,sys,time,os\nfrom pathlib import Path\nos.environ.pop("PYTHONPATH",None)\n'
                        'flags = {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform=="win32" else {"start_new_session":True}\n'
                        'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(90)"],**flags)\n'
                        f'Path({str(pid_file)!r}).write_text(str(p.pid))\n'
                        'time.sleep(90)\n', encoding='utf-8')
        # Python startup hook simulates a hung worker with a detached descendant.
        customization = self.directory / 'sitecustomize.py'
        customization.write_text('exec(' + repr(shim.read_text(encoding='utf-8')) + ')\n', encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(self.directory))
        process = subprocess.Popen(self.command('--timeout', '3', '--retries', '0'), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not pid_file.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(pid_file.exists())
            locked = subprocess.run([str(BIN), 'plan', str(self.source), '--build-dir', str(self.build)], capture_output=True, text=True)
            self.assertNotEqual(locked.returncode, 0)
            self.assertIn('another build', locked.stderr)
            _, error = process.communicate(timeout=15)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn(b'timeout', error)
            pid = int(pid_file.read_text())
            if os.name == 'nt':
                import ctypes
                ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
                ctypes.windll.kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    status = ctypes.c_ulong()
                    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(status))
                    ctypes.windll.kernel32.CloseHandle(handle)
                    self.assertNotEqual(status.value, 259)
            else:
                stat = Path('/proc') / str(pid) / 'stat'
                self.assertTrue(not stat.exists() or ') Z ' in stat.read_text())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

if __name__ == '__main__':
    unittest.main(verbosity=2)
