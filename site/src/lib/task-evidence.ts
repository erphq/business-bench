import type { Attempt, Check } from "./data";

/** A task's current declaration and its historical scorer may have different checks.
 * Count only verdicts actually present; an absent check is not an observed pass. */
export function recordedChecks(rows: Pick<Attempt, "checks">[]) {
  const groups = new Map<string, Check & { observed: number; failed: number }>();
  for (const row of rows) for (const check of row.checks) {
    const key = JSON.stringify([check.name, check.type, check.required]);
    const group = groups.get(key) ?? { name: check.name, type: check.type, required: check.required, observed: 0, failed: 0 };
    group.observed += 1;
    group.failed += Number(!check.passed);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function sameCheckSchema(left: Check[], right: Check[]) {
  const keys = (checks: Check[]) => checks.map(c => JSON.stringify([c.name, c.type, c.required])).sort();
  return JSON.stringify(keys(left)) === JSON.stringify(keys(right));
}
