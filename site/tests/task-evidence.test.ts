import { expect, test } from "bun:test";
import { recordedChecks, sameCheckSchema } from "../src/lib/task-evidence";
import { attempts, deskTasks } from "../src/lib/data";

test("missing historical checks are not displayed as zero failures out of all attempts", () => {
  const check = { name: "balance", type: "values", required: true };
  const rows = [{ checks: [{ ...check, passed: true }] }, { checks: [] }];
  expect(recordedChecks(rows)).toEqual([{ ...check, observed: 1, failed: 0 }]);
  expect(sameCheckSchema([check], [])).toBe(false);
});

test("recorded task checks keep replacements and changes in required status distinct", () => {
  const rows = [
    { checks: [{ name: "total", type: "values", required: true, passed: false }] },
    { checks: [{ name: "total", type: "values", required: false, passed: true }] },
  ];
  expect(recordedChecks(rows).map(c => [c.required, c.observed, c.failed])).toEqual([[true, 1, 1], [false, 1, 0]]);
});

test("known frozen scorer replacements are shown from the ledger, not today's task declaration", () => {
  const task = deskTasks().find(t => t.id === "tuition-collections")!;
  const checks = recordedChecks(attempts().filter(r => r.task === task.id));
  expect(sameCheckSchema(task.checks, checks)).toBe(false);
  expect(checks.some(c => c.name === "total still owed")).toBe(true);
  expect(checks.some(c => c.name === "total net due after credits")).toBe(false);
  expect(checks.every(c => c.observed === 6)).toBe(true);
});
