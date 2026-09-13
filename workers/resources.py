"""Inventory local dependencies for resume validation, including CSS imports."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import url2pathname
from lxml import html


def inventory(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding="utf-8"))
    dependencies = {}
    visited = set()

    def visit(value, base):
        address = urljoin(base, value)
        parsed = urlparse(address)
        if parsed.scheme != 'file':
            return
        path = Path(url2pathname(('//' + parsed.netloc if parsed.netloc else '') + parsed.path)).resolve()
        if path in visited:
            return
        visited.add(path)
        if not path.is_file():
            raise FileNotFoundError(f'Local resource does not exist: {path}')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while data := stream.read(1024 * 1024):
                digest.update(data)
        dependencies[str(path)] = digest.hexdigest()
        if path.suffix.lower() in ('.css', '.svg'):
            text = path.read_text(encoding="utf-8")
            for url in re.findall(r'''url\(\s*["']?([^)'"\s]+)|@import\s+["']([^"']+)''', text):
                visit(url[0] or url[1], path.as_uri())
            if path.suffix.lower() == '.svg':
                for url in re.findall(r'''(?:xlink:)?href=["']([^"']+)["']''', text):
                    if not url.startswith('#'):
                        visit(url, path.as_uri())

    for chunk in manifest['chunks']:
        path = directory / (chunk['id'] + '.html')
        tree = html.parse(str(path))
        base = tree.xpath('//base/@href')[0]
        for value in tree.xpath('//img/@src | //source/@src | //video/@poster | //link[@rel="stylesheet"]/@href | //iframe/@src | //object/@data'):
            visit(value, base)
        for text in tree.xpath('//style/text() | //@style'):
            for match in re.findall(r'''url\(\s*["']?([^)'"\s]+)|@import\s+["']([^"']+)''', text):
                visit(match[0] or match[1], base)
    (directory / 'resources.json').write_text(json.dumps(dependencies, indent=2), encoding="utf-8")

if __name__ == '__main__':
    inventory(sys.argv[1])
