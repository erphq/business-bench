"""Event-log emitter with planted deviations (v2 axis 7: process discovery and conformance).

A ProcessModel is a happy path of steps. `simulate` runs cases through it and plants deviations
whose ground truth is returned beside the events, so a task's checks can be exact:

  skip      a step is missing from the case                      truth: case ids
  reorder   two adjacent steps swap                              truth: case ids
  rework    a step returns to an earlier one and repeats          truth: case ids
  sod       the same resource performs two steps that must differ truth: case ids
  bottleneck one resource takes `multiplier` times longer          truth: resource, hours lost

Everything is deterministic in the caller's random.Random.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Step:
    name: str
    resources: list[str]
    hours: tuple[float, float]          # service time range
    wait_hours: tuple[float, float] = (0.5, 8.0)   # queue time before the step starts


@dataclass
class ProcessModel:
    name: str
    steps: list[Step]
    case_prefix: str = "C"
    attributes: dict[str, list] = field(default_factory=dict)   # case attribute -> value pool


@dataclass
class Event:
    case_id: str
    activity: str
    resource: str
    start: datetime
    end: datetime
    attrs: dict = field(default_factory=dict)

    def row(self, ts_fmt: str = "%Y-%m-%d %H:%M:%S") -> list:
        return [self.case_id, self.activity, self.resource, self.start.strftime(ts_fmt), self.end.strftime(ts_fmt), *self.attrs.values()]


def _hours(r: random.Random, lo_hi: tuple[float, float]) -> timedelta:
    return timedelta(hours=r.uniform(*lo_hi))


def simulate(r: random.Random, model: ProcessModel, n_cases: int, start: datetime,
             deviations: dict | None = None, arrival_hours: tuple[float, float] = (0.2, 6.0)) -> tuple[list[Event], dict]:
    """Return (events, truth). `deviations` keys: skip, reorder, rework, sod, bottleneck, each a dict.
    Rates are exact counts, not probabilities: round(rate * n_cases) cases are chosen without replacement,
    disjointly across deviation kinds, so the planted sets never overlap and are always recoverable."""
    d = deviations or {}
    names = [s.name for s in model.steps]
    steps = {s.name: s for s in model.steps}
    case_ids = [f"{model.case_prefix}{i + 1:04d}" for i in range(n_cases)]
    pool = case_ids[:]
    r.shuffle(pool)
    assigned: dict[str, list[str]] = {}
    for kind in ("skip", "reorder", "rework", "sod"):
        if kind in d:
            n = int(round(float(d[kind].get("rate", 0)) * n_cases))
            assigned[kind], pool = sorted(pool[:n]), pool[n:]
    truth: dict = {k: v for k, v in assigned.items()}
    truth["model"] = names
    bott = d.get("bottleneck")
    if bott:
        truth["bottleneck"] = {"activity": bott["activity"], "resource": bott["resource"], "multiplier": float(bott.get("multiplier", 3.0)), "hours_lost": 0.0}
    events: list[Event] = []
    t = start
    for cid in case_ids:
        t += _hours(r, arrival_hours)
        attrs = {k: r.choice(v) for k, v in model.attributes.items()}
        seq = names[:]
        if cid in assigned.get("skip", []):
            seq.remove(d["skip"]["activity"])
        if cid in assigned.get("reorder", []):
            a, b = d["reorder"]["pair"]; ia, ib = seq.index(a), seq.index(b)
            seq[ia], seq[ib] = seq[ib], seq[ia]
        if cid in assigned.get("rework", []):
            act, back = d["rework"]["activity"], d["rework"]["back_to"]
            i = seq.index(act); j = seq.index(back)
            seq = seq[:i + 1] + seq[j:i + 1] + seq[i + 1:]    # ... act, back, ..., act, ...
        sod_pair = tuple(d["sod"]["pair"]) if cid in assigned.get("sod", []) else None
        clock = t
        sod_resource = None
        for act in seq:
            s = steps[act]
            clock += _hours(r, s.wait_hours)
            if sod_pair and act in sod_pair:
                res = sod_resource or r.choice(s.resources)
                sod_resource = res
            else:
                res = r.choice(s.resources)
                if sod_pair and act == sod_pair[0]: sod_resource = res
            dur = _hours(r, s.hours)
            if bott and act == bott["activity"] and res == bott["resource"]:
                extra = dur * (float(bott.get("multiplier", 3.0)) - 1.0)
                truth["bottleneck"]["hours_lost"] += extra.total_seconds() / 3600
                dur += extra
            events.append(Event(cid, act, res, clock, clock + dur, attrs))
            clock += dur
    if bott:
        truth["bottleneck"]["hours_lost"] = round(truth["bottleneck"]["hours_lost"], 2)
    return events, truth


def directly_follows(events: list[Event]) -> set[tuple[str, str]]:
    """The directly-follows relation over the log: the edge set a discovery task must recover."""
    by_case: dict[str, list[Event]] = {}
    for e in events: by_case.setdefault(e.case_id, []).append(e)
    edges: set[tuple[str, str]] = set()
    for evs in by_case.values():
        evs.sort(key=lambda e: e.start)
        for a, b in zip(evs, evs[1:]): edges.add((a.activity, b.activity))
    return edges


def variants(events: list[Event]) -> dict[tuple[str, ...], list[str]]:
    """Activity sequence per case, grouped: the variant analysis truth."""
    by_case: dict[str, list[Event]] = {}
    for e in events: by_case.setdefault(e.case_id, []).append(e)
    out: dict[tuple[str, ...], list[str]] = {}
    for cid, evs in by_case.items():
        key = tuple(e.activity for e in sorted(evs, key=lambda e: e.start))
        out.setdefault(key, []).append(cid)
    return out


def write_eventlog(path: str, events: list[Event], r: random.Random | None = None, shuffle: bool = True,
                   attr_names: list[str] | None = None, mixed_timestamps: bool = False) -> None:
    """CSV export shaped like a real system export: optionally shuffled rows and mixed timestamp formats."""
    import csv
    rows = []
    fmts = ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %I:%M %p"] if mixed_timestamps else ["%Y-%m-%d %H:%M:%S"]
    for i, e in enumerate(events):
        fmt = fmts[i % len(fmts)] if mixed_timestamps else fmts[0]
        rows.append(e.row(fmt))
    if shuffle and r is not None: r.shuffle(rows)
    header = ["case_id", "activity", "resource", "start", "end", *(attr_names or (list(events[0].attrs) if events else []))]
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
