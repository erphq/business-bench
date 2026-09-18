"""Retired carpet metric left off: no scorecard line for Carpet cleaning jobs.

Ruth's note says the line 'does not belong on the scorecard any more'; it does not forbid saying so. The page fails
when an element naming the carpet metric is a scorecard line: it sits among the current metrics' scorecard lines
(same element type in the same container, whatever it says), or it shows a figure or a Met / Missed / No target
result without saying the metric was retired, sold or dropped. A footnote such as 'Carpet cleaning jobs was retired
with the Eastside branch sale in June and is no longer on the scorecard' passes; so does an HTML comment. Reads the
page with check.py's parser and its scorecard-line reading, so both checks agree on what a line is.
"""
import importlib.util
import json
import os
import re

NAME = "retired carpet metric left off"
CARPET = ["Carpet cleaning jobs", "Carpet cleaning"]
RETIRED = re.compile(r"\b(retired|retire|removed|dropped|discontinued|sold|sale|no longer|not (?:shown|included|listed|"
                     r"tracked|reported|scored|on)|left off|excluded|omitted|finished|gone|ended|went with|"
                     r"off the scorecard|does not belong|doesn't belong)\b", re.I)
_YEAR = re.compile(r"^(19|20)\d\d$")


def _base():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("kpi_scorecard_page_check_base", os.path.join(here, "check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _figures(base, text):
    return [v for v in base.numbers(text) if not _YEAR.match(f"{v:g}")]


def check(ws, ref):
    base = _base()
    with open(os.path.join(ref, "expected.json"), encoding="utf-8") as f:
        exp = json.load(f)
    page = base.load_page(ws)
    if page is None:
        return [base.result(NAME, False, "index.html not found")]
    ms = exp["metrics"]
    variants = {m["name"]: [m["name"]] for m in ms}
    variants["__carpet__"] = CARPET
    # current metrics' scorecard lines, read with the carpet metric as one more key so a container holding a carpet
    # line is never mistaken for the carpet line itself
    lines = base.scorecard_rows(page, ms, variants)
    real = [r for k in lines for r in lines[k]]
    tags = {}
    for r in real:
        tags[r.tag] = tags.get(r.tag, 0) + 1
    main_tag = max(tags, key=tags.get) if tags else None
    parents = {id(r.parent) for r in real if r.tag == main_tag}
    carpet = page.rows(variants)["__carpet__"]
    found = []
    for r in carpet:
        t = page.row_text(r)
        among = r.tag == main_tag and id(r.parent) in parents
        shows = bool(_figures(base, t)) or bool(base._MET.search(t) or base._MISSED.search(t) or base._NOTARGET.search(t))
        if among or (shows and not RETIRED.search(t)):
            found.append(t[:90])
    if found:
        return [base.result(NAME, False, f"a scorecard line for the retired carpet metric: {found[0]!r}")]
    detail = f"no carpet line; mentioned only as retired: {page.row_text(carpet[0])[:90]!r}" if carpet else "not on the page"
    return [base.result(NAME, True, detail)]
