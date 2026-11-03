#!/usr/bin/env python3
"""Render a visually selected PDF figure region into a high resolution PNG."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--page', type=int, required=True, help='1-based PDF page')
    parser.add_argument('--bbox', type=float, nargs=4, required=True, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=240)
    args = parser.parse_args()
    try:
        import fitz
    except ImportError:
        parser.error('PyMuPDF is required for cropping; use available PDF rendering tools if unavailable')
    if not 72 <= args.dpi <= 600:
        parser.error('dpi must be between 72 and 600')
    if args.output.suffix.lower() != '.png':
        parser.error('output must use .png')
    with fitz.open(args.pdf) as document:
        if not 1 <= args.page <= len(document):
            parser.error('page is outside PDF page range')
        page = document[args.page - 1]
        region = fitz.Rect(args.bbox)
        if region.is_empty or region.is_infinite or not page.rect.contains(region):
            parser.error('bbox must be a non-empty rectangle within the page')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        pix = page.get_pixmap(matrix=fitz.Matrix(args.dpi / 72, args.dpi / 72), clip=region, alpha=False)
        pix.save(args.output)
    print(json.dumps({'output': str(args.output.resolve()), 'page': args.page,
                      'bbox': args.bbox, 'dpi': args.dpi, 'width': pix.width,
                      'height': pix.height}, ensure_ascii=False))


if __name__ == '__main__':
    main()
