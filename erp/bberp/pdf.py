"""A minimal, dependency-free PDF writer for vendor documents (packing slips, invoices, statements).

Output is byte-identical for the same input: no timestamps, no IDs. Text is Latin-1 in Helvetica / Helvetica-Bold,
placed on a Letter page in points, so `pdftotext -layout` and pdfplumber read tables back in columns.
"""
from __future__ import annotations

PAGE_W, PAGE_H = 612, 792


def _esc(s: str) -> str:
    s = s.encode('latin-1', 'replace').decode('latin-1')
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


class Doc:
    """Pages of positioned text. `text(x, y, s, size=10, bold=False)` with y measured from the top."""

    def __init__(self):
        self.pages: list[list[str]] = [[]]

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False) -> None:
        font = 'F2' if bold else 'F1'
        self.pages[-1].append(f'BT /{font} {size:g} Tf {x:.2f} {PAGE_H - y:.2f} Td ({_esc(str(s))}) Tj ET')

    def rule(self, x1: float, y: float, x2: float) -> None:
        self.pages[-1].append(f'0.5 w {x1:.2f} {PAGE_H - y:.2f} m {x2:.2f} {PAGE_H - y:.2f} l S')

    def new_page(self) -> None:
        self.pages.append([])

    def bytes(self) -> bytes:
        objs: list[bytes] = []

        def add(b: str | bytes) -> int:
            objs.append(b.encode('latin-1') if isinstance(b, str) else b)
            return len(objs)
        catalog = add('')  # placeholder, filled below
        pages = add('')
        f1 = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
        f2 = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
        kids = []
        for ops in self.pages:
            stream = '\n'.join(ops).encode('latin-1')
            content = add(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
            kids.append(add(f'<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] '
                            f'/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {content} 0 R >>'))
        objs[catalog - 1] = f'<< /Type /Catalog /Pages {pages} 0 R >>'.encode()
        objs[pages - 1] = f'<< /Type /Pages /Kids [{" ".join(f"{k} 0 R" for k in kids)}] /Count {len(kids)} >>'.encode()
        out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = []
        for i, o in enumerate(objs, 1):
            offsets.append(len(out))
            out += f'{i} 0 obj\n'.encode() + o + b'\nendobj\n'
        xref = len(out)
        out += f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode()
        for off in offsets:
            out += f'{off:010d} 00000 n \n'.encode()
        out += f'trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        return bytes(out)


def business_document(title: str, party_lines: list[str], meta: list[tuple[str, str]], columns: list[tuple[str, float]],
                      rows: list[list[str]], totals: list[tuple[str, str]] = (), notes: list[str] = (),
                      heading: str = '', totals_at: tuple[float, float] = (400, 490)) -> bytes:
    """A letterhead, a key/value block, a table and totals: the shape of an invoice or a packing slip.
    `columns` are (header, x position); numeric columns are right-aligned by the caller padding the text."""
    d = Doc()
    y = 54
    if heading:
        d.text(54, y, heading, 14, bold=True)
        y += 16
    for ln in party_lines:
        d.text(54, y, ln, 9)
        y += 11
    d.text(400, 54, title, 16, bold=True)
    my = 74
    for k, v in meta:
        d.text(400, my, f'{k}:', 9, bold=True)
        d.text(480, my, v, 9)
        my += 12
    y = max(y, my) + 18
    for h, x in columns:
        d.text(x, y, h, 9, bold=True)
    d.rule(54, y + 4, 558)
    y += 18
    for r in rows:
        if y > 700:
            d.new_page()
            y = 72
        for (h, x), cell in zip(columns, r):
            d.text(x, y, cell, 9)
        y += 13
    d.rule(54, y - 6, 558)
    y += 10
    for k, v in totals:
        d.text(totals_at[0], y, k, 9, bold=True)
        d.text(totals_at[1], y, v, 9)
        y += 13
    y += 10
    for n in notes:
        d.text(54, y, n, 9)
        y += 12
    return d.bytes()
