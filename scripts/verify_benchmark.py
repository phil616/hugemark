#!/usr/bin/env python3
"""Prove the current planner/preprocessor produce the benchmark's exact HTML.

Useful when coordinator/cache validation changed during a long benchmark run.
Does not replace the real PDF, text and memory checks in benchmark.py.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--directory', type=Path, default=Path('tmp/benchmark'))
    p.add_argument('--binary', default='target/debug/hugemark')
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('hugemark_render', 'workers/render.py')
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)
    reports = []
    for result in json.loads((args.directory / 'results.json').read_text()):
        size = result['input_bytes'] // (1024 * 1024)
        baseline = args.directory / f'{size}mb-build'
        original = json.loads((baseline / 'manifest.json').read_text())
        assert all(c['complete'] for c in original['chunks'])
        with tempfile.TemporaryDirectory(dir=args.directory) as tmp:
            plan = Path(tmp)
            subprocess.run([args.binary, 'plan', str(args.directory / f'{size}mb.md'), '--build-dir', str(plan)], check=True)
            current = json.loads((plan / 'manifest.json').read_text())
            assert current['headings'] == original['headings']
            assert len(current['chunks']) == len(original['chunks'])
            digest = hashlib.sha256()
            for chunk, original_chunk in zip(current['chunks'], original['chunks'], strict=True):
                name = chunk['id']
                original_name = original_chunk['id']
                source = plan / (name + '.html')
                assert source.read_bytes() == (baseline / (original_name + '.html')).read_bytes()
                prepared = render.prepare(source)
                assert prepared.read_bytes() == (baseline / (original_name + '.ready.html')).read_bytes(), name
                digest.update(prepared.read_bytes())
            reports.append({'input_mib': size, 'chunks': len(current['chunks']), 'planner_html_identical': True,
                            'renderer_html_identical': True, 'combined_html_sha256': digest.hexdigest()})
            print(json.dumps(reports[-1]), flush=True)
    (args.directory / 'current-equivalence.json').write_text(json.dumps(reports, indent=2))

if __name__ == '__main__':
    main()
