#!/usr/bin/env python3
"""Export task metadata for the site: site/src/data/tasks.json.

Uses the same YAML parser as bench/grade.py so the site shows exactly what the grader reads.
Reference answers, tolerances, and traps are deliberately not exported.
Run from anywhere: python3 site/scripts/export_tasks.py [--check]
"""
import json, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "..", "src", "data", "tasks.json")

def files(d):
    out = []
    for dp, _, fs in os.walk(d):
        for f in fs:
            out.append(os.path.relpath(os.path.join(dp, f), d))
    return sorted(out)

ITEM = re.compile(r"^\s*(\d+)\.\s+(?:\(CORE\)\s+)?\[([A-Za-z]+)\]", re.M)
def checklist(md):
    items = ITEM.findall(md)
    tags = {}
    for _, t in items: tags[t] = tags.get(t, 0) + 1
    return len(items), tags

def desk():
    root = os.path.join(ROOT, "tasks", "desk"); out = []
    for tid in sorted(os.listdir(root)):
        p = os.path.join(root, tid, "task.yaml")
        if tid.startswith("_") or not os.path.isfile(p): continue
        y = yaml.safe_load(open(p)) or {}
        checks = [{"type": str(c.get("type")), "name": str(c.get("name") or c.get("type")), "required": c.get("required", True) is not False} for c in (y.get("checks") or [])]
        deliverables = sorted({c.get("path") for c in (y.get("checks") or []) if c.get("path")})
        out.append({
            "id": tid, "category": str(y.get("category")), "title": str(y.get("title") or tid), "ask": str(y.get("ask") or "").strip(),
            "timeout_s": int(y.get("timeout_s") or 1200), "checks": checks, "deliverables": deliverables,
            "workspaceFiles": files(os.path.join(root, tid, "workspace")), "customCheck": os.path.isfile(os.path.join(root, tid, "check.py")),
        })
    return out

def build():
    root = os.path.join(ROOT, "tasks", "build"); out = []
    for tid in sorted(os.listdir(root)):
        d = os.path.join(root, tid); p = os.path.join(d, "task.yaml")
        if not os.path.isfile(p): continue
        y = yaml.safe_load(open(p)) or {}
        n, tags = checklist(open(os.path.join(d, "checklist.md"), encoding="utf-8").read())
        changes = []
        for i, rel in enumerate(y.get("changes") or [], 1):
            md = open(os.path.join(d, rel), encoding="utf-8").read()
            owner = re.split(r"^---\s*$", md, maxsplit=1, flags=re.M)[0]
            owner = re.sub(r"^#\s.*$", "", owner, count=1, flags=re.M).strip()
            changes.append({"n": i, "ask": owner, "items": checklist(md)[0]})
        out.append({
            "id": tid, "category": str(y.get("category") or ""), "title": str(y.get("title") or tid), "ask": str(y.get("ask") or "").strip(),
            "seed": [s.replace("seed/", "", 1) for s in (y.get("seed") or [])], "timeout_per_turn_s": int(y.get("timeout_per_turn_s") or 3600),
            "changes": changes, "checklistItems": n, "tags": tags, "coreItems": y.get("core_items") or [],
        })
    return out

def main():
    data = {"desk": desk(), "build": build()}
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != text:
            print("site/src/data/tasks.json is stale; run python3 site/scripts/export_tasks.py", file=sys.stderr); sys.exit(1)
        print(f"tasks.json fresh: {len(data['desk'])} desk, {len(data['build'])} build"); return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(data['desk'])} desk, {len(data['build'])} build")

if __name__ == "__main__":
    main()
