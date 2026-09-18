"""Unit size per SKU, graded jointly with pack_qty where the field guide supports two splits.

A package of two counted items typed 'pk of 2', '2-pack' or '2 pcs' (reference/catalog_clean_other_pack_split.csv
lists them) fits both of the guide's rules: 'pack_qty: How many units are sold together' gives 2 x 1 ea, and 'For
counted goods ... put the count in one package in unit_size' gives 1 x 2 ea. For those SKUs the deliverable's
(pack_qty, unit_size) pair must equal the pair in reference/catalog_clean.csv or the pair in the alternative file, so
either consistent split passes and a mixed pair (2 x 2, 1 x 1) does not. Every other SKU compares unit_size alone
against reference/catalog_clean.csv, exactly as the numeric csv_values_match check did (tolerance 0.01, a blank
reference cell needs a blank deliverable cell).
"""
import os

NAME = "unit size"
TOL = 0.01


def _grade():
    try:
        from grade import find_file, read_table, num_eq  # the bench grader's own readers
    except ImportError:  # grader run as a script from elsewhere: use the running module
        import __main__ as g
        find_file, read_table, num_eq = g.find_file, g.read_table, g.num_eq
    return find_file, read_table, num_eq


def _rows(df):
    keys = [str(v).strip().lower() for v in df["sku"].astype(str)]
    return dict(zip(keys, df.to_dict("records")))


def check(ws, ref):
    find_file, read_table, num_eq = _grade()
    p = find_file(ws, "catalog_clean.csv")
    if not p:
        return [{"name": NAME, "passed": False, "detail": "output file missing"}]
    df = read_table(p)
    if "sku" not in df.columns:
        return [{"name": NAME, "passed": False, "detail": f"column 'sku' not found; have {list(df.columns)}"}]
    rdf = read_table(os.path.join(ref, "catalog_clean.csv"))
    alt = _rows(read_table(os.path.join(ref, "catalog_clean_other_pack_split.csv")))
    got = _rows(df)

    def same(grow, rrow, cols):
        for c in cols:
            gv, rv = str(grow.get(c, "")).strip(), str(rrow.get(c, "")).strip()
            if gv == "" or rv == "":
                if not (gv == "" and rv == ""):
                    return False
            elif not num_eq(gv, rv, TOL):
                return False
        return True

    total = hits = 0
    wrong = []
    for key, rrow in _rows(rdf).items():
        total += 1
        grow = got.get(key)
        if grow is None:
            ok = False
        elif key in alt:
            pair = ["pack_qty", "unit_size"]
            ok = same(grow, rrow, pair) or same(grow, alt[key], pair)
        else:
            ok = same(grow, rrow, ["unit_size"])
        hits += ok
        if not ok:
            wrong.append(key)
    acc = hits / total if total else 0.0
    return [{"name": NAME, "passed": acc >= 1.0,
             "detail": f"accuracy {acc:.3f} (min 1.0); wrong={wrong[:8]}; two-count packs graded as a pack_qty x unit_size pair: {sorted(alt)}"}]
