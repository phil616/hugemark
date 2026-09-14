"""Validate extracted release contents and both new/existing environment bootstrap paths."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


@unittest.skipUnless(os.environ.get('HUGEMARK_ARCHIVE'), 'Set HUGEMARK_ARCHIVE to test an actual release archive')
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hugemark-package-中文-')
        self.root = Path(self.temp.name)
        archive = Path(os.environ['HUGEMARK_ARCHIVE']).resolve()
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(self.root)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(self.root, filter='data')
        self.folder = next(self.root.iterdir())
        self.windows = os.name == 'nt'
        self.binary = self.folder / ('hugemark-windows-amd64.exe' if self.windows else 'hugemark-linux-amd64')
        self.script = self.folder / ('hugemark-init.ps1' if self.windows else 'hugemark-init.sh')
        self.command = [shutil.which('pwsh'), '-NoProfile', '-File', str(self.script)] if self.windows else ['/bin/bash', str(self.script)]

    def tearDown(self):
        self.temp.cleanup()

    def run_init(self, env=None, success=True):
        result = subprocess.run(self.command, cwd=self.root, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace', timeout=480)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout[-18000:])
            self.assertIn('初始化成功', result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout[-18000:])
        return result.stdout

    def test_contents_and_missing_binary(self):
        names = {p.relative_to(self.folder).as_posix() for p in self.folder.rglob('*') if p.is_file()}
        self.assertEqual(names, {self.binary.name, self.script.name, 'gui.py', 'desktop.py',
                         'initialize_environment.py', 'requirements-gui.txt', 'LICENSE.txt', 'README.md',
                         'assets/desktop.qss', 'assets/fonts/NotoSansCJKsc-Regular.otf'})
        if not self.windows:
            self.assertTrue(os.access(self.binary, os.X_OK))
            self.assertTrue(os.access(self.script, os.X_OK))
        self.binary.unlink()
        self.assertIn('缺少', self.run_init(success=False))

    def test_broken_environment_rejected(self):
        (self.folder / '.venv').mkdir()
        self.assertIn('.venv', self.run_init(success=False))

    def test_install_and_reinstall(self):
        # Initial run tests uv if available; a second run must also perform installation.
        for _ in range(2):
            output = self.run_init()
            self.assertIn('每次执行均重新安装', output)
            self.assertTrue((self.folder / '.venv/pyvenv.cfg').is_file())
            self.assertTrue(Path((self.folder / '.hugemark-browser').read_text(encoding='utf-8')).is_file())
        python = self.folder / ('.venv/Scripts/python.exe' if self.windows else '.venv/bin/python')
        self.assertEqual(subprocess.run([str(python), '-c', 'import PySide6.QtWidgets,pikepdf,lxml,playwright'], check=True).returncode, 0)

    def test_no_python_and_pip_fallback(self):
        tool_dir = self.root / 'path'
        tool_dir.mkdir()
        env = dict(os.environ, PATH=str(tool_dir))
        self.assertIn('找不到可用', self.run_init(env, success=False))
        if self.windows:
            # Python installation root contains python.exe, but uv is in Scripts.
            env['PATH'] = os.pathsep.join([str(Path(sys._base_executable).parent),
                                          str(Path(os.environ['SystemRoot']) / 'System32')])
        else:
            (tool_dir / 'python3').symlink_to(Path(sys.executable).resolve())
        # Exclude uv from PATH; Python's venv/ensurepip path must work too.
        self.run_init(env)
        self.run_init(env)


if __name__ == '__main__':
    unittest.main(verbosity=2)
