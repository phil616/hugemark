"""One isolated invocation per chunk. No Markdown parsing in Chromium."""
import argparse
import json
import os
import shutil
from pathlib import Path
from lxml import html as LH
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from playwright.sync_api import sync_playwright


def find_chrome(requested='auto'):
    if requested != 'auto':
        return requested
    candidates = [os.environ.get('CHROME_PATH', '')]
    candidates += [shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome', 'msedge')]
    if os.name == 'nt':
        for root in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            for suffix in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'):
                candidates.append(str(Path(os.environ.get(root, '')) / suffix))
    for path in candidates:
        if path and Path(path).is_file():
            return str(Path(path).resolve())
    raise RuntimeError('Chrome/Chromium not found. Install it or pass --chrome PATH.')


def prepare(path, chrome=None, timeout=90000, theme="default", advanced=False):
    tree = LH.parse(str(path), parser=LH.HTMLParser(encoding="utf-8"))
    if advanced:
        from advanced import render_components
        render_components(tree, path.parent, chrome, timeout, theme)
    for code in tree.xpath('//pre/code'):
        language = code.get('class', '').removeprefix('language-').split(' ')[0]
        try:
            lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
        except ClassNotFound:
            continue
        rendered = highlight(code.text_content(), lexer, HtmlFormatter(nowrap=True))
        code.set('class', (code.get('class', '') + ' hm-highlight').strip())
        fragment = LH.fragment_fromstring('<div>' + rendered + '</div>')
        code.text = fragment.text
        for child in list(code):
            code.remove(child)
        for child in list(fragment):
            code.append(child)
    for element in tree.xpath('//*[@id and not(ancestor-or-self::svg)]'):
        if element.get('class') == 'hm-anchor':
            continue
        marker = LH.Element('a', {'class': 'hm-anchor', 'href': 'https://hugemark.invalid/dest/' + element.get('id')})
        marker.text = '\u200b'
        if element.tag not in ('img', 'input', 'br', 'hr', 'meta', 'link'):
            container = element
            while len(container) and container[0].tag in ('p', 'div', 'section', 'article', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td'):
                container = container[0]
            container.insert(0, marker)
    for anchor in tree.xpath('//a[@href]'):
        if anchor.get('href', '').startswith('#'):
            anchor.set('href', 'https://hugemark.invalid/link/' + anchor.get('href')[1:])
    style = LH.Element('style')
    style.text = HtmlFormatter().get_style_defs('.hm-highlight')
    head = tree.find('.//head')
    links = head.xpath('./link[@rel="stylesheet"]')
    if links:
        head.insert(head.index(links[0]), style)
    else:
        head.append(style)
    target = path.with_suffix('.ready.html')
    tree.write(str(target), encoding='utf-8', method='html', doctype='<!doctype html>')
    return target


def main():
    p = argparse.ArgumentParser()
    p.add_argument('html', type=Path)
    p.add_argument('pdf', type=Path)
    p.add_argument('--chrome', default='auto')
    p.add_argument('--mermaid-theme', default='default')
    p.add_argument('--no-advanced', action='store_true')
    p.add_argument('--timeout', type=int, default=90000)
    p.add_argument('--allow-remote', action='store_true')
    args = p.parse_args()
    args.chrome = find_chrome(args.chrome)
    ready = prepare(args.html, args.chrome, args.timeout, args.mermaid_theme, not args.no_advanced)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.chrome, headless=True)
        context = browser.new_context(java_script_enabled=False)
        if not args.allow_remote:
            context.route('http://**/*', lambda route: route.abort())
            context.route('https://**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(args.timeout)
        page.goto(ready.resolve().as_uri(), wait_until='load', timeout=args.timeout)
        page.emulate_media(media='print')
        page.evaluate('document.fonts.ready')
        broken = page.locator('img').evaluate_all('(images) => images.filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)')
        if broken:
            raise RuntimeError('Images failed to load: ' + repr(broken[:5]))
        page.pdf(path=str(args.pdf), prefer_css_page_size=True, print_background=True)
        context.close()
        browser.close()
    print(json.dumps({'pdf_bytes': args.pdf.stat().st_size}))

if __name__ == '__main__':
    main()
