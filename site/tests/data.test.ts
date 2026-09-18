import { describe, expect, test } from "bun:test";
import { ARMS, CATEGORIES, deskTasks, buildTasks, attempts, summary, matrix, scorer, readRepoFile } from "../src/lib/data";
import { slugify, renderMarkdown } from "../src/lib/markdown";

const known = new Set(CATEGORIES.map((c) => c.id));

describe("task export", () => {
  test("inventory sizes match the release", () => {
    expect(deskTasks().length).toBe(187);
    expect(buildTasks().length).toBe(20);
  });
  test("every desk task has a known category, an ask, and a required check", () => {
    for (const t of deskTasks()) {
      expect(known.has(t.category)).toBe(true);
      expect(t.ask.length).toBeGreaterThan(20);
      expect(t.checks.some((c) => c.required)).toBe(true);
      expect(t.deliverables.length).toBeGreaterThan(0);
    }
  });
  test("every build task has three changes and a checklist", () => {
    for (const b of buildTasks()) {
      expect(b.changes.length).toBe(3);
      expect(b.checklistItems).toBeGreaterThanOrEqual(15);
      for (const c of b.changes) expect(c.ask.length).toBeGreaterThan(10);
    }
  });
});

describe("ledger", () => {
  test("1,122 attempts, two complete arms, every task three times", () => {
    const led = attempts();
    expect(led.length).toBe(1122);
    expect(ARMS.map((a) => a.id).sort()).toEqual(["codex-sol", "proto-deepseek"]);
    const m = matrix();
    for (const t of deskTasks()) for (const a of ARMS) expect(m[t.id][a.id].map((r) => r.run)).toEqual([1, 2, 3]);
  });
  test("summary.json agrees with the ledger", () => {
    const led = attempts();
    for (const s of summary()) {
      const arm = led.filter((r) => r.harness === s.harness);
      expect(arm.length).toBe(s.attempts);
      expect(arm.filter((r) => r.passed).length).toBe(s.passed);
      expect(arm.filter((r) => r.raw_passed).length).toBe(s.raw_passed);
      expect(arm.filter((r) => r.timed_out).length).toBe(s.timed_out);
      const byCat: Record<string, number> = {};
      for (const r of arm) if (r.passed) byCat[r.category] = (byCat[r.category] ?? 0) + 1;
      for (const [c, v] of Object.entries(s.by_category)) expect(byCat[c] ?? 0).toBe(v.passed);
    }
  });
});

describe("frozen scorer", () => {
  test("equivalence task list is read from scorer.py and every task exists", () => {
    const sc = scorer();
    expect(sc.equivalenceTasks.length).toBe(7);
    const ids = new Set(deskTasks().map((t) => t.id));
    for (const t of sc.equivalenceTasks) expect(ids.has(t)).toBe(true);
    expect(readRepoFile("scoring/frozen-v7/scorer.py")).toContain(`'${sc.equivalenceTasks[0]}'`);
  });
  test("every attempt points at the released scorer manifest", () => {
    const sc = scorer();
    for (const r of attempts()) expect(r.scorer_manifest_sha256).toBe(sc.manifestSha);
  });
});

describe("markdown", () => {
  test("slugify matches the anchors the site links to", () => {
    expect(slugify("5. Validity and limitations")).toBe("5-validity-and-limitations");
    expect(slugify("1. Introduction")).toBe("1-introduction");
    expect(slugify("A.2 Scoring and verification")).toBe("a2-scoring-and-verification");
  });
  test("relative links are rebased and headings get ids", () => {
    const { html, toc } = renderMarkdown("## Hello world\n\nSee [x](docs/a.md).", { linkBase: "https://r/" });
    expect(html).toContain('id="hello-world"');
    expect(html).toContain('href="https://r/docs/a.md"');
    expect(toc[0].text).toBe("Hello world");
  });
});

import { findings, crossArm, SUMMARY_BY_ID } from "../src/lib/data";
describe("findings", () => {
  test("derived rates agree with summary.json and are internally consistent", () => {
    for (const a of ARMS) {
      const f = findings(a.id), s = SUMMARY_BY_ID[a.id];
      expect(Math.abs(f.pass1 - s.pass_rate)).toBeLessThan(1e-9);
      expect(Math.round(f.passAll * s.tasks)).toBe(s.all_three_pass);
      expect(f.checkRate).toBeGreaterThanOrEqual(f.taskRate);
      expect(f.passAny).toBeGreaterThanOrEqual(f.pass1);
      expect(f.pass1).toBeGreaterThanOrEqual(f.passAll);
      expect(Object.values(f.failedDist).reduce((x, y) => x + y, 0)).toBe(f.failed);
      expect(f.failed + s.passed).toBe(s.attempts);
      expect(f.failedDist[0] ?? 0).toBe(0);
    }
    const x = crossArm();
    expect(x.total).toBe(187);
    expect(x.bothAll + x.anyZero).toBeLessThanOrEqual(187);
  });
});
