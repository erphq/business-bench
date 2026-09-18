"""The written procedure puts the steps in the order the thread implies, and does not keep the retired blue binder.

A step is a numbered line or step heading (bulleted lines too when there are fewer than four numbered ones) together
with the plain lines under it. A step's position is the first step whose opening words (the first 90 characters after
the number, bullet and bold marks) name it; if no step opens with it, the first step that mentions it anywhere. The order rules come straight from the thread: inspect the item and get
approval before processing the refund, process the refund before emailing the receipt, email the receipt before
logging. A step that shares a line with a later one counts as in order.

The blue binder may only appear where the procedure retires it. A binder mention is retired when its sentence says so
(the negation words in NEG), and also when its context does, because a printed procedure often retires the binder
outside that one sentence: a table cell under a column headed as the old way ("Old way", "Before", "Was") or in a row
whose other cell names the Refunds Log as the replacement; a question or label ("Binder?", "Blue binder:") whose
answer, the next sentence, retires it or names the Refunds Log; a sentence followed by one that says it changed or
stopped; a mention under a heading about what changed or was retired. A binder kept alongside the log ("file the slip
in the blue binder and log it in the Refunds Log") is still kept.
"""
import glob
import os
import re

STEP = re.compile(r"^\s*(#{1,6}\s*)?(step\s*\d+\s*[:.)-]?|\d+\s*[.)]|[-*•]|\(\d+\))\s*", re.I)
KEYS = {
    "inspect the item": re.compile(r"(inspect|look (the item|it) over|check (the )?(item|condition|tags)|condition|return tag|tag (it|the item))", re.I),
    "get approval": re.compile(r"(approv|sign[- ]?off|permission|get (the owner|an? ok|the ok)|\bok\b|okay)", re.I),
    "process the refund": re.compile(r"(process(ing)? (the |a )?refund|issue (the |a )?refund|run (the |a )?refund|refund (it |the (sale|purchase|payment|amount) )?(back )?to the (original|customer's)|refund (the customer|it)\b)", re.I),
    "email the receipt": re.compile(r"(e-?mail[^.\n]{0,60}receipt|receipt[^.\n]{0,40}e-?mail)", re.I),
    "log the refund": re.compile(r"(refunds? log|log (it|the refund|every refund|each refund)|log sheet|\blog\b[^.\n]{0,30}(sheet|shared drive))", re.I),
}
ORDER = [("inspect the item", "process the refund"), ("get approval", "process the refund"),
         ("process the refund", "email the receipt"), ("email the receipt", "log the refund")]
NEG = re.compile(r"(no longer|not|don't|do not|never|retired|replac|instead of|stopp|done with|gone|old|shred|used to|was)", re.I)
# context rules (see the module docstring): wording that retires the binder from outside its own sentence
RETIRE = re.compile(r"(no longer|retire|replac|instead|stopp|done with|shred|used to|\bchang(e|ed|es|ing)\b|in place of|not used|"
                    r"don't use|do not use|never use|anymore|any more)", re.I)
OLD_HEADING = re.compile(r"\bold\b", re.I)
REPLACEMENT = re.compile(r"(refunds? log|log sheet|shared drive|spreadsheet)", re.I)
OLD_HEADER = re.compile(r"(\bold\b|\bbefore\b|\bwas\b|previous|former|retire|replac|no longer|used to|\bthen\b|\bpast\b|"
                        r"originally|\bstop)", re.I)
