// Build-time loader. Everything on the site derives from the repo itself:
// tasks/**/task.yaml (via scripts/export_tasks.py), results/latest/*, scoring/frozen-v7, SPEC.md.
// Nothing is hand-copied.
import fs from "node:fs";
import path from "node:path";
import tasksJson from "../data/tasks.json";

function findRoot(): string {
  let d = process.cwd();
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(d, "tasks", "desk")) && fs.existsSync(path.join(d, "results", "latest"))) return d;
    d = path.dirname(d);
  }
  throw new Error("business-bench repo root not found above " + process.cwd());
}
export const ROOT = findRoot();
export const REPO = "https://github.com/erphq/business-bench";
export const SITE_VERSION = "1.0.0";

export type ArmId = string;
export interface Arm { id: ArmId; system: string; short: string; harness: string; model: string; route: string; slot: number }

/** Display metadata per harness id. Colour slot follows the entity, never its rank. */
const ARM_META: Record<string, Omit<Arm, "id">> = {
  "codex-sol": { system: "Codex / GPT-5.6 sol", short: "Codex", harness: "Codex CLI 0.154.0", model: "gpt-5.6-sol", route: "OpenAI via Codex CLI, high reasoning, CLI-managed sampling", slot: 1 },
  "proto-deepseek": { system: "Proto / DeepSeek V4.1 Flash", short: "Proto", harness: "Proto CLI, runtime c8f62dd60", model: "deepseek/deepseek-v4.1-flash", route: "DeepSeek only, no fallback, high reasoning, temperature 0", slot: 2 },
  "proto-glm": { system: "Proto / GLM-5.3 Flash", short: "Proto GLM", harness: "Proto CLI", model: "z-ai/glm-5.3-flash", route: "OpenRouter pinned to Z.ai", slot: 3 },
  "proto-qwen": { system: "Proto / Qwen 3.8 Flash", short: "Proto Qwen", harness: "Proto CLI", model: "qwen/qwen3.8-flash", route: "OpenRouter pinned to Alibaba", slot: 4 },
};

export const CATEGORIES: { id: string; label: string; deliverable: string }[] = [
  { id: "spreadsheet", label: "Spreadsheet", deliverable: "Reconciled, calculated, or reshaped workbook" },
  { id: "bookkeeping", label: "Bookkeeping", deliverable: "Reconciliation, schedule, transaction classifications" },
  { id: "reports", label: "Reports", deliverable: "Data summary and source-grounded memo" },
  { id: "reformatting", label: "Reformatting", deliverable: "Destination-compatible import file" },
  { id: "extraction", label: "Extraction", deliverable: "Structured records extracted from documents" },
  { id: "drafting", label: "Drafting", deliverable: "Business text preserving required facts and rules" },
  { id: "tooling", label: "Tooling", deliverable: "Small file-based tool or static page" },
];
export const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.label]));

export interface Check { type: string; name: string; required: boolean }
export interface DeskTask {
  id: string; category: string; title: string; ask: string; timeout_s: number;
  checks: Check[]; workspaceFiles: string[]; customCheck: boolean; deliverables: string[];
}
export interface BuildTask {
  id: string; category: string; title: string; ask: string; seed: string[]; timeout_per_turn_s: number;
  changes: { n: number; ask: string; items: number }[]; checklistItems: number; tags: Record<string, number>; coreItems: number[];
}
export function deskTasks(): DeskTask[] { return (tasksJson as any).desk as DeskTask[]; }
export function buildTasks(): BuildTask[] { return (tasksJson as any).build as BuildTask[]; }

export interface Attempt {
  task: string; category: string; harness: ArmId; run: number;
  passed: boolean; raw_passed: boolean; timed_out: boolean; exit_code: number | null;
  wall_s: number | null; cost_usd: number | null; grader_error_count: number; raw_grader_error_count: number;
  checks: { name: string; type: string; required: boolean; passed: boolean }[];
  usage: Record<string, any>; artifact_hashes?: Record<string, string>; receipt_sha256?: string; scorer_manifest_sha256?: string; source_sha256: string;
}
export interface ArmSummary {
  harness: ArmId; tasks: number; attempts: number; passed: number; raw_passed: number; pass_rate: number; all_three_pass: number;
  by_repetition: Record<string, number>; raw_by_repetition: Record<string, number>;
  timed_out: number; nonzero_exit: number; passing_abnormal_exit: number;
  grader_error_attempts: number; raw_grader_error_attempts: number; usage_missing: number;
  cost_observations: number; estimated_cost_sum_usd: number; estimated_cost_mean_usd: number;
  median_wall_s: number; p90_wall_s: number; sum_wall_s: number;
  usage: { input: number; cached_input: number; output: number; uncached_input: number };
  by_category: Record<string, { attempts: number; passed: number }>;
}

