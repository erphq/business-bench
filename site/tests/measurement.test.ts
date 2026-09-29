import { describe, expect, test } from "bun:test";
import { ARMS, SUMMARY_BY_ID, attempts, findings, contractMetrics, scorerTransitions, scorerDelta, workloadComparison, deskComparison } from "../src/lib/data";

const contract = (outcomes: boolean[]) => ({ passed: outcomes.every(Boolean), checks: outcomes.map((passed, index) => ({ name: `check-${index}`, type: "test", required: true, passed })) });

describe("measurement interpretation", () => {
  test("pooling can fall below attempt acceptance when failed tasks have more checks", () => {
    const metrics = contractMetrics([contract([true]), contract([true, true, false, false, false, false, false, false, false, false])]);
    expect(metrics.attemptRate).toBe(0.5);
    expect(metrics.meanCheckFraction).toBe(0.6);
    expect(metrics.pooledCheckRate).toBeCloseTo(3 / 11, 12);
    expect(metrics.pooledCheckRate).toBeLessThan(metrics.attemptRate);
    expect(metrics.gap).toBeCloseTo(0.1, 12);
  });

  test("duplicating a failed predicate changes partial credit without changing acceptance", () => {
    const original = contractMetrics([contract([true]), contract([true, false])]);
    const duplicated = contractMetrics([contract([true]), contract([true, false, false])]);
    expect(original.attemptRate).toBe(duplicated.attemptRate);
    expect(original.meanCheckFraction).not.toBe(duplicated.meanCheckFraction);
    expect(() => contractMetrics([])).toThrow();
    expect(() => contractMetrics([{ passed: true, checks: [] }])).toThrow();
    expect(() => contractMetrics([{ ...contract([true, false]), passed: true }])).toThrow();
  });

  test("paper check-completion numbers reconcile with the frozen ledger", () => {
    const expected = {
      "proto-deepseek": { passedChecks: 3698, fraction: 0.9733780380839204, single: 34 },
      "codex-sol": { passedChecks: 3558, fraction: 0.9441802157042799, single: 39 },
    };
    for (const [arm, values] of Object.entries(expected)) {
      const metrics = contractMetrics(attempts().filter((row) => row.harness === arm));
      expect(metrics.requiredChecks).toBe(3801);
      expect(metrics.checksPassed).toBe(values.passedChecks);
      expect(metrics.meanCheckFraction).toBeCloseTo(values.fraction, 12);
      expect(findings(arm).singleFail).toBe(values.single);
    }
  });

  test("scorer accounting preserves all six original-to-frozen transitions", () => {
    const rows = [
      { raw_passed: true, passed: true, raw_grader_error_count: 0 },
      { raw_passed: true, passed: false, raw_grader_error_count: 0 },
      { raw_passed: false, passed: true, raw_grader_error_count: 0 },
      { raw_passed: false, passed: false, raw_grader_error_count: 0 },
      { raw_passed: false, passed: true, raw_grader_error_count: 1 },
      { raw_passed: false, passed: false, raw_grader_error_count: 1 },
    ];
    expect(scorerTransitions(rows)).toEqual({ passToPass: 1, passToFail: 1, failToPass: 1, failToFail: 1, ungradedToPass: 1, ungradedToFail: 1, rawPasses: 2, frozenPasses: 3, net: 1, attempts: 6 });
    expect(scorerDelta("proto-deepseek").failToPass).toBe(56);
    expect(scorerDelta("proto-deepseek").ungradedToPass).toBe(4);
    expect(scorerDelta("codex-sol").passToFail).toBe(1);
    expect(scorerDelta("codex-sol").net).toBe(42);
  });

  test("workload sensitivity preserves the released weighting and exposes category reversal", () => {
    const comparison = deskComparison();
    for (const arm of ARMS) expect(comparison.released.rates[arm.id]).toBeCloseTo(SUMMARY_BY_ID[arm.id].pass_rate, 12);
    expect(comparison.frozenDifference).toBeCloseTo(34 / 561, 12);
    expect(comparison.rawDifference).toBeCloseTo(16 / 561, 12);
    expect(comparison.scorerSensitivity).toBeCloseTo(18 / 561, 12);
    expect((comparison.equalCategories.difference * 100).toFixed(2)).toBe("3.55");
    expect(workloadComparison({ tooling: 1 }).difference).toBeCloseTo(-7 / 27, 12);
    const weights = { reports: 2, tooling: 1 };
    expect(workloadComparison(weights).rates).toEqual(workloadComparison({ reports: 20, tooling: 10 }).rates);
    expect(weights).toEqual({ reports: 2, tooling: 1 });
    expect(comparison.categories.reduce((sum, category) => sum + category.passDifference, 0)).toBe(34);
  });

  test("invalid workload weights never produce a plausible comparison", () => {
    for (const weights of [{}, { tooling: 0 }, { tooling: -1 }, { tooling: Infinity }, { unknown: 1 }, { reports: NaN }]) {
      expect(() => workloadComparison(weights)).toThrow();
    }
  });
});
