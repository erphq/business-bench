"""Delegation envelope tooling (bench/envelope.py). No model calls, no LibreOffice; a few seconds."""
import contextlib, io, json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import envelope  # noqa: E402

PM = ROOT / 'tasks' / 'desk' / 'project-margin'
EFFECTS = {"baseline": 3.0, "abilities": {"sys-a": 0.6, "sys-b": -0.6},
           "effects": {"join_key": 0.8, "drafts": 1.2, "unbilled": 0.5, "credit_brackets": 0.4, "format_noise": 0.6}}


def load(p):
    with open(p) as f:
        return json.load(f)


def cli(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = envelope.main([str(a) for a in args])
    return rc, buf.getvalue()


class VariantChoice(unittest.TestCase):
    decl = {"switchable": {"a": "", "b": "", "c": ""}, "requires": {"c": "b"}}

    def test_single_pairs_full_dedupe(self):
        v, d = envelope.choose_variants(self.decl, "single")
        self.assertEqual([sorted(x["effective"]) for x in v], [[], ["a"], ["c"], ["b", "c"]])
        self.assertEqual(d, [])
        v, d = envelope.choose_variants(self.decl, "pairs")
        effs = [frozenset(x["effective"]) for x in v]
        self.assertEqual(len(effs), len(set(effs)))
        self.assertIn({"requested": ["b", "c"], "same_as_effective": ["b", "c"]}, d)   # b off implies c off
        v, _ = envelope.choose_variants(self.decl, "full")
        self.assertEqual(len(v), 6)   # 8 subsets, {b} and {b,c} collapse, {a,b} and {a,b,c} collapse
        self.assertEqual(len(v), len(envelope.feasible_off_sets(self.decl)))
        v, _ = envelope.choose_variants(self.decl, "random:3", seed=1)
        self.assertEqual(sorted(v[0]["effective"]), [])
        self.assertEqual(len(v), 4)


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        rc, cls.plan_out = cli("plan", "--task", "project-margin", "--design", "single", "--root", cls.d / "single")
        assert rc == 0, cls.plan_out
        cls.man_single = load(cls.d / "single" / "manifest.json")
        rc, _ = cli("plan", "--task", "project-margin", "--design", "full", "--root", cls.d / "full", "--dry-run")
        cls.full = cls.d / "full" / "manifest.json"
        rc, _ = cli("simulate", "--manifest", cls.full, "--effects", json.dumps(EFFECTS), "--systems", "sys-a,sys-b",
                    "--reps", 40, "--seed", 3, "--out", cls.d / "sim")
        rc, cls.fit_out = cli("fit", "--manifest", cls.full, "--results", cls.d / "sim", "--out", cls.d / "F.json",
                              "--boot", 30)
        cls.fit = load(cls.d / "F.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # ---- plan
    def test_plan_manifest_single(self):
        m = self.man_single
        self.assertEqual(m["task"], "project-margin")
        self.assertEqual([v["id"] for v in m["variants"]], [f"v0{i}" for i in range(6)])
        self.assertTrue(m["variants"][0]["canonical"])
        fn = next(v for v in m["variants"] if "format_noise" in v["traps_off"])
        self.assertEqual(fn["effective_off"], ["credit_brackets", "format_noise"])   # requires closure
        effs = [tuple(v["effective_off"]) for v in m["variants"]]
        self.assertEqual(len(effs), len(set(effs)))
        for v in m["variants"]:
            d = self.d / "single" / v["dir"]
            self.assertTrue((d / "task.yaml").is_file() and (d / "workspace").is_dir())
            self.assertEqual(v["sha256"]["reference"], m["variants"][0]["sha256"]["reference"])
            self.assertEqual(v["sha256"]["checks"], m["variants"][0]["sha256"]["checks"])
            if not v["canonical"]:
                self.assertNotEqual(v["sha256"]["workspace"], m["variants"][0]["sha256"]["workspace"])
        self.assertTrue(m["canonical_matches_published"]["reference"])
        self.assertTrue(m["canonical_matches_published"]["checks"])

    def test_plan_full_dry_run_dedupes(self):
        m = load(self.full)
        self.assertEqual(len(m["variants"]), 24)          # 32 subsets minus 8 implied by format_noise
        self.assertEqual(len(m["duplicates_dropped"]), 8)
        self.assertFalse(m["materialized"])

    # ---- simulate / fit
    def test_simulated_records_are_labelled(self):
        rec = load(next((self.d / "sim").glob("*/result.json")))
        self.assertTrue(rec["synthetic"])
        self.assertIn("SYNTHETIC", rec["synthetic_note"])
        self.assertIn("SYNTHETIC", self.fit_out)

    def test_fit_recovers_known_effects(self):
        der = self.fit["derived"]
        for t, w in EFFECTS["effects"].items():
            self.assertAlmostEqual(der[f"effect:{t}"]["estimate"], w, delta=0.45, msg=t)
        self.assertAlmostEqual(der["ability:sys-a"]["estimate"] - der["ability:sys-b"]["estimate"], 1.2, delta=0.35)
        self.assertAlmostEqual(der["baseline"]["estimate"], 3.0, delta=0.6)

    # ---- register / score
    def test_register_and_score(self):
        P, R = self.d / "P.json", self.d / "registry.jsonl"
        rc, out = cli("predict", "--manifest", self.d / "single" / "manifest.json", "--systems", "sys-a,sys-b",
                      "--from-ledger", ROOT / "results" / "latest" / "attempts.jsonl", "--out", P, "--draws", 500)
        self.assertEqual(rc, 0)
        doc = load(P)
        self.assertEqual(doc["method"], "canonical-rate + prior")
        self.assertIn("prior", doc["method_note"])
        self.assertEqual(len(doc["cells"]), 12)
        self.assertEqual(envelope.content_sha(doc), doc["sha256"])
        man = self.d / "single" / "manifest.json"
        late, early = self.d / "late", self.d / "early"
        cli("simulate", "--manifest", man, "--effects", json.dumps(EFFECTS), "--systems", "sys-a,sys-b",
            "--reps", 5, "--out", late, "--start-utc", "2099-01-01T00:00:00Z")
        cli("simulate", "--manifest", man, "--effects", json.dumps(EFFECTS), "--systems", "sys-a,sys-b",
            "--reps", 5, "--out", early, "--start-utc", "2000-01-01T00:00:00Z")
        # not registered yet
        rc, out = cli("score", "--predictions", P, "--results", late, "--registry", R)
        self.assertEqual(rc, 2); self.assertIn("not pre-registered", out)
        rc, _ = cli("register", P, "--registry", R)
        self.assertEqual(rc, 0)
        entry = json.loads(Path(R).read_text().splitlines()[-1])
        self.assertEqual(entry["predictions_sha256"], doc["sha256"])
        self.assertIn("git_head", entry)
        # runs that started before registration
        rc, out = cli("score", "--predictions", P, "--results", early, "--registry", R)
        self.assertEqual(rc, 2); self.assertIn("not pre-registered", out)
        # proper order
        rc, out = cli("score", "--predictions", P, "--results", late, "--registry", R, "--out", self.d / "S.json")
        self.assertEqual(rc, 0, out)
        s = load(self.d / "S.json")
        self.assertEqual(len(s["cells"]), 12)
        self.assertTrue(s["synthetic"])
        self.assertIn("Brier", out); self.assertIn("Reliability", out); self.assertIn("| miss |", out)
        # tampering after registration
        doc["cells"][0]["p_mean"] = 0.5
        Path(P).write_text(json.dumps(doc))
        rc, out = cli("score", "--predictions", P, "--results", late, "--registry", R)
        self.assertEqual(rc, 2); self.assertIn("sha256", out)

    # ---- envelope
    def test_envelope_output(self):
        rc, out = cli("envelope", "--fit", self.d / "F.json", "--system", "sys-a", "--k", 5, "--threshold", 0.5,
                      "--json", self.d / "E.json")
        self.assertEqual(rc, 0)
        self.assertIn("SYNTHETIC", out)
        e = load(self.d / "E.json")
        self.assertEqual(len(e["combinations"]), 24)
        desc = self.fit["traps"]["switchable"]
        inside = [c for c in e["combinations"] if c["passk"] >= 0.5]
        self.assertTrue(inside)
        top = max(inside, key=lambda c: len(c["on"]))
        for t in top["on"]:
            self.assertIn(desc[t], out)           # business-readable trap descriptions
        self.assertIn("takes it out of the envelope", out)
        for c in e["combinations"]:               # pass^k falls when a trap is added (all effects positive here)
            for c2 in e["combinations"]:
                if set(c["on"]) < set(c2["on"]):
                    self.assertLessEqual(c2["passk"], c["passk"] + 1e-9)


if __name__ == '__main__':
    unittest.main()
