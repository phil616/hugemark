"""QPDF-backed merge; marker annotations recover exact cross-chunk targets."""
import json
import sys
from pathlib import Path
from urllib.parse import unquote
import pikepdf


def assemble(manifest_path, output):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    merged = pikepdf.Pdf.new()
    offsets = {}
    for chunk in manifest['chunks']:
        offsets[chunk['id']] = len(merged.pages)
        with pikepdf.Pdf.open(manifest_path.parent / (chunk['id'] + '.pdf')) as src:
            merged.add_pages_from(src)
    targets = {}
    for i, page in enumerate(merged.pages):
        kept = pikepdf.Array()
        for annot in page.obj.get('/Annots', []):
            uri = str(annot.get('/A', {}).get('/URI', ''))
            if uri.startswith('https://hugemark.invalid/dest/'):
                name = unquote(uri.split('/dest/', 1)[1])
                targets.setdefault(name, (i, float(annot.Rect[3])))
            else:
                kept.append(annot)
        page.obj.Annots = kept
    unresolved = set()
    for page in merged.pages:
        for annot in page.obj.get('/Annots', []):
            uri = str(annot.get('/A', {}).get('/URI', ''))
            if uri.startswith('https://hugemark.invalid/link/'):
                name = unquote(uri.split('/link/', 1)[1])
                if name in targets:
                    i, top = targets[name]
                    annot.Dest = pikepdf.Array([merged.pages[i].obj, pikepdf.Name('/XYZ'), None, top, None])
                    del annot['/A']
                else:
                    unresolved.add(name)
                    del annot['/A']
    with merged.open_outline() as outline:
        stack = [(0, outline.root)]
        for heading in manifest['headings']:
            target = targets.get(heading['id'])
            if target is None:
                continue
            while len(stack) > 1 and stack[-1][0] >= heading['level']:
                stack.pop()
            item = pikepdf.OutlineItem(heading['title'], target[0], 'XYZ', top=target[1])
            stack[-1][1].append(item)
            stack.append((heading['level'], item.children))
    merged.docinfo['/Title'] = manifest['title']
    merged.docinfo['/Creator'] = 'hugemark'
    merged.docinfo['/Producer'] = 'hugemark / Chromium / QPDF'
    output = Path(output)
    temporary = output.with_suffix(output.suffix + '.tmp')
    merged.save(temporary)
    with pikepdf.Pdf.open(temporary) as check:
        assert len(check.pages) == len(merged.pages) > 0
    temporary.replace(output)
    report = {'pages': len(merged.pages), 'targets': len(targets), 'unresolved_links': sorted(unresolved), 'chunk_page_offsets': offsets}
    (manifest_path.parent / 'assembly.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    assemble(*sys.argv[1:])
