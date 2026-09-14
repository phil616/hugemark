#!/usr/bin/env python3
"""Hugemark desktop launcher. Qt front end with a reusable serial rendering backend."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent


def default_binary():
    suffix = '.exe' if os.name == 'nt' else ''
    for path in (ROOT / ('hugemark' + suffix), ROOT / ('hugemark-windows-amd64.exe' if os.name == 'nt' else 'hugemark-linux-amd64'), ROOT / 'target/release' / ('hugemark' + suffix)):
        if path.is_file():
            return str(path)
    return shutil.which('hugemark') or ''


def default_python():
    local = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    return str(local) if local.is_file() else sys.executable


def capture(args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError(result.stdout.strip() or f'程序退出码 {result.returncode}')
    return result.stdout.strip()


def render(binary, python, chrome, source, output, work, log):
    args = [binary, 'build', str(source), '-o', str(output), '--build-dir', str(work),
            '--python', python, '--chrome', chrome or 'auto', '--timeout', '120', '--retries', '0']
    env = dict(os.environ, PYTHONUTF8='1')
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding='utf-8', errors='replace', env=env,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
        for line in process.stdout:
            log(line.rstrip())
        code = process.wait()
    if code:
        for path in sorted(work.glob('*.log')):
            log(f'{path.name}:\n{path.read_text(encoding="utf-8", errors="replace")[-8000:]}')
        raise RuntimeError(f'转换失败（退出码 {code}），详见日志：{work}')
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError('程序未生成有效输出文件')


def check_dependencies(binary, python, chrome, log):
    if not binary or not python:
        raise ValueError('请选择 Hugemark 程序和 Python 解释器')
    version = capture([binary, '--version'])
    if not version.startswith('hugemark '):
        raise RuntimeError('选择的程序不是 Hugemark')
    log('✓ ' + version)
    requirements = capture([binary, 'requirements']).splitlines()
    probe = '''import sys,json,importlib,importlib.metadata
assert sys.version_info >= (3,12), '需要 Python 3.12 或更新版本'
for name in ['playwright.sync_api','pikepdf','pygments','lxml.html']:
    importlib.import_module(name)
print(json.dumps({n:importlib.metadata.version(n) for n in ['playwright','pikepdf','Pygments','lxml']}))
'''
    versions = json.loads(capture([python, '-c', probe]))
    for requirement in requirements:
        if '==' not in requirement:
            continue
        name, expected = requirement.split('==', 1)
        actual = versions.get(name)
        if actual != expected:
            raise RuntimeError(f'{name} 需要 {expected}，当前为 {actual}。请按所选二进制的 requirements 安装依赖。')
        log(f'✓ {name} {actual}')
    log('正在实测浏览器、MathJax、Mermaid 和 PDF 合并…')
    with tempfile.TemporaryDirectory(prefix='hugemark-check-') as temp:
        folder = Path(temp)
        source = folder / 'check.md'
        source.write_text('# 环境检查\n\n中文 English $x^2$\n\n```mermaid\nflowchart LR\nA[Input] --> B[PDF]\n```\n', encoding='utf-8')
        render(binary, python, chrome, source, folder / 'check.pdf', folder / 'work', log)
    log('✓ 依赖与完整渲染链检查通过。中文字体外观仍取决于系统安装的字体。')


def batch(binary, python, chrome, sources, directory, stop, emit):
    """One blocking render at a time. Atomically reserve names; never overwrite PDFs."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources):
        if stop.is_set():
            emit('status', index, '未处理')
            continue
        output = None
        try:
            source = Path(source)
            if not source.is_file():
                raise FileNotFoundError(f'输入文件不存在：{source}')
            number = 1
            while True:
                name = source.stem + (f' ({number})' if number > 1 else '') + '.pdf'
                candidate = directory / name
                try:
                    with candidate.open('xb'):
                        pass
                    output = candidate
                    break
                except FileExistsError:
                    number += 1
            emit('status', index, '处理中')
            # Unique work folders isolate duplicate basenames and concurrent GUI instances.
            work_root = directory / '.hugemark-gui'
            work_root.mkdir(exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix='job-', dir=work_root))
            render(binary, python, chrome, source, output, work, lambda text: emit('log', text))
            emit('status', index, '完成', str(output))
        except Exception as error:
            if output is not None and output.exists() and output.stat().st_size == 0:
                output.unlink()
            emit('log', str(error))
            emit('status', index, '失败')


def main():
    try:
        from desktop import launch
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith('PySide6'):
            raise SystemExit('请先安装 Qt GUI 依赖：python -m pip install -r requirements-gui.txt') from error
        raise
    launch()


if __name__ == '__main__':
    main()
