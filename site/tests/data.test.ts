import { describe, expect, test } from "bun:test";
import { ARMS, CATEGORIES, deskTasks, buildTasks, attempts, summary, matrix } from "../src/lib/data";
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
  test("2,244 attempts, four complete arms, every task three times", () => {
    const led = attempts();
    expect(led.length).toBe(2244);
    const m = matrix();
    for (const t of deskTasks()) for (const a of ARMS) expect(m[t.id][a.id].map((r) => r.run)).toEqual([1, 2, 3]);
  });
  test("summary.json agrees with the ledger", () => {
    const led = attempts();
    for (const s of summary()) {
      const arm = led.filter((r) => r.harness === s.harness);
      expect(arm.length).toBe(s.attempts);
      expect(arm.filter((r) => r.passed).length).toBe(s.passed);
      expect(arm.filter((r) => r.timed_out).length).toBe(s.timed_out);
      const byCat: Record<string, number> = {};
      for (const r of arm) if (r.passed) byCat[r.category] = (byCat[r.category] ?? 0) + 1;
      for (const [c, v] of Object.entries(s.by_category)) expect(byCat[c] ?? 0).toBe(v.passed);
    }
  });
});

describe("markdown", () => {
  test("slugify matches the anchors the site links to", () => {
    expect(slugify("10. Validity, safety, and release boundary")).toBe("10-validity-safety-and-release-boundary");
    expect(slugify("1. The problem: completion is a contract, not a conversation")).toBe("1-the-problem-completion-is-a-contract-not-a-conversation");
  });
  test("relative links are rebased and headings get ids", () => {
    const { html, toc } = renderMarkdown("## Hello world\n\nSee [x](docs/a.md).", { linkBase: "https://r/" });
    expect(html).toContain('id="hello-world"');
    expect(html).toContain('href="https://r/docs/a.md"');
    expect(toc[0].text).toBe("Hello world");
  });
});
