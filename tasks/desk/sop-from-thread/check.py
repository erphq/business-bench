"""The written procedure puts the steps in the order the thread implies, and does not keep the retired blue binder.

A step is a numbered line or step heading (bulleted lines too when there are fewer than four numbered ones) together
with the plain lines under it. A step's position is the first step whose opening words (the first 90 characters after
the number, bullet and bold marks) name it; if no step opens with it, the first step that mentions it anywhere. The order rules come straight from the thread: inspect the item and get
approval before processing the refund, process the refund before emailing the receipt, email the receipt before
logging. A step that shares a line with a later one counts as in order. The blue binder may only appear in a sentence
that says it is no longer used.
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
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    kept = [s for s in sentences if re.search(r"\bbinder\b", s, re.I) and not NEG.search(s)]
    out.append({"name": "blue binder not kept", "passed": not kept,
                "detail": f"binder still used: {kept[0][:120]!r}" if kept else "binder not used"})
    return out
