"""Offline, bounded math/diagram pre-rendering in a separate browser.

Only source strings reach the trusted library page; document HTML never executes.
The final print browser receives SVG and has JavaScript disabled.
"""
import hashlib
import json
import re
from pathlib import Path
from lxml import etree, html
from playwright.sync_api import sync_playwright


def render_components(tree, directory, chrome, timeout, theme='default'):
    components = []
    for node in tree.xpath('//*[@data-math-style]'):
        components.append((node, 'math', node.text_content(), node.get('data-math-style') == 'display'))
    for node in tree.xpath('//pre/code'):
        language = node.get('class', '').removeprefix('language-').split()[0] if node.get('class') else ''
        if language in ('mermaid', 'math', 'latex', 'tex'):
            components.append((node.getparent(), 'mermaid' if language == 'mermaid' else 'math', node.text_content(), True))
    if not components:
        return
    cache = directory / 'components'
    cache.mkdir(exist_ok=True)
    bundles = directory / 'mathjax.js', directory / 'mermaid.js'
    # Cache identity includes the renderer implementation and both pinned bundles.
    version = hashlib.sha256(Path(__file__).read_bytes())
    for bundle in bundles:
        version.update(bundle.read_bytes())
    styles = '\n'.join(tree.xpath('//head/style/text()'))
    version.update(styles.encode('utf-8'))
    version = version.hexdigest()
    pending = []
    for node, kind, source, display in components:
        key = hashlib.sha256(json.dumps([version, kind, source, display, theme], ensure_ascii=False).encode()).hexdigest()
        target = cache / (key + '.svg.html')
        pending.append((node, kind, source, display, target, key))
    def valid_cache(target):
        try:
            return hashlib.sha256(target.read_bytes()).hexdigest() == target.with_suffix('.sha256').read_text(encoding='ascii')
        except OSError:
            return False
    missing = [item for item in pending if not valid_cache(item[4])]
    if missing:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome, headless=True)
            context = browser.new_context()
            context.route('**/*', lambda route: route.abort())
            page = context.new_page()
            page.set_default_timeout(timeout)
            page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>')
            page.add_style_tag(content=styles)
            kinds = {item[1] for item in missing}
            if 'math' in kinds:
                page.evaluate("""() => {window.MathJax = {
                    startup: {typeset: false}, svg: {fontCache: 'local'},
                    tex: {packages: {'[-]': ['autoload', 'require', 'noundefined']}, maxBuffer: 32768}
                }}""")
                page.add_script_tag(path=str(bundles[0]))
                page.evaluate('MathJax.startup.promise')
            if 'mermaid' in kinds:
                page.add_script_tag(path=str(bundles[1]))
                page.evaluate("""theme => mermaid.initialize({
                    startOnLoad:false, securityLevel:'strict', theme,
                    maxTextSize:32768, maxEdges:1000, htmlLabels:false, fontFamily:'var(--sans),var(--cjk),sans-serif',
                    flowchart:{htmlLabels:false},
                    secure:['securityLevel','startOnLoad','maxTextSize','maxEdges','htmlLabels','flowchart']
                })""", theme)
            for _, kind, source, display, target, key in missing:
                try:
                    if kind == 'math':
                        if re.search(r'\\(?:global|gdef|def|edef|xdef|let|newcommand|renewcommand|providecommand|DeclareMathOperator|require)\b', source):
                            raise ValueError('Document-level TeX macros/loading are not supported; use self-contained expressions')
                        markup = page.evaluate("""async ({source,display}) => {
                            const node=await MathJax.tex2svgPromise(source,{display});
                            const error=node.querySelector('[data-mjx-error]');
                            if(error) throw new Error(error.getAttribute('data-mjx-error'));
                            node.querySelectorAll('mjx-assistive-mml').forEach(n => n.remove());
                            return node.outerHTML;
                        }""", {'source': source, 'display': display})
                    else:
                        markup = page.evaluate("""async ({source,id}) => {
                            const {svg}=await mermaid.render(id,source);
                            document.body.replaceChildren();
                            return svg;
                        }""", {'source': source, 'id': 'hm' + key[:24]})
                except Exception as error:
                    raise RuntimeError(f'{kind} rendering failed for {source[:120]!r}: {error}') from error
                temporary = target.with_suffix('.tmp')
                temporary.write_text(markup, encoding='utf-8')
                temporary.replace(target)
                temporary = target.with_suffix('.sha256.tmp')
                temporary.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding='ascii')
                temporary.replace(target.with_suffix('.sha256'))
            context.close()
            browser.close()
    for occurrence, (node, kind, source, display, target, key) in enumerate(pending):
        markup = target.read_text(encoding='utf-8')
        wrapper = html.Element('div' if display else 'span')
        wrapper.set('class', 'hm-diagram' if kind == 'mermaid' else ('hm-math-display' if display else 'hm-math-inline'))
        wrapper.set('aria-label', source)
        # Each inline SVG needs unique IDs even when its cached source repeats.
        component = html.fragment_fromstring(markup)
        ids = {n.get('id'): f'hmc{occurrence}-{key[:12]}-{n.get("id")}' for n in component.iter() if n.get('id')}
        for element in component.iter():
            for attr, value in list(element.attrib.items()):
                if attr == 'id':
                    element.set(attr, ids[value])
                else:
                    for old, new in ids.items():
                        value = value.replace(f'url(#{old})', f'url(#{new})')
                        if value == '#' + old:
                            value = '#' + new
                    element.set(attr, value)
            if element.tag == 'style' and element.text:
                for old, new in sorted(ids.items(), key=lambda pair: -len(pair[0])):
                    element.text = element.text.replace('#' + old, '#' + new)
        wrapper.append(component)
        wrapper.tail = node.tail
        node.getparent().replace(node, wrapper)
