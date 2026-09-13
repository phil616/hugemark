"""Real Chromium tests plus deterministic worker fault injection. Run from repo root."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import pikepdf

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / os.environ.get('HUGEMARK_BIN', 'target/debug/hugemark')

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.md'
        self.build = self.root / 'build'
        self.pdf = self.root / 'output.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def run_build(self, *extra, success=True):
        result = subprocess.run([str(BIN), 'build', str(self.source), '-o', str(self.pdf), '--build-dir', str(self.build), '--chunk-bytes', '8192', *extra], cwd=ROOT, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def manifest(self):
        return json.loads((self.build / 'manifest.json').read_text())

    def test_real_cross_chunk_links_and_resume(self):
        self.source.write_text('[跳到最后](#最后)\n\n' + ('一段中文 mixed prose。' * 100 + '\n\n') * 8 + '# 最后\n\nFINAL-SENTINEL\n')
        self.run_build()
        m = self.manifest()
        self.assertGreater(len(m['chunks']), 1)
        times = {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')}
        self.run_build('--resume')
        self.assertEqual(times, {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')})
        with pikepdf.Pdf.open(self.pdf) as pdf:
            target_page = pdf.pages[-1].obj.objgen
            links = [a for p in pdf.pages for a in p.obj.get('/Annots', []) if '/Dest' in a]
            self.assertTrue(any(a.Dest[0].objgen == target_page for a in links))
            with pdf.open_outline() as outline:
                self.assertEqual(outline.root[0].title, '最后')
        extracted = subprocess.check_output(['pdftotext', str(self.pdf), '-']).decode()
        self.assertIn('FINAL-SENTINEL', extracted)
        self.assertIn('中文', extracted)
        # A damaged cached PDF must be re-rendered.
        victim = self.build / (m['chunks'][0]['id'] + '.pdf')
        victim.write_bytes(b'broken')
        self.run_build('--resume')
        self.assertTrue(victim.read_bytes().startswith(b'%PDF-'))

    def test_crash_splits_and_resume(self):
        self.source.write_text(('Paragraph content ' * 25 + '\n\n') * 16)
        worker = self.root / 'worker'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' + '''import os, sys, signal
from pathlib import Path
import pikepdf
source = Path(sys.argv[1]).read_text()
if source.count('<p>') > 2:
    os.kill(os.getpid(), signal.SIGKILL)
pdf = pikepdf.Pdf.new()
pdf.add_blank_page()
pdf.save(sys.argv[2])
''')
        worker.chmod(0o755)
        self.run_build('--renderer', str(worker), '--retries', '0')
        m = self.manifest()
        self.assertTrue(all(c['complete'] for c in m['chunks']))
        self.assertTrue(any(c['depth'] > 0 for c in m['chunks']))
        self.assertIn('split', (self.build / 'events.jsonl').read_text())
        self.run_build('--renderer', str(worker), '--retries', '0', '--resume')

    def test_identical_content_chunks_have_independent_cache_entries(self):
        self.source.write_text(('重复 content ' * 100 + '\n\n') * 20)
        self.run_build()
        chunks = self.manifest()['chunks']
        self.assertGreater(len(chunks), 2)
        self.assertEqual(len({c['id'] for c in chunks}), len(chunks))
        times = {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')}
        self.run_build('--resume')
        self.assertEqual(times, {p.name: p.stat().st_mtime_ns for p in self.build.glob('*.pdf')})
        text = subprocess.check_output(['pdftotext', str(self.pdf), '-']).decode()
        self.assertEqual(''.join(text.split()).count('重复'), 2000)

    def test_partial_failure_resume_preserves_completed_chunks(self):
        self.source.write_text(''.join(f'Paragraph {i}: ' + 'content ' * 200 + '\n\n' for i in range(15)) + 'FAIL_UNTIL_FIXED\n')
        worker = self.root / 'recoverable-worker'
        fixed = self.root / 'fixed'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' +
            'import sys\nfrom pathlib import Path\nimport pikepdf\n' +
            f'fixed = Path({str(fixed)!r})\n' +
            "if 'FAIL_UNTIL_FIXED' in Path(sys.argv[1]).read_text() and not fixed.exists():\n    sys.exit(42)\n" +
            'pdf = pikepdf.Pdf.new()\npdf.add_blank_page()\npdf.save(sys.argv[2])\n')
        worker.chmod(0o755)
        options = ['--renderer', str(worker), '--retries', '0', '--max-split-depth', '0']
        self.run_build(*options, success=False)
        previous = self.manifest()
        completed = [c for c in previous['chunks'] if c['complete']]
        self.assertGreater(len(completed), 0)
        self.assertLess(len(completed), len(previous['chunks']))
        times = {c['id']: (self.build / (c['id'] + '.pdf')).stat().st_mtime_ns for c in completed}
        fixed.touch()
        self.run_build(*options, '--resume')
        self.assertTrue(all(c['complete'] for c in self.manifest()['chunks']))
        self.assertEqual(times, {name: (self.build / (name + '.pdf')).stat().st_mtime_ns for name in times})
        with pikepdf.Pdf.open(self.pdf) as pdf:
            self.assertEqual(len(pdf.pages), len(previous['chunks']))

    def test_actual_chromium_crash_is_retried(self):
        self.source.write_text('# Real Chrome crash\n\n中文 sentinel')
        worker = self.root / 'chrome-crash-worker'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' + "import os, signal, subprocess, sys, time\nfrom pathlib import Path\nstate = Path(__file__).with_suffix('.killed')\ncommand = [sys.executable, str(Path(sys.argv[1]).parent / 'render.py'), *sys.argv[1:]]\nif state.exists():\n    os.execv(sys.executable, command)\nchild = subprocess.Popen(command)\ndeadline = time.monotonic() + 20\nwhile time.monotonic() < deadline:\n    rows = {}\n    for path in Path('/proc').iterdir():\n        try:\n            stat = (path / 'stat').read_text()\n            fields = stat[stat.rfind(')')+2:].split()\n            rows[int(path.name)] = (int(fields[1]), (path / 'comm').read_text().strip())\n        except (OSError, ValueError):\n            pass\n    owned = {child.pid}\n    for _ in range(10):\n        owned |= {pid for pid, (parent, _) in rows.items() if parent in owned}\n    browsers = sorted(pid for pid in owned if rows.get(pid, (0,''))[1] == 'chrome')\n    if browsers:\n        os.kill(browsers[0], signal.SIGKILL)\n        state.write_text('actual Chromium was killed')\n        sys.exit(child.wait())\n    time.sleep(.01)\nchild.kill()\nraise RuntimeError('No Chromium found for fault injection')\n")
        worker.chmod(0o755)
        self.run_build('--renderer', str(worker), '--retries', '1')
        self.assertTrue(worker.with_suffix('.killed').exists())
        chunk = self.manifest()['chunks'][0]
        self.assertTrue(chunk['complete'])
        self.assertEqual(chunk['attempts'], 2)
        text = subprocess.check_output(['pdftotext', str(self.pdf), '-']).decode()
        self.assertIn('sentinel', text)

    def test_highlighter_preserves_code_whitespace(self):
        html_path = self.root / 'code.html'
        code = "\n\nprint('中文')\n\n"
        html_path.write_text('<html><head><meta charset="utf-8"></head><body><pre><code class="language-python">' + code + '</code></pre></body></html>')
        script = "from workers.render import prepare; from lxml import html; from pathlib import Path; import json,sys; print(json.dumps(html.parse(str(prepare(Path(sys.argv[1])))).find('.//code').text_content()))"
        result = subprocess.check_output([str(ROOT / '.venv/bin/python'), '-c', script, str(html_path)], cwd=ROOT)
        self.assertEqual(json.loads(result), code)

    def test_malformed_pdf_is_not_cached(self):
        self.source.write_text('single block')
        worker = self.root / 'bad-worker'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' +
            'import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_bytes(b"%PDF-1.7\\nnot a PDF\\n%%EOF")\n')
        worker.chmod(0o755)
        self.run_build('--renderer', str(worker), '--retries', '1', success=False)
        chunk = self.manifest()['chunks'][0]
        self.assertFalse(chunk['complete'])
        self.assertEqual(chunk['attempts'], 2)

    def test_single_block_adaptive_split(self):
        self.source.write_text('中文 content ' * 180)
        worker = self.root / 'small-worker'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' + "import sys\nfrom pathlib import Path\nimport pikepdf\nfrom lxml import html\ntext = html.parse(sys.argv[1]).find('.//article').text_content()\nif len(text) > 400:\n    sys.exit(42)\npdf = pikepdf.Pdf.new()\npdf.add_blank_page()\npdf.save(sys.argv[2])\n")
        worker.chmod(0o755)
        self.run_build('--renderer', str(worker), '--retries', '0')
        self.assertTrue(all(c['complete'] for c in self.manifest()['chunks']))
        self.assertTrue(any(c['depth'] > 0 for c in self.manifest()['chunks']))

    def test_resource_change_invalidates_resume(self):
        resource = self.root / 'image.svg'
        resource.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>')
        self.source.write_text('![test](image.svg)')
        self.run_build()
        resource.write_text(resource.read_text().replace('red', 'blue'))
        self.assertIn('resources changed', self.run_build('--resume', success=False).stderr)

    def test_footnotes_across_chunks(self):
        self.source.write_text('Reference[^n].\n\n' + ('中文 paragraph ' * 100 + '\n\n') * 10 + '[^n]: Footnote sentinel.\n')
        self.run_build()
        report = json.loads((self.build / 'assembly.json').read_text())
        self.assertEqual(report['unresolved_links'], [])
        self.assertGreaterEqual(report['targets'], 2)
        with pikepdf.Pdf.open(self.pdf) as pdf:
            links = [a for p in pdf.pages for a in p.obj.get('/Annots', []) if '/Dest' in a]
            self.assertGreaterEqual(len(links), 2)
        text = subprocess.check_output(['pdftotext', str(self.pdf), '-']).decode()
        self.assertIn('Footnote sentinel.', text)

    def test_timeout_cleans_detached_grandchild(self):
        self.source.write_text('single block')
        worker = self.root / 'detached-worker'
        pidfile = self.root / 'descendant.pid'
        worker.write_text('#!' + str(ROOT / '.venv/bin/python') + '\n' +
            'import subprocess, time\nfrom pathlib import Path\n' +
            'p = subprocess.Popen(["sleep", "30"], start_new_session=True)\n' +
            f'Path({str(pidfile)!r}).write_text(str(p.pid))\n' +
            'time.sleep(30)\n')
        worker.chmod(0o755)
        self.run_build('--renderer', str(worker), '--timeout', '1', '--retries', '0', success=False)
        pid = int(pidfile.read_text())
        proc = Path('/proc') / str(pid) / 'stat'
        self.assertTrue(not proc.exists() or ') Z ' in proc.read_text())

    def test_output_cannot_overwrite_markdown(self):
        self.source.write_text('preserve this')
        result = subprocess.run([str(BIN), 'build', str(self.source), '-o', os.path.relpath(self.source, ROOT), '--build-dir', str(self.build)], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('output must not overwrite input', result.stderr)
        self.assertEqual(self.source.read_text(), 'preserve this')

    def test_timeout_is_bounded_and_manifest_survives(self):
        self.source.write_text('single block')
        worker = self.root / 'sleep'
        worker.write_text('#!/bin/sh\nsleep 30\n')
        worker.chmod(0o755)
        result = self.run_build('--renderer', str(worker), '--timeout', '1', '--retries', '0', success=False)
        self.assertIn('timeout', result.stderr)
        self.assertFalse(self.manifest()['chunks'][0]['complete'])

if __name__ == '__main__':
    (ROOT / 'tmp').mkdir(exist_ok=True)
    unittest.main(verbosity=2)