const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");
export function readRepoFile(rel: string): string { return read(rel); }

let _sum: ArmSummary[] | null = null;
export function summary(): ArmSummary[] { return (_sum ??= JSON.parse(read("results/latest/summary.json"))); }
export function provenance(): any { return JSON.parse(read("results/latest/provenance.json")); }
export function prices(): Record<string, any> { return JSON.parse(read("bench/prices.json")); }

/** Arms in the release, in the order summary.json lists them. */
export const ARMS: Arm[] = summary().map((s) => ({ id: s.harness, ...(ARM_META[s.harness] ?? { system: s.harness, short: s.harness, harness: "", model: "", route: "", slot: 5 }) }));
export const ARM_BY_ID: Record<ArmId, Arm> = Object.fromEntries(ARMS.map((a) => [a.id, a]));
export const SUMMARY_BY_ID: Record<ArmId, ArmSummary> = Object.fromEntries(summary().map((s) => [s.harness, s]));
export const REPS = provenance().repetitions as number;

let _ledger: Attempt[] | null = null;
export function attempts(): Attempt[] {
  return (_ledger ??= read("results/latest/attempts.jsonl").split("\n").filter(Boolean).map((l) => JSON.parse(l)));
}

/** Per task, per arm: the repetitions in order. */
export type Matrix = Record<string, Record<ArmId, Attempt[]>>;
let _matrix: Matrix | null = null;
export function matrix(): Matrix {
  if (_matrix) return _matrix;
  const m: Matrix = {};
  for (const a of attempts()) {
    m[a.task] ??= Object.fromEntries(ARMS.map((x) => [x.id, [] as Attempt[]]));
    m[a.task][a.harness].push(a);
  }
  for (const t of Object.values(m)) for (const arr of Object.values(t)) arr.sort((x, y) => x.run - y.run);
  return (_matrix = m);
}
export const passes = (list: Attempt[]) => list.filter((a) => a.passed).length;
export const rawPasses = (list: Attempt[]) => list.filter((a) => a.raw_passed).length;

