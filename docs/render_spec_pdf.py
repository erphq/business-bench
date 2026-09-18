#!/usr/bin/env python
"""Render SPEC.md into docs/business-harness-bench-spec.pdf with reportlab.

Usage:
    .venv/bin/python docs/render_spec_pdf.py [SPEC.md] [output.pdf]

Faithful markdown rendering: headings, paragraphs, bullet and numbered lists,
inline **bold** / `code`, and pipe tables (header shading, wrapped cells, thin
rules, always fitted to the frame width). A title page is prepended and the
source's H1 line is treated as consumed by it (set REPEAT_H1 = True to also
print it at the top of the body).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "SPEC.md"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "business-harness-bench-spec.pdf"

TITLE = "Business Harness Bench"
SUBTITLE = "Research Premise and Benchmark Specification"
DATE = "Release snapshot | 17 September 2026"
REPEAT_H1 = False

PAGE = A4
MARGIN_L = MARGIN_R = 22 * mm
MARGIN_T = 24 * mm
MARGIN_B = 24 * mm
FRAME_W = PAGE[0] - MARGIN_L - MARGIN_R
FRAME_H = PAGE[1] - MARGIN_T - MARGIN_B

INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#6B6B6B")
RULE = colors.HexColor("#C4C4C4")
RULE_DARK = colors.HexColor("#8A8A8A")
HEAD_BG = colors.HexColor("#EDEDED")

BODY_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"
MONO_FONT = "Courier"

BODY_SIZE = 10
CELL_SIZE = 9
CELL_PAD_X = 5
CELL_PAD_Y = 4
NARROW_COL_FRACTION = 0.22   # columns narrower than this share of the frame never wrap
KEEP_TABLE_FRACTION = 0.45   # tables shorter than this share of the frame are not split across pages

# --------------------------------------------------------------------------- styles

def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(
        fontName=BODY_FONT,
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * 1.45,
        textColor=INK,
        alignment=TA_LEFT,
        allowWidows=0,
        allowOrphans=0,
        splitLongWords=1,
    )
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {
    "body": _style("body", spaceAfter=7),
    "h1": _style("h1", fontName=BOLD_FONT, fontSize=18, leading=22, spaceBefore=6, spaceAfter=10, keepWithNext=1),
    "h2": _style("h2", fontName=BOLD_FONT, fontSize=14, leading=18, spaceBefore=18, spaceAfter=6, keepWithNext=1),
    "h3": _style("h3", fontName=BOLD_FONT, fontSize=11.5, leading=15, spaceBefore=13, spaceAfter=4, keepWithNext=1),
    "h4": _style("h4", fontName=BOLD_FONT, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=3, keepWithNext=1),
    "bullet": _style("bullet", leftIndent=14, bulletIndent=3, spaceAfter=4, bulletFontName=BODY_FONT, bulletFontSize=BODY_SIZE),
    "num": _style("num", leftIndent=18, bulletIndent=3, spaceAfter=4, bulletFontName=BODY_FONT, bulletFontSize=BODY_SIZE),
    "cell": _style("cell", fontSize=CELL_SIZE, leading=CELL_SIZE * 1.3),
    "cellhead": _style("cellhead", fontName=BOLD_FONT, fontSize=CELL_SIZE, leading=CELL_SIZE * 1.3),
    "code": _style("code", fontName=MONO_FONT, fontSize=8.5, leading=11, leftIndent=6, spaceAfter=8),
    "title": _style("title", fontName=BOLD_FONT, fontSize=30, leading=36, spaceAfter=10),
    "subtitle": _style("subtitle", fontSize=15, leading=20, textColor=INK, spaceAfter=4),
    "date": _style("date", fontSize=11, leading=15, textColor=MUTED),
}

# --------------------------------------------------------------------------- inline markdown

CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITAL_RE = re.compile(r"(?<![\w*])\*(?!\*)([^*\n]+?)\*(?![\w*])")


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_plain(s: str) -> str:
    s = esc(s)
    s = BOLD_RE.sub(r"<b>\1</b>", s)
    s = ITAL_RE.sub(r"<i>\1</i>", s)
    return s


def inline(md: str, size: float) -> str:
    """Convert inline markdown to reportlab Paragraph markup."""
    code_size = round(size * 0.92, 1)
    out, pos = [], 0
    for m in CODE_RE.finditer(md):
        out.append(_fmt_plain(md[pos:m.start()]))
        out.append(f'<font face="{MONO_FONT}" size="{code_size}">{esc(m.group(1))}</font>')
        pos = m.end()
    out.append(_fmt_plain(md[pos:]))
    return "".join(out)


def _segments(md: str):
    """Yield (text, is_code) segments with bold markers stripped."""
    pos = 0
    for m in CODE_RE.finditer(md):
        if m.start() > pos:
            yield md[pos:m.start()].replace("**", ""), False
        yield m.group(1), True
        pos = m.end()
    if pos < len(md):
        yield md[pos:].replace("**", ""), False


def measure(md: str, font: str, size: float) -> tuple[float, float]:
    """Return (natural width, widest single word) of an inline-markdown cell."""
    natural = 0.0
    widest = 0.0
    for text, is_code in _segments(md):
        f = MONO_FONT if is_code else font
        s = round(size * 0.92, 1) if is_code else size
        natural += stringWidth(text, f, s)
        for word in text.split():
            widest = max(widest, stringWidth(word, f, s))
    return natural, widest

# --------------------------------------------------------------------------- block parsing

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
NUM_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
FENCE_RE = re.compile(r"^```")


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, buf, in_code, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def parse(md_text: str) -> list[tuple]:
    lines = md_text.splitlines()
    blocks: list[tuple] = []
    para: list[str] = []

    def flush():
        if para:
            blocks.append(("p", " ".join(para)))
            para.clear()

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line:
            flush()
            i += 1
            continue
        if FENCE_RE.match(line):
            flush()
            i += 1
            code: list[str] = []
            while i < len(lines) and not FENCE_RE.match(lines[i].strip()):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence
            blocks.append(("code", "\n".join(code)))
            continue
        m = HEADING_RE.match(line)
        if m:
            flush()
            blocks.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and SEP_RE.match(lines[i + 1].strip()):
            flush()
            header = split_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            blocks.append(("table", header, rows))
            continue
        m = BULLET_RE.match(line)
        if m:
            flush()
            text = m.group(1)
            i += 1
            while i < len(lines) and lines[i].startswith(("  ", "\t")) and lines[i].strip() and not BULLET_RE.match(lines[i].strip()):
                text += " " + lines[i].strip()
                i += 1
            blocks.append(("bullet", text))
            continue
        m = NUM_RE.match(line)
        if m:
            flush()
            text = m.group(2)
            i += 1
            while i < len(lines) and lines[i].startswith(("  ", "\t")) and lines[i].strip() and not NUM_RE.match(lines[i].strip()):
                text += " " + lines[i].strip()
                i += 1
            blocks.append(("num", m.group(1), text))
            continue
        para.append(line)
        i += 1
    flush()
    return blocks

# --------------------------------------------------------------------------- tables


def allocate(natural: list[float], minimum: list[float], avail: float) -> list[float]:
    """Proportional allocation by natural width with a per-column floor."""
    n = len(natural)
    fixed: dict[int, float] = {}
    for _ in range(n + 1):
        free = [i for i in range(n) if i not in fixed]
        if not free:
            break
        rem = avail - sum(fixed.values())
        tot = sum(natural[i] for i in free) or 1.0
        widths = dict(fixed)
        changed = False
        for i in free:
            w = rem * natural[i] / tot
            if w < minimum[i]:
                fixed[i] = minimum[i]
                changed = True
            else:
                widths[i] = w
        if not changed:
            return [widths[i] for i in range(n)]
    total = sum(minimum) or 1.0
    return [m * avail / total for m in minimum]


def build_table(header: list[str], rows: list[list[str]]) -> Table:
    ncols = len(header)
    rows = [(r + [""] * ncols)[:ncols] for r in rows]
    natural = [0.0] * ncols
    minimum = [0.0] * ncols
    for ri, row in enumerate([header] + rows):
        font = BOLD_FONT if ri == 0 else BODY_FONT
        for ci, cell in enumerate(row):
            nat, widest = measure(cell, font, CELL_SIZE)
            natural[ci] = max(natural[ci], nat)
            minimum[ci] = max(minimum[ci], widest)
    pad = 2 * CELL_PAD_X + 1
    natural = [w + pad for w in natural]
    # A single very long token is split by the Paragraph anyway; cap the floor.
    minimum = [min(w + pad, FRAME_W * 0.45) for w in minimum]
    # Narrow label columns ("Part", "Cell", "Week", "Adapter") never wrap:
    # their floor is their full natural width; only wide prose columns squeeze.
    minimum = [nat if nat <= FRAME_W * NARROW_COL_FRACTION else mn for nat, mn in zip(natural, minimum)]
    if sum(natural) <= FRAME_W:
        widths = natural
    else:
        widths = allocate(natural, minimum, FRAME_W)
    assert sum(widths) <= FRAME_W + 0.01, (sum(widths), FRAME_W)

    data = [[Paragraph(inline(c, CELL_SIZE), ST["cellhead"]) for c in header]]
    for row in rows:
        data.append([Paragraph(inline(c, CELL_SIZE), ST["cell"]) for c in row])

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("GRID", (0, 0), (-1, -1), 0.3, RULE),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE_DARK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE_DARK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE_DARK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
                ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
                ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_Y),
                ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_Y),
            ]
        )
    )
    return t

# --------------------------------------------------------------------------- page furniture


class NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so the footer can say 'Page N of M'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        page = self._pageNumber
        if page == 1:  # title page stays clean
            return
        self.saveState()
        y = MARGIN_B - 10 * mm
        self.setStrokeColor(RULE)
        self.setLineWidth(0.4)
        self.line(MARGIN_L, y + 12, PAGE[0] - MARGIN_R, y + 12)
        self.setFont(BODY_FONT, 8.5)
        self.setFillColor(MUTED)
        self.drawString(MARGIN_L, y, f"{TITLE} - Specification")
        self.drawRightString(PAGE[0] - MARGIN_R, y, f"Page {page} of {total}")
        self.restoreState()


def title_page() -> list:
    return [
        Spacer(1, PAGE[1] * 0.30),
        Paragraph(TITLE, ST["title"]),
        HRFlowable(width="38%", thickness=0.8, color=INK, spaceBefore=2, spaceAfter=14, hAlign="LEFT"),
        Paragraph(SUBTITLE, ST["subtitle"]),
        Paragraph(DATE, ST["date"]),
        PageBreak(),
    ]

# --------------------------------------------------------------------------- build


def build_story(blocks: list[tuple]) -> list:
    story: list = title_page()
    seen_h1 = False
    for b in blocks:
        kind = b[0]
        if kind == "h":
            level, text = b[1], b[2]
            if level == 1 and not seen_h1:
                seen_h1 = True
                if not REPEAT_H1:
                    continue
            style = ST["h%d" % min(level, 4)]
            story.append(Paragraph(inline(text, style.fontSize), style))
        elif kind == "p":
            story.append(Paragraph(inline(b[1], BODY_SIZE), ST["body"]))
        elif kind == "bullet":
            story.append(Paragraph(inline(b[1], BODY_SIZE), ST["bullet"], bulletText="•"))
        elif kind == "num":
            story.append(Paragraph(inline(b[2], BODY_SIZE), ST["num"], bulletText=f"{b[1]}."))
        elif kind == "code":
            story.append(Preformatted(b[1], ST["code"]))
        elif kind == "table":
            table = build_table(b[1], b[2])
            _, height = table.wrap(FRAME_W, FRAME_H)
            group = [Spacer(1, 3), table]
            if height <= FRAME_H * KEEP_TABLE_FRACTION and story and isinstance(story[-1], Paragraph) and getattr(story[-1].style, 'keepWithNext', False):
                group.insert(0, story.pop())
            story.append(KeepTogether(group) if height <= FRAME_H * KEEP_TABLE_FRACTION else group[0])
            if height > FRAME_H * KEEP_TABLE_FRACTION:
                story.append(table)
            story.append(Spacer(1, 10))
    return story


def prefer_canonical_winansi_slots() -> None:
    """Make U+2022 (bullet) encode to WinAnsi 0x95 instead of 0x7F.

    reportlab's WinAnsi table lists the 'bullet' glyph at 0x7F/0x81/0x8D/0x8E/
    0x8F/0x90/0x9D/0x9E as well as the canonical 0x95, and its charmap picks
    0x7F. Viewers draw the same glyph either way, but text extractors (pypdf,
    pdftotext, search, copy/paste) decode 0x7F as DEL, so "ERP•AI" would not be
    findable in the PDF. The codec keeps its encoding map as a default argument
    of the encode closure; mutate that dict in place.
    """
    import codecs

    from reportlab.pdfbase import rl_codecs

    rl_codecs.RL_Codecs.register()
    encode = codecs.lookup("winansi").encode
    func = getattr(encode, "__func__", encode)
    for default in getattr(func, "__defaults__", None) or ():
        if isinstance(default, dict) and default.get(0x41) == 0x41:  # the encoding map
            default[0x2022] = 0x95
            break
    assert "•".encode("winansi") == b"\x95", "bullet still not on 0x95"


def check_glyphs(md_text: str) -> None:
    """Built-in Type 1 fonts are WinAnsi; refuse to silently drop glyphs."""
    prefer_canonical_winansi_slots()
    bad = sorted({ch for ch in md_text if ord(ch) > 127 and not _encodable(ch)})
    if bad:
        raise SystemExit("Characters outside WinAnsi (would render as boxes): " + ", ".join(f"U+{ord(c):04X} {c!r}" for c in bad))


def _encodable(ch: str) -> bool:
    try:
        ch.encode("winansi")
        return True
    except UnicodeEncodeError:
        return False


def main() -> None:
    md_text = SRC.read_text(encoding="utf-8")
    check_glyphs(md_text)
    blocks = parse(md_text)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=PAGE,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title=f"{TITLE} — {SUBTITLE}",
        author="",
        subject=f"{TITLE} specification, {DATE}",
        creator="render_spec_pdf.py (reportlab)",
    )
    doc.build(build_story(blocks), canvasmaker=NumberedCanvas)
    tables = sum(1 for b in blocks if b[0] == "table")
    print(f"wrote {OUT}  ({tables} tables, {len(blocks)} blocks)")

    try:
        from pypdf import PdfReader
    except ImportError:
        return
    reader = PdfReader(str(OUT))
    print(f"pages: {len(reader.pages)}")


if __name__ == "__main__":
    main()