NEW_HEADER = re.compile(r"(\bnew\b|\bnow\b|\bafter\b|current|today|going forward|\bfrom\b)", re.I)
BINDER = re.compile(r"\bbinder\b", re.I)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _binder_kept(text):
    """Sentences that still use the blue binder, after the sentence and context rules."""
    lines = text.splitlines()
    # markdown tables: the header row of each contiguous block of |-rows (the row above a |---| separator)
    header_of = {}
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            hdr = _cells(lines[i]) if j - i >= 2 and re.fullmatch(r"[\s|:\-]+", lines[i + 1]) else None
            for k in range(i, j):
                header_of[k] = hdr
            i = j
        else:
            i += 1
    heading = {}
    current = ""
    for n, ln in enumerate(lines):
        if re.match(r"^\s*#{1,6}\s", ln):
            current = ln
        heading[n] = current
    units = []  # (line number, sentence) in reading order
    for n, ln in enumerate(lines):
        for sent in re.split(r"(?<=[.!?])\s+", ln):
            if sent.strip():
                units.append((n, sent))
    kept = []
    for u, (n, sent) in enumerate(units):
        if not BINDER.search(sent) or NEG.search(sent):
            continue  # no mention, or its own sentence retires it (the original rule)
        transition = re.search(r"\b(?:moved|switched|changed|transferred)\s+from\b[^.;]{0,60}\bbinder\b[^.;]{0,40}\bto\b[^.;]{0,60}(?:refunds? log|log sheet|shared drive|spreadsheet)", sent, re.I)
        if (transition and len(BINDER.findall(sent)) == 1
                and not re.search(r"\b(?:but|still|continue|keep using|alongside)\b", sent[transition.end():], re.I)):
            continue
        line = lines[n]
        nxt = units[u + 1][1] if u + 1 < len(units) else ""
        answer_no = bool(re.match(r"^\W*no\b", nxt, re.I))
        # a mention under a heading about what changed or the old way
        under_retiring_heading = bool(RETIRE.search(heading[n]) or OLD_HEADING.search(heading[n]))
        retired = under_retiring_heading
        if line.strip().startswith("|") and line.count("|") >= 2:
            # table row: every binder cell says it is retired, sits under an old-way column, or - unless its own column
            # is headed as the new way - faces a cell naming the Refunds Log (a before/after row) or sits in a table
            # under a heading about what changed
            cells, hdr = _cells(line), header_of.get(n)
            if hdr is not None and cells == hdr:
                hdr = None
            verdicts = []
            for c, cell in enumerate(cells):
                if not BINDER.search(cell):
                    continue
                col_head = hdr[c] if hdr is not None and c < len(hdr) else ""
                others_name_log = any(REPLACEMENT.search(x) for c2, x in enumerate(cells) if c2 != c)
                verdicts.append(bool(NEG.search(cell) or OLD_HEADER.search(col_head) or
                                     (not NEW_HEADER.search(col_head) and
                                      (under_retiring_heading or (others_name_log and not REPLACEMENT.search(cell))))))
            retired = bool(verdicts) and all(verdicts)
        elif sent.rstrip().endswith("?"):
            # a question ("Binder?") answered by the next sentence
            retired = retired or bool(RETIRE.search(nxt) or NEG.search(nxt) or REPLACEMENT.search(nxt) or answer_no)
        else:
            # a label ("Blue binder:") or statement followed by a sentence saying it changed or stopped
            retired = retired or bool(RETIRE.search(nxt) or (sent.rstrip().rstrip("*_").endswith(":") and answer_no))
        if not retired:
            kept.append(sent)
    return kept


def check(ws, ref):
    hits = sorted(glob.glob(os.path.join(ws, "procedure.md"))) or sorted(
        h for h in glob.glob(os.path.join(ws, "**", "procedure.md"), recursive=True) if "/.proto" not in h and "/.codex" not in h)
    if not hits:
        return [{"name": "steps in the right order", "passed": False, "detail": "procedure.md not found"},
                {"name": "blue binder not kept", "passed": False, "detail": "procedure.md not found"}]
    text = open(hits[0], encoding="utf-8", errors="replace").read()
    all_lines = text.splitlines()
    is_step = lambda ln: bool(STEP.match(ln)) and len(STEP.sub("", ln, count=1).strip()) > 3
    is_numbered = lambda ln: bool(re.match(r"^\s*(#{1,6}\s*)?(step\s*\d+|\d+\s*[.)]|\(\d+\))", ln, re.I)) and is_step(ln)
    starts = is_numbered if sum(1 for ln in all_lines if is_numbered(ln)) >= 4 else is_step  # numbered procedure: bullets are notes inside steps
    blocks = []  # each step line plus the plain lines under it, up to the next step line or heading
    for ln in all_lines:
        if starts(ln):
            blocks.append([ln])
        elif blocks and ln.strip() and not re.match(r"^\s*#", ln):
            blocks[-1].append(ln)
        elif blocks and re.match(r"^\s*#", ln):
            blocks.append([])  # a non-step heading closes the current step
    blocks = [b for b in blocks if b]
    clean = lambda ln: re.sub(r"[*_`]", "", STEP.sub("", ln, count=1)).strip()
    heads = [" ".join(clean(x) for x in b)[:90] for b in blocks]
    bodies = [" ".join(b) for b in blocks]
    pos, missing = {}, []
    for k, rx in KEYS.items():
        i = next((j for j, h in enumerate(heads) if rx.search(h)), None)
        if i is None:
            i = next((j for j, bd in enumerate(bodies) if rx.search(bd)), None)
        if i is None:
            missing.append(k)
        else:
            pos[k] = i
    wrong = [f"{a} (step {pos[a] + 1}) after {b} (step {pos[b] + 1})" for a, b in ORDER if a in pos and b in pos and pos[a] > pos[b]]
    ok = not missing and not wrong
    detail = ("no step line found for " + ", ".join(missing) + ("; " if wrong else "")) if missing else ""
    detail += "; ".join(wrong)
    out = [{"name": "steps in the right order", "passed": ok, "detail": detail or f"order ok across {len(blocks)} steps"}]
    kept = _binder_kept(text)
    out.append({"name": "blue binder not kept", "passed": not kept,
                "detail": f"binder still used: {kept[0][:120]!r}" if kept else "binder not used"})
    return out
