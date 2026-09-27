#!/usr/bin/env python3
"""The measurement graph: what each desk task measures, and what the ledger says about it.

    measure_graph.py [--ledger results/latest/attempts.jsonl] [--out DIR] [--no-gen]

Nodes: task, trap (one per task.yaml trap sentence), check, category, check type.
Edges: task-has-trap, task-has-check, trap-cites-check (from the "(checks: ...)" citations, resolved by
bench/trap_links.py), task-in-category, check-of-type. Where a generator declares switchable traps
(`gen.py --list-traps`), each trap node carries its key and whether it is switchable or fixed.

Joined with the attempt ledger, every check gets attempts and failures per system, and every trap gets a
bite rate: the share of attempts in which a check it cites failed. A check cited by one trap only gives
that trap an exclusive bite; a check cited by several cannot say which trap caused the failure, which is
what the trap switches are for.

Writes graph.json (nodes and edges) and report.md to --out (default results/measurement/). Offline
tooling; linear in tasks x (traps x checks) plus attempts x checks. Ledger verdicts whose check name no
longer exists in the current task files (renamed since the frozen scorer) are counted and reported, not
guessed at.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import subprocess
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trap_links import trap_links  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# check types that verify the deliverable's shape rather than a business fact; they need no trap
STRUCTURAL = {"file_exists", "csv_columns", "xlsx_has_formulas", "xlsx_no_errors", "csv_row_count"}


def load_tasks(task_root: str) -> dict[str, dict]:
    out = {}
    for p in sorted(glob.glob(os.path.join(task_root, "*", "task.yaml"))):
        with open(p) as f:
            t = yaml.safe_load(f) or {}
        t["_dir"] = os.path.dirname(p)
        out[t["id"]] = t
    return out


def trap_declaration(task_dir: str) -> dict | None:
    gen = os.path.join(task_dir, "gen.py")
    if not os.path.isfile(gen):
        return None
    with open(gen) as f:
        if "add_trap_args" not in f.read():
            return None
    r = subprocess.run([sys.executable, gen, "--list-traps"], capture_output=True, text=True, cwd=task_dir)
    return json.loads(r.stdout) if r.returncode == 0 else None


def build_graph(tasks: dict[str, dict], use_gen: bool = True) -> dict:
    nodes, edges = [], []
    for tid, t in tasks.items():
        checks = t.get("checks") or []
        nodes.append({"id": f"task:{tid}", "kind": "task", "task": tid, "category": t.get("category"),
                      "n_checks": sum(1 for c in checks if c.get("required", True))})
        edges.append({"src": f"task:{tid}", "dst": f"category:{t.get('category')}", "rel": "in_category"})
        for c in checks:
            cid = f"check:{tid}:{c.get('name', c['type'])}"
            nodes.append({"id": cid, "kind": "check", "task": tid, "name": c.get("name", c["type"]),
                          "type": c["type"], "required": bool(c.get("required", True))})
            edges.append({"src": f"task:{tid}", "dst": cid, "rel": "has_check"})
            edges.append({"src": cid, "dst": f"check_type:{c['type']}", "rel": "of_type"})
        decl = trap_declaration(t["_dir"]) if use_gen else None
        keys = (decl or {}).get("sentence_keys") or []
        for link in trap_links(t):
            i = link["index"]
            key = keys[i] if i < len(keys) else None
            kind = None
            if key and decl:
                kind = "switchable" if key in decl["switchable"] else "fixed" if key in decl["fixed"] else None
            trid = f"trap:{tid}:{i}"
            nodes.append({"id": trid, "kind": "trap", "task": tid, "index": i, "text": link["text"],
                          "key": key, "control": kind or "undeclared"})
            edges.append({"src": f"task:{tid}", "dst": trid, "rel": "has_trap"})
            for c in link["cites"]:
                if c["status"] == "ok":
                    e = {"src": trid, "dst": f"check:{tid}:{c['check']}", "rel": "cites"}
                    if c.get("part"):
                        e["part"] = c["part"]
                    edges.append(e)
                else:
                    edges.append({"src": trid, "dst": None, "rel": "cites_unresolved", "cite": c["cite"],
                                  "status": c["status"]})
    for cat in sorted({t.get("category") for t in tasks.values()}):
        nodes.append({"id": f"category:{cat}", "kind": "category"})
    for ty in sorted({c["type"] for t in tasks.values() for c in t.get("checks") or []}):
        nodes.append({"id": f"check_type:{ty}", "kind": "check_type"})
    return {"nodes": nodes, "edges": edges}


def join_ledger(graph: dict, ledger_path: str) -> dict:
    """Attach per-system attempts/failures to check nodes and bite rates to trap nodes."""
    by_id = {n["id"]: n for n in graph["nodes"]}
    cites = collections.defaultdict(set)          # check id -> trap ids citing it
    trap_checks = collections.defaultdict(set)    # trap id -> check ids
    for e in graph["edges"]:
        if e["rel"] == "cites":
            cites[e["dst"]].add(e["src"]); trap_checks[e["src"]].add(e["dst"])
    with open(ledger_path) as f:
        attempts = [json.loads(l) for l in f]
    systems = sorted({a["harness"] for a in attempts})
    unmatched = collections.Counter()
    task_att = collections.defaultdict(lambda: collections.Counter())
    for a in attempts:
        task_att[a["task"]][(a["harness"], "attempts")] += 1
        task_att[a["task"]][(a["harness"], "passed")] += bool(a["passed"])
        failed_here = set()
        for c in a["checks"]:
            cid = f"check:{a['task']}:{c['name']}"
            n = by_id.get(cid)
            if n is None:
                unmatched[a["task"]] += 1
                continue
            st = n.setdefault("ledger", {s: {"attempts": 0, "failed": 0} for s in systems})
            st[a["harness"]]["attempts"] += 1
            if c.get("required", True) and not c["passed"]:
                st[a["harness"]]["failed"] += 1
                failed_here.add(cid)
        touched = {t for cid in failed_here for t in cites[cid]}
        for trid in {t for t in trap_checks if t.startswith(f"trap:{a['task']}:")}:
            tn = by_id[trid]
            b = tn.setdefault("ledger", {s: {"attempts": 0, "bitten": 0, "exclusive": 0} for s in systems})
            b[a["harness"]]["attempts"] += 1
            if trid in touched:
                b[a["harness"]]["bitten"] += 1
                if any(cid in failed_here and cites[cid] == {trid} for cid in trap_checks[trid]):
                    b[a["harness"]]["exclusive"] += 1
    for tid, cnt in task_att.items():
        n = by_id.get(f"task:{tid}")
        if n is not None:
            n["ledger"] = {s: {"attempts": cnt[(s, "attempts")], "passed": cnt[(s, "passed")]} for s in systems}
    graph["ledger"] = {"path": os.path.relpath(ledger_path, ROOT), "systems": systems, "attempts": len(attempts),
                       "unmatched_check_names": dict(unmatched)}
    return graph


def report(graph: dict) -> str:
    nodes = graph["nodes"]
    tasks = [n for n in nodes if n["kind"] == "task"]
    traps = [n for n in nodes if n["kind"] == "trap"]
    checks = [n for n in nodes if n["kind"] == "check"]
    cited = {e["dst"] for e in graph["edges"] if e["rel"] == "cites"}
    unresolved = [e for e in graph["edges"] if e["rel"] == "cites_unresolved"]
    trap_has_cite = {e["src"] for e in graph["edges"] if e["rel"] in ("cites", "cites_unresolved")}
    L = ["# Measurement graph\n",
         f"{len(tasks)} tasks, {len(traps)} traps, {len(checks)} checks "
         f"({sum(c['required'] for c in checks)} required). Trap switches declared on "
         f"{len({t['task'] for t in traps if t['control'] != 'undeclared'})} task(s).\n",
         "## Citation integrity\n",
         f"- Trap citations resolved: {sum(1 for e in graph['edges'] if e['rel'] == 'cites')}; "
         f"unresolved or ambiguous: {len(unresolved)}"]
    for e in unresolved:
        L.append(f"  - `{e['src'].split(':')[1]}`: \"{e['cite']}\" ({e['status']})")
    no_cite = [t for t in traps if t["id"] not in trap_has_cite]
    L.append(f"- Traps that cite no check: {len(no_cite)} (a trap nothing grades is documentation, not measurement)")
    bare = [c for c in checks if c["required"] and c["id"] not in cited and c["type"] not in STRUCTURAL]
    L.append(f"- Required non-structural checks no trap cites: {len(bare)} (what they measure is undocumented)\n")
    if "ledger" not in graph:
        return "\n".join(L) + "\n"
    systems = graph["ledger"]["systems"]
    L.append(f"## Against the ledger ({graph['ledger']['attempts']} attempts, systems: {', '.join(systems)})\n")
    um = graph["ledger"]["unmatched_check_names"]
    if um:
        L.append(f"- Ledger check names not found in the current task files (renamed since the frozen scorer): "
                 f"{sum(um.values())} verdicts across {len(um)} task(s)")
    led = [c for c in checks if "ledger" in c]
    never = [c for c in led if c["required"] and all(v["failed"] == 0 for v in c["ledger"].values())]
    L.append(f"- Required checks that never failed for any system: {len(never)} of "
             f"{sum(1 for c in led if c['required'])}")
    sat = [t for t in tasks if "ledger" in t and all(v["passed"] == v["attempts"] for v in t["ledger"].values())]
    L.append(f"- Tasks every system passed on every attempt: {len(sat)} of {len(tasks)}")
    tl = [t for t in traps if "ledger" in t]
    dead = [t for t in tl if all(v["bitten"] == 0 for v in t["ledger"].values())]
    L.append(f"- Traps no system ever fell for: {len(dead)} of {len(tl)} cited traps\n")

    def rate(t, key):
        a = sum(v["attempts"] for v in t["ledger"].values())
        return sum(v[key] for v in t["ledger"].values()) / a if a else 0.0
    L.append("## Traps that catch agents most\n")
    L.append("Bite = share of attempts in which a check the trap cites failed. Exclusive = a failed check that only "
             "this trap cites, so the failure is attributable to it.\n")
    L.append("| task | trap | bite | exclusive | " + " | ".join(systems) + " |")
    L.append("|---|---|---|---|" + "---|" * len(systems))
    for t in sorted(tl, key=lambda t: (-rate(t, "bitten"), t["id"]))[:25]:
        per = " | ".join(f"{t['ledger'][s]['bitten']}/{t['ledger'][s]['attempts']}" for s in systems)
        text = t["text"].split("(check")[0].strip().rstrip(";,")
        text = (text[:110] + "…") if len(text) > 110 else text
        L.append(f"| {t['task']} | {text} | {rate(t, 'bitten'):.0%} | {rate(t, 'exclusive'):.0%} | {per} |")
    L.append("\n## Failure rate by check type\n")
    L.append("| check type | required checks | verdicts | failed | " + " | ".join(systems) + " |")
    L.append("|---|---|---|---|" + "---|" * len(systems))
    by_type = collections.defaultdict(list)
    for c in led:
        if c["required"]:
            by_type[c["type"]].append(c)
    for ty, cs in sorted(by_type.items(), key=lambda kv: -sum(sum(v["failed"] for v in c["ledger"].values()) for c in kv[1])):
        att = sum(v["attempts"] for c in cs for v in c["ledger"].values())
        fl = sum(v["failed"] for c in cs for v in c["ledger"].values())
        per = " | ".join(f"{sum(c['ledger'][s]['failed'] for c in cs) / max(1, sum(c['ledger'][s]['attempts'] for c in cs)):.1%}"
                         for s in systems)
        L.append(f"| {ty} | {len(cs)} | {att} | {fl / att:.1%} | {per} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks", default=os.path.join(ROOT, "tasks", "desk"))
    ap.add_argument("--ledger", default=os.path.join(ROOT, "results", "latest", "attempts.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "measurement"))
    ap.add_argument("--no-gen", action="store_true", help="do not ask generators for their trap declarations")
    a = ap.parse_args()
    graph = build_graph(load_tasks(a.tasks), use_gen=not a.no_gen)
    if a.ledger and os.path.isfile(a.ledger):
        graph = join_ledger(graph, a.ledger)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "graph.json"), "w") as f:
        json.dump(graph, f, indent=1)
    rep = report(graph)
    with open(os.path.join(a.out, "report.md"), "w") as f:
        f.write(rep)
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