/** Frozen-scorer facts, read from the frozen package itself. */
export interface Scorer { dir: string; manifestSha: string; equivalenceTasks: string[]; fileCount: number; recipe: any; notes: any }
let _scorer: Scorer | null = null;
export function scorer(): Scorer {
  if (_scorer) return _scorer;
  const dir = "scoring/frozen-v7";
  const src = read(`${dir}/scorer.py`);
  const block = src.slice(src.indexOf("CUSTOM = {"), src.indexOf("}", src.indexOf("CUSTOM = {")));
  const equivalenceTasks = [...block.matchAll(/'([a-z0-9-]+)':\s*'/g)].map((m) => m[1]);
  const manifest = JSON.parse(read(`${dir}/manifest.json`));
  const manifestSha = provenance().scorer_manifest_sha256 as string;
  return (_scorer = { dir, manifestSha, equivalenceTasks, fileCount: Object.keys(manifest.files ?? {}).length, recipe: manifest.recipe, notes: manifest.notes });
}

/** How the frozen scorer changed verdicts relative to the runner's original grader. */
export function scorerDelta(armId: ArmId) {
  const rs = attempts().filter((r) => r.harness === armId);
  const up = rs.filter((r) => r.passed && !r.raw_passed);
  const down = rs.filter((r) => !r.passed && r.raw_passed);
  const eq = new Set(scorer().equivalenceTasks);
  const upEq = up.filter((r) => eq.has(r.task)).length;
  const byCat: Record<string, number> = {};
  for (const r of up) byCat[r.category] = (byCat[r.category] ?? 0) + 1;
  return { up: up.length, down: down.length, upEq, upOther: up.length - upEq, byCat };
}

export const fmt = {
  pct: (x: number, d = 1) => `${(x * 100).toFixed(d)}%`,
  usd: (x: number, d = 2) => `$${x.toFixed(d)}`,
  int: (n: number) => n.toLocaleString("en-US"),
  m: (n: number) => (n / 1e6).toFixed(1) + "M",
};

/** Derived phenomena for the findings page. Everything here is recomputed from the ledger at build time. */
export interface Findings {
  arm: ArmId; attempts: number; failed: number; requiredChecks: number;
  checkRate: number; taskRate: number; gap: number;
  singleFail: number; failedDist: Record<number, number>; meanFracInFailures: number;
  singleFailTypes: [string, number][];
  pass1: number; passAny: number; passAll: number; mixedTasks: number;
  costPerPass: number; medianWall: number;
  byCategory: Record<string, { checkRate: number; taskRate: number; attempts: number }>;
}
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };
export function findings(armId: ArmId): Findings {
  const ar = attempts().filter((r) => r.harness === armId);
  const req = ar.flatMap((r) => r.checks.filter((c) => c.required));
  const checkRate = req.filter((c) => c.passed).length / req.length;
  const passed = ar.filter((r) => r.passed);
  const taskRate = passed.length / ar.length;
  const failedRows = ar.filter((r) => !r.passed);
  const nFailed = (r: Attempt) => r.checks.filter((c) => c.required && !c.passed).length;
  const failedDist: Record<number, number> = {};
  for (const r of failedRows) failedDist[nFailed(r)] = (failedDist[nFailed(r)] ?? 0) + 1;
  const singleRows = failedRows.filter((r) => nFailed(r) === 1);
  const types: Record<string, number> = {};
  for (const r of singleRows) { const t = r.checks.find((c) => c.required && !c.passed)!.type; types[t] = (types[t] ?? 0) + 1; }
  const meanFracInFailures = failedRows.length ? failedRows.reduce((s, r) => { const rq = r.checks.filter((c) => c.required); return s + rq.filter((c) => c.passed).length / Math.max(1, rq.length); }, 0) / failedRows.length : 0;
  const byTask: Record<string, boolean[]> = {};
  for (const r of ar) (byTask[r.task] ??= []).push(r.passed);
  const tasks = Object.values(byTask);
  const pass1 = tasks.reduce((s, v) => s + v.filter(Boolean).length / v.length, 0) / tasks.length;
  const passAny = tasks.filter((v) => v.some(Boolean)).length / tasks.length;
  const passAll = tasks.filter((v) => v.every(Boolean)).length / tasks.length;
  const mixedTasks = tasks.filter((v) => v.some(Boolean) && !v.every(Boolean)).length;
  const cost = ar.reduce((s, r) => s + (r.cost_usd ?? 0), 0);
  const byCategory: Findings["byCategory"] = {};
  for (const c of CATEGORIES) {
    const cr = ar.filter((r) => r.category === c.id); const rq = cr.flatMap((r) => r.checks.filter((k) => k.required));
    byCategory[c.id] = { checkRate: rq.filter((k) => k.passed).length / rq.length, taskRate: cr.filter((r) => r.passed).length / cr.length, attempts: cr.length };
  }
  return {
    arm: armId, attempts: ar.length, failed: failedRows.length, requiredChecks: req.length, checkRate, taskRate, gap: checkRate - taskRate,
    singleFail: singleRows.length, failedDist, meanFracInFailures, singleFailTypes: Object.entries(types).sort((a, b) => b[1] - a[1]).slice(0, 4),
    pass1, passAny, passAll, mixedTasks, costPerPass: cost / passed.length, medianWall: median(ar.map((r) => r.wall_s ?? 0)),
    byCategory,
  };
}
/** Agreement between systems at task level. */
export function crossArm() {
  const m = matrix();
  const tasks = Object.values(m);
  const bothAll = tasks.filter((t) => ARMS.every((a) => t[a.id].every((r) => r.passed))).length;
  const anyZero = tasks.filter((t) => ARMS.some((a) => t[a.id].every((r) => !r.passed))).length;
  const allZero = tasks.filter((t) => ARMS.every((a) => t[a.id].every((r) => !r.passed))).length;
  return { bothAll, anyZero, allZero, total: tasks.length };
}
