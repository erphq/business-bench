"""Conference schedule: every running session once with a time, its Mountain start time, under its day and room, and
the word CONFLICT on exactly the sessions that overlap another in the same room. Markup-agnostic (sections, a list
table, cards or a room grid); expected values from reference/expected.json."""
# ---------------------------------------------------------------- page reading (standard library only)
# Tolerant of markup style: a table row, a list item or a card div all count as the "row" for an entity,
# namely the largest element whose visible text names that entity and no other. Group labels come from the
# row's own text (a status column), the column header of a grid cell, or the nearest heading-like block above.
import glob
import json
import os
import re
from html.parser import HTMLParser

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_SKIP = {"script", "style", "template", "head", "title", "noscript", "svg"}
_BLOCK = {"address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "dialog", "div", "dl", "dt",
          "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup",
          "hr", "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th",
          "thead", "tr", "ul", "legend", "body", "html", "label", "meter", "progress"}
_HEADING = {"h1", "h2", "h3", "h4", "h5", "h6", "caption", "legend", "summary", "dt", "figcaption"}


class _Node:
    __slots__ = ("tag", "attrs", "kids", "parent", "pos", "end")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.kids, self.parent, self.pos, self.end = tag, dict(attrs or []), [], parent, 0, 0


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", None, None)
        self.stack = [self.root]

    def _open_tags(self):
        return [n.tag for n in self.stack]

    def _pop_to(self, tag, stop):
        tags = self._open_tags()
        for i in range(len(tags) - 1, 0, -1):
            if tags[i] in stop:
                return
            if tags[i] == tag:
                del self.stack[i:]
                return

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "li":
            self._pop_to("li", {"ul", "ol", "menu"})
        elif tag in ("dt", "dd"):
            self._pop_to("dt", {"dl"}); self._pop_to("dd", {"dl"})
        elif tag == "tr":
            self._pop_to("tr", {"table", "thead", "tbody", "tfoot"})
        elif tag in ("td", "th"):
            self._pop_to("td", {"tr", "table"}); self._pop_to("th", {"tr", "table"})
        elif tag in ("thead", "tbody", "tfoot"):
            self._pop_to("thead", {"table"}); self._pop_to("tbody", {"table"}); self._pop_to("tfoot", {"table"})
        if tag in _BLOCK and tag not in ("br",) and "p" in self._open_tags():
            self._pop_to("p", {"div", "li", "td", "th", "section", "article", "table", "ul", "ol", "body"})
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].kids.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        self.stack[-1].kids.append(_Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        tag = tag.lower()
        tags = self._open_tags()
        if tag in tags[1:]:
            i = len(tags) - 1 - tags[::-1].index(tag)
            del self.stack[i:]

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


class Page:
    def __init__(self, html_text):
        t = _Tree()
        t.feed(html_text)
        t.close()
        self.root = t.root
        self.nodes = []
        self._text = {}
        self._walk(self.root)

    def _walk(self, n):
        n.pos = len(self.nodes)
        self.nodes.append(n)
        for k in n.kids:
            if not isinstance(k, str) and k.tag not in _SKIP:
                self._walk(k)
        n.end = len(self.nodes)

    def text(self, n):
        key = id(n)
        if key not in self._text:
            parts = []

            def rec(x):
                prev_el = False
                for k in x.kids:
                    if isinstance(k, str):
                        parts.append(k)
                        prev_el = False
                    elif k.tag in _SKIP:
                        continue
                    else:
                        # Inline spans can be separate styled labels beside raw text,
                        # not only beside another element (e.g. heading and count).
                        blk = k.tag in _BLOCK or k.tag == "span" or prev_el
                        if blk: parts.append(" ")
                        rec(k)
                        if k.tag in _BLOCK or k.tag == "span": parts.append(" ")
                        prev_el = True
            rec(n)
            self._text[key] = re.sub(r"\s+", " ", "".join(parts)).strip()
        return self._text[key]

    def index(self, variants):
        """variants: {key: [surface strings]}. Records which keys each element's text names (whole-word,
        case-insensitive, longest surface form first)."""
        pats = sorted({(v.lower().strip(), k) for k, vs in variants.items() for v in vs if v and v.strip()},
                      key=lambda x: -len(x[0]))
        rx = re.compile("|".join("(?<![a-z0-9])" + re.escape(v) + "(?![a-z0-9])" for v, _ in pats)) if pats else None
        lookup = {}
        for v, k in pats:
            lookup.setdefault(v, k)
        self._keys, self._first = {}, {}
        for n in self.nodes:
            txt = self.text(n).lower()
            found = [lookup[m.group(0)] for m in rx.finditer(txt)] if rx else []
            self._keys[id(n)] = frozenset(found)
            self._first[id(n)] = found[0] if found else None
        self._variants = variants

    def keys_in(self, n):
        return self._keys.get(id(n), frozenset())

    def rows(self, variants=None):
        """{key: [row nodes in document order]}: a row is the largest element whose text names that key and no other."""
        if variants is not None:
            self.index(variants)
        out = {k: [] for k in self._variants}
        for n in self.nodes:
            ks = self._keys[id(n)]
            if len(ks) != 1:
                continue
            if n.parent is not None and self._keys.get(id(n.parent)) == ks:
                continue
            out[next(iter(ks))].append(n)
        return out

    def cards(self, variants=None, cue=r"(waiting|wait|depends?|dependent|dependency|dependencies|after|blocked by|needs?|requires?|behind|on hold for)\b[^.;]{0,60}$"):
        """{key: [card node]} for pages whose cards also mention other keys ("waiting on X"). Each key's anchor is
        its tightest mention (the element whose text is most nearly just that name, not introduced by a dependency
        cue); the card is the largest element around the anchor that holds no other key's anchor."""
        if variants is not None:
            self.index(variants)
        pats = {k: re.compile("|".join("(?<![a-z0-9])" + re.escape(v.lower().strip()) + "(?![a-z0-9])"
                                       for v in sorted(vs, key=len, reverse=True) if v and v.strip()))
                for k, vs in self._variants.items()}
        cue_rx = re.compile(cue, re.I)

        def count(n, k):
            return len(pats[k].findall(self.text(n).lower())) if k in self._keys.get(id(n), ()) else 0

        best, seen = {}, {}
        for n in self.nodes:
            for k in self._keys.get(id(n), ()):
                own = count(n, k) - sum(count(c, k) for c in n.kids if not isinstance(c, str) and c.tag not in _SKIP)
                if own <= 0:
                    continue
                txt = self.text(n).lower()
                m = pats[k].search(txt)
                score = len(m.group(0)) / max(len(txt), 1)
                blk = n
                while blk is not None and blk.tag not in _BLOCK:
                    blk = blk.parent
                btxt = self.text(blk).lower() if blk is not None else txt
                inner = btxt.find(txt) if txt else -1
                mm = pats[k].search(btxt, max(inner, 0))
                before = btxt[:mm.start()] if mm else ""
                if cue_rx.search(before[-80:]):
                    score -= 1.0
                seen.setdefault(k, []).append((score, n))
                if k not in best or score > best[k][0] + 1e-9:
                    best[k] = (score, n)
        anchors = {k: v[1] for k, v in best.items()}
        out = {k: [] for k in self._variants}
        for k, a in anchors.items():
            others = [x for kk, x in anchors.items() if kk != k]
            card = a
            while card.parent is not None and card.parent.tag != "#root" and not any(Page.inside(o, card.parent) for o in others):
                card = card.parent
            out[k].append(card)
            # the same card shape again elsewhere (a task shown twice)
            for score, n in seen.get(k, []):
                if n is not a and score > 0 and score >= 0.9 * best[k][0] and not Page.inside(n, card):
                    dup = n
                    others2 = others + [a]
                    while dup.parent is not None and dup.parent.tag != "#root" and not any(Page.inside(o, dup.parent) for o in others2):
                        dup = dup.parent
                    if not any(Page.inside(dup, c) or Page.inside(c, dup) for c in out[k]):
                        out[k].append(dup)
        return out

    def row_text(self, row):
        """The row's text, plus the keyless siblings that follow a bare label (a dt and its dd, a heading or a
        paragraph and the lines under it) up to the next keyed sibling."""
        txt = self.text(row)
        if row.tag not in ("dt", "h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "strong", "b", "em", "a", "label") \
                or row.parent is None:
            return txt
        sibs = [k for k in row.parent.kids if not isinstance(k, str) and k.tag not in _SKIP]
        i = sibs.index(row)
        extra = []
        for k in sibs[i + 1:i + 5]:
            if self._keys.get(id(k)) or k.tag in ("h1", "h2", "h3") and row.tag not in ("h1", "h2"):
                break
            if k.tag == "dt":
                break
            extra.append(self.text(k))
        return " ".join([txt] + extra).strip()

    @staticmethod
    def inside(n, outer):
        return outer.pos <= n.pos < outer.end

    def blocks(self):
        return [n for n in self.nodes if n.tag in _BLOCK]

    def _is_heading(self, n):
        if n.tag in _HEADING or n.attrs.get("role") == "heading":
            return True
        if n.tag == "tr":
            cells = [k for k in n.kids if not isinstance(k, str) and k.tag in ("td", "th")]
            return bool(cells) and all(c.tag == "th" for c in cells)
        return False

    def headings_before(self, row):
        """Heading-like elements that start before the row (nearest first), plus any inside the row."""
        inside = [n for n in self.nodes[row.pos + 1:row.end] if self._is_heading(n)]
        before = [n for n in self.nodes[:row.pos] if self._is_heading(n) and n.end <= row.pos]
        return inside + before[::-1]

    def column_header(self, row):
        """For a row that is (inside) a table cell: the header cell text of its column, honouring colspan/rowspan."""
        cell = row
        while cell is not None and cell.tag not in ("td", "th"):
            cell = cell.parent
        if cell is None:
            # a whole table row holding a single keyed cell: use that cell
            cands = [n for n in self.nodes[row.pos + 1:row.end] if n.tag in ("td", "th") and self._keys.get(id(n))]
            if not cands:
                return ""
            cell = cands[-1]
        table = cell.parent
        while table is not None and table.tag != "table":
            table = table.parent
        if table is None:
            return ""
        trs = [n for n in self.nodes[table.pos + 1:table.end] if n.tag == "tr"]
        # drop rows that belong to a nested table
        trs = [tr for tr in trs if self._owner_table(tr) is table]
        grid, occupied = {}, {}
        for ri, tr in enumerate(trs):
            ci = 0
            for c in [k for k in tr.kids if not isinstance(k, str) and k.tag in ("td", "th")]:
                while occupied.get((ri, ci)):
                    ci += 1
                try:
                    cs = max(1, int(c.attrs.get("colspan") or 1)); rs = max(1, int(c.attrs.get("rowspan") or 1))
                except ValueError:
                    cs, rs = 1, 1
                for dr in range(rs):
                    for dc in range(cs):
                        occupied[(ri + dr, ci + dc)] = c
                grid[id(c)] = (ri, ci)
                ci += cs
        if id(cell) not in grid:
            return ""
        _, col = grid[id(cell)]
        # column headers live in the leading rows made only of header cells, two or more of them
        for tr in trs:
            cells = [k for k in tr.kids if not isinstance(k, str) and k.tag in ("td", "th")]
            if not cells or any(c.tag == "td" for c in cells):
                break
            if len(cells) < 2:
                continue
            ri = trs.index(tr)
            h = occupied.get((ri, col))
            if h is not None and h is not cell:
                return self.text(h)
        return ""

    def row_cells_text(self, row):
        """Text of the first cell of the table row a cell sits in (a grid's time column), else ''."""
        cell = row
        while cell is not None and cell.tag not in ("td", "th"):
            cell = cell.parent
        if cell is None or cell.parent is None or cell.parent.tag != "tr":
            return ""
        first = next((k for k in cell.parent.kids if not isinstance(k, str) and k.tag in ("td", "th")), None)
        return self.text(first) if first is not None and first is not cell else ""

    def _owner_table(self, n):
        p = n.parent
        while p is not None and p.tag != "table":
            p = p.parent
        return p

    def _label_near(self, row, hit):
        """Nearest label above the row: walk up its ancestors and, in each, scan the content before the row's
        branch from nearest to farthest, skipping earlier rows (anything naming a key) and reading headings,
        short header blocks and loose text."""
        def scan(nodes):
            for k in reversed(nodes):
                if isinstance(k, str):
                    t = re.sub(r"\s+", " ", k).strip()
                    if t and len(t) <= 80:
                        g = hit(t)
                        if g:
                            return g
                    continue
                if k.tag in _SKIP or self._keys.get(id(k)):
                    continue
                t = self.text(k)
                if self._is_heading(k) or len(t) <= 80:
                    g = hit(t)
                    if g:
                        return g
                    if self._is_heading(k):
                        continue
                g = scan(k.kids)
                if g:
                    return g
            return None
        child, anc = row, row.parent
        while anc is not None:
            i = next(j for j, k in enumerate(anc.kids) if k is child)
            g = scan(anc.kids[:i])
            if g:
                return g
            child, anc = anc, anc.parent
        return None

    def group_of(self, row, labels, own_text=True, structure_first=False):
        """labels: {label: regex}. The row's own text if it names exactly one label, else its grid column header,
        else the nearest label above it (see _label_near). structure_first consults the page structure before the
        row's own text (for sectioned pages whose rows may mention other labels)."""
        def hit(txt):
            found = {lab for lab, rx in labels.items() if re.search(rx, txt, re.I)}
            return next(iter(found)) if len(found) == 1 else None
        own = hit(self.text(row)) if own_text else None
        if own and not structure_first:
            return own
        g = hit(self.column_header(row)) or self._label_near(row, hit)
        return g or own


def find_page(ws, name="index.html"):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def load_page(ws, name="index.html"):
    p = find_page(ws, name)
    if not p:
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return Page(f.read())


_NUM = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d)|(?<![\d.,])\d+(?:\.\d+)?")


def numbers(text):
    """Every figure in the text as an absolute value ("$1,240.50" -> 1240.5, "(30.00)" -> 30.0, "x2214" -> 2214)."""
    out = []
    for m in _NUM.finditer(text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def has_number(text, want, tol=0.005):
    return any(abs(v - abs(want)) <= tol for v in numbers(text))


def main_container(rows, keys=None):
    """The element holding rows for the most distinct keys (the main table body or list), or None."""
    held = {}
    for k, rs in rows.items():
        if keys is not None and k not in keys:
            continue
        for rw in rs:
            if rw.parent is not None:
                held.setdefault(id(rw.parent), [rw.parent, set()])[1].add(k)
    if not held:
        return None
    return max(held.values(), key=lambda x: (len(x[1]), -x[0].pos))[0]


def result(name, ok, detail):
    return {"name": name, "passed": bool(ok), "detail": detail}


# ---------------------------------------------------------------- event-schedule-page
_ANY_TIME = re.compile(r"(?<![\d:.])\d{1,2}[:.h]\d{2}(?!\d)")


def _start_rx(h, m):
    h12 = h % 12 or 12
    alts = []
    if h >= 13:
        alts.append(rf"(?<![\d:.]){h}[:.h]{m:02d}(?!\d)")
        alts.append(rf"(?<![\d:.])0?{h12}[:.]{m:02d}(?!\d)(?=[^a-z]{{0,14}}p\.?\s?m\b)")
    elif h == 12:
        alts.append(rf"(?<![\d:.])12[:.h]{m:02d}(?!\d)(?![^a-z]{{0,14}}a\.?\s?m\b)")
    else:
        alts.append(rf"(?<![\d:.])0?{h}[:.h]{m:02d}(?!\d)(?![^a-z]{{0,14}}p\.?\s?m\b)")
    return re.compile("|".join(alts), re.I)


def _time_context(page, row):
    own = page.row_text(row)
    if _ANY_TIME.search(own):
        return own
    head = page.row_cells_text(row)
    if _ANY_TIME.search(head):
        return head
    for h in page.headings_before(row):
        if _ANY_TIME.search(page.text(h)):
            return page.text(h)
    return ""


def check(ws, ref):
    name = "page structure"
    with open(os.path.join(ref, "expected.json"), encoding="utf-8") as f:
        exp = json.load(f)
    page = load_page(ws)
    if page is None:
        return [result(name, False, "index.html not found")]
    sess = exp["sessions"]
    variants = {s["title"]: [s["title"]] for s in sess}
    variants[exp["cancelled"]] = [exp["cancelled"]]
    rows = page.rows(variants)
    flag = re.compile(exp["flag_rx"], re.I)
    out = []
    sched = {s["title"]: [rw for rw in rows[s["title"]] if _time_context(page, rw)] for s in sess}
    missing = [s["title"] for s in sess if not sched[s["title"]]]
    duplicated = [s["title"] for s in sess if len(sched[s["title"]]) > 1]
    cx = [rw for rw in rows[exp["cancelled"]]]
    out.append(result("one entry per session", not missing and not duplicated and not cx,
                      f"{len(sess) - len(missing)}/{len(sess)} sessions scheduled with a time; missing={missing[:4]}"
                      + (f"; duplicated={duplicated[:4]}" if duplicated else "")
                      + ("; the cancelled session is on the page" if cx else "")))
    bad_time, bad_place, bad_flag = [], [], []
    for s in sess:
        want = _start_rx(s["start_h"], s["start_m"])
        for rw in sched[s["title"]]:
            if not want.search(_time_context(page, rw)):
                bad_time.append(f"{s['title']} (want {s['start_h']:02d}:{s['start_m']:02d} Mountain)")
            day = page.group_of(rw, exp["day_rx"])
            room = page.group_of(rw, exp["room_rx"])
            if day != s["day"] or room != s["room"]:
                bad_place.append(f"{s['title']}: {day}/{room} (want {s['day']}/{s['room']})")
            if bool(flag.search(page.row_text(rw))) != s["conflict"]:
                bad_flag.append(f"{s['title']}: {'marked' if not s['conflict'] else 'not marked'}")
    out.append(result("local start times", not bad_time and not missing,
                      "every session starts at its Mountain time" if not bad_time else f"{len(bad_time)} wrong: {bad_time[:4]}"))
    out.append(result("day and room", not bad_place and not missing,
                      "every session under its day and room" if not bad_place else f"{len(bad_place)} misplaced: {bad_place[:4]}"))
    n_conf = sum(1 for s in sess if s["conflict"])
    out.append(result("CONFLICT marks", not bad_flag and not missing,
                      f"{n_conf} overlapping sessions marked, none else" if not bad_flag else f"{len(bad_flag)} wrong: {bad_flag[:5]}"))
    return out
