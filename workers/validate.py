"""Validate each renderer result before promoting it into the resume cache."""
import json
import sys
import pikepdf

with pikepdf.Pdf.open(sys.argv[1], attempt_recovery=False) as pdf:
    if not len(pdf.pages):
        raise ValueError('Renderer produced a PDF with no pages')
    issues = pdf.check_pdf_syntax()
    if issues:
        raise ValueError('Invalid PDF: ' + '; '.join(issues[:10]))
    print(json.dumps({'pages': len(pdf.pages)}))
