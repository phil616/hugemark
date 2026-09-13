#!/usr/bin/env python3
"""Generate real mixed-content inputs, build every size, record renderer RSS."""
import argparse
import json
import subprocess
import time
from pathlib import Path


def generate(path, size):
    prose = '超大型文档应保持完整语义，中文 English 日本語 한국어，逐块排版并恢复结构。' * 25
    with path.open('w') as f:
        i = 0
        while f.tell() < size:
            f.write(f'\n# Section {i} 章节\n\nBEGIN-{i:06d}\n\n{prose}\n\n')
            f.write('| Feature | 内容 |\n|---|---|\n| Table | 表格与代码 |\n\n')
            f.write('- [x] 有界渲染\n- [ ] 可恢复构建\n\n')
            f.write(f'```python\n# 中文 comment {i}\nprint("section {i}")\n```\n\nEND-{i:06d}\n')
            i += 1
    return i


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sizes', nargs='+', type=int, default=[10, 20, 50])
    p.add_argument('--directory', type=Path, default=Path('tmp/benchmark'))
    p.add_argument('--binary', default='target/release/hugemark')
    a = p.parse_args()
    a.directory.mkdir(parents=True, exist_ok=True)
    results = []
    for size in a.sizes:
        source = a.directory / f'{size}mb.md'
        count = generate(source, size * 1024 * 1024)
        build = a.directory / f'{size}mb-build'
        output = a.directory / f'{size}mb.pdf'
        started = time.monotonic()
        with (a.directory / f'{size}mb.log').open('w') as log:
            subprocess.run([a.binary, 'build', str(source), '-o', str(output), '--build-dir', str(build)], stdout=log, stderr=log, check=True)
        m = json.loads((build / 'manifest.json').read_text())
        assembly = json.loads((build / 'assembly.json').read_text())
        text = subprocess.check_output(['pdftotext', str(output), '-']).decode()
        assert all(f'BEGIN-{i:06d}' in text and f'END-{i:06d}' in text for i in range(count))
        assert '中文' in text
        assert assembly['targets'] == count
        result = dict(input_bytes=source.stat().st_size, characters=len(source.read_text()), sections=count,
                      chunks=len(m['chunks']), pages=assembly['pages'], peak_worker_rss_kib=max(c['peak_rss_kib'] for c in m['chunks']),
                      largest_html_bytes=max((build / (c['id'] + '.html')).stat().st_size for c in m['chunks']),
                      pdf_bytes=output.stat().st_size, elapsed_seconds=round(time.monotonic()-started, 2), text_verified=True)
        results.append(result)
        (a.directory / 'results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)

if __name__ == '__main__':
    main()
