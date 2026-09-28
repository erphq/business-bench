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
export const SITE = "https://businessbench.org";
export const SITE_VERSION = "1.0.0";
export const ORG = { name: "ERP.AI", url: "https://erp.ai" };
export const AUTHORS = ["Somesh Misra", "Somnath Misra", "Shashank Dixit"];

export type ArmId = string;
export interface Arm { id: ArmId; system: string; short: string; harness: string; model: string; route: string; slot: number }

/** Display metadata per harness id. Colour slot follows the entity, never its rank. */
const ARM_META: Record<string, Omit<Arm, "id">> = {
  "codex-sol": { system: "Codex / GPT-5.6 sol", short: "Codex", harness: "Codex CLI 0.154.0", model: "gpt-5.6-sol", route: "OpenAI via Codex CLI, high reasoning, CLI-managed sampling", slot: 1 },
  "proto-deepseek": { system: "Proto / DeepSeek V4.1 Flash", short: "Proto", harness: "Proto CLI, runtime c8f62dd60", model: "deepseek/deepseek-v4.1-flash", route: "DeepSeek only, no fallback, high reasoning, temperature 0", slot: 2 },
  "proto-glm": { system: "Proto / GLM-5.3 Flash", short: "Proto GLM", harness: "Proto CLI", model: "z-ai/glm-5.3-flash", route: "OpenRouter pinned to Z.ai", slot: 3 },
  "proto-qwen": { system: "Proto / Qwen 3.8 Flash", short: "Proto Qwen", harness: "Proto CLI", model: "qwen/qwen3.8-flash", route: "OpenRouter pinned to Alibaba", slot: 4 },
  "codex-sol6": { system: "Codex / GPT-6 sol", short: "Codex", harness: "Codex CLI 0.158.0-alpha.2.1", model: "gpt-6-sol", route: "ChatGPT subscription, high reasoning, CLI-managed sampling", slot: 1 },
  "proto-deepseek-direct": { system: "Proto / DeepSeek V4.1 Flash", short: "Proto DeepSeek", harness: "Proto CLI, unreleased build", model: "deepseek-flash", route: "DeepSeek API direct, high reasoning, temperature 0.7", slot: 2 },
  "proto-sol6-sub": { system: "Proto / GPT-6 sol", short: "Proto GPT-6", harness: "Proto CLI, unreleased build", model: "gpt-6-sol", route: "ChatGPT subscription through the Codex sign-in, high reasoning", slot: 3 },
};
export function armMeta(id: ArmId): Arm { return { id, ...(ARM_META[id] ?? { system: id, short: id, harness: "", model: "", route: "", slot: 5 }) }; }

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

/** Process-track pilot tasks: an agent works inside bb-erp over several business days; graded on system state. */
export interface ProcessTask {
  id: string; title: string; family: string; band: string; summary: string;
  agent: { name: string; title: string }; company: string; start: string; grading_date: string;
  turns: { n: number; date: string; budget_s: number; from: string; request: string }[];
  checks: { type: string; name: string; cites: string[] }[];
  negative_controls: { name: string; fails: string[] }[];
  handbook: { file: string; clauses: string[]; markdown: string }[];
}
export function processTasks(): ProcessTask[] { return (tasksJson as any).process as ProcessTask[]; }
/** A published process-track campaign: results/process/<label>/ (provenance, summary and the attempt ledger). */
export interface ProcessCell { system: string; harness: string; model: string; route: string; effort: string }
export interface ProcessAttempt {
  run_id: string; task: string; harness: string; seed: number; run: number; passed: boolean; breach: boolean; error: boolean;
  checks: { name: string; type: string; passed: boolean; breach: boolean }[];
  turns: { n: number; date: string; exit_code: number; timed_out: boolean; wall_s: number }[];
  wall_s: number; usage: { requests: number; input: number; cached_input: number; output: number; reasoning: number };
  cost_usd: number | null;
}
export interface ProcessCampaign {
  label: string; repetitions: number; seed: number; cells: Record<string, ProcessCell>; conditions: string[];
  tasks: string[]; bench_commit_at_run: string; ledger_sha256: string; summary: Record<string, any>; attempts: ProcessAttempt[];
}
export function processCampaign(label: string): ProcessCampaign {
  const dir = `results/process/${label}`;
  const prov = JSON.parse(read(`${dir}/provenance.json`));
  return {
    label, repetitions: prov.repetitions, seed: prov.seed, cells: prov.cells, conditions: prov.conditions, tasks: prov.tasks,
    bench_commit_at_run: prov.bench_commit_at_run, ledger_sha256: prov.ledger_sha256,
    summary: JSON.parse(read(`${dir}/summary.json`)),
    attempts: read(`${dir}/attempts.jsonl`).split("\n").filter(Boolean).map((l) => JSON.parse(l)),
  };
}
export const PROCESS_PILOT = "pilot-process-2026-09-27";
export const FAMILY_LABEL: Record<string, string> = {
  "requisitions-and-purchasing": "Requisitions and purchasing", "receiving-matching-paying": "Receiving, matching and paying",
  "finance-questions": "Finance questions", "record-to-report": "Record to report", "plan-to-produce": "Plan to produce",
};

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
export const ARMS: Arm[] = summary().map((s) => armMeta(s.harness));
export const ARM_BY_ID: Record<ArmId, Arm> = Object.fromEntries(ARMS.map((a) => [a.id, a]));
export const SUMMARY_BY_ID: Record<ArmId, ArmSummary> = Object.fromEntries(summary().map((s) => [s.harness, s]));
export const REPS = provenance().repetitions as number;
export const RELEASE = { id: provenance().campaign as string, version: SITE_VERSION, date: (provenance().scorecard_snapshot_utc as string).slice(0, 10) };

/** A named desk campaign: results/desk/<label>/ holds its declaration, provenance, summary and attempt ledger.
 *  Each is a separate campaign on the released tasks and frozen scorer; none is pooled with results/latest. */
export interface DeskCampaignSummary extends Omit<ArmSummary, "all_three_pass" | "estimated_cost_sum_usd" | "estimated_cost_mean_usd"> {
  all_repetitions_pass: number; estimated_cost_sum_usd: number | null; estimated_cost_mean_usd: number | null;
}
export interface DeskCampaign {
  label: string; title: string; date: string; repetitions: number; window: [string, string]; arms: Arm[];
  configurations: Record<ArmId, Record<string, string | number>>; provenance: any;
  summary: Record<ArmId, DeskCampaignSummary>; attempts: Attempt[]; matrix: Matrix;
  pair?: { arms: [ArmId, ArmId]; difference_percentage_points: number; bootstrap_95_percent_interval_pp: [number, number]; seed: number; samples: number };
}
export function deskCampaignLabels(): string[] {
  const dir = path.join(ROOT, "results", "desk");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((d) => fs.existsSync(path.join(dir, d, "campaign.json"))).sort();
}
const _desk: Record<string, DeskCampaign> = {};
export function deskCampaign(label: string): DeskCampaign {
  if (_desk[label]) return _desk[label];
  const dir = `results/desk/${label}`;
  const prov = JSON.parse(read(`${dir}/provenance.json`));
  const rows: DeskCampaignSummary[] = JSON.parse(read(`${dir}/summary.json`));
  const led: Attempt[] = read(`${dir}/attempts.jsonl`).split("\n").filter(Boolean).map((l) => JSON.parse(l));
  const arms = (prov.included_arms as ArmId[]).map(armMeta);
  const m: Matrix = {};
  for (const a of led) {
    m[a.task] ??= Object.fromEntries(arms.map((x) => [x.id, [] as Attempt[]]));
    m[a.task][a.harness].push(a);
  }
  for (const t of Object.values(m)) for (const arr of Object.values(t)) arr.sort((x, y) => x.run - y.run);
  const date = new Date(prov.execution_window_utc[0]).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  return (_desk[label] = {
    label, title: `Desk comparison, ${date}`, date, repetitions: prov.repetitions, window: prov.execution_window_utc, arms,
    configurations: prov.configurations, provenance: prov, summary: Object.fromEntries(rows.map((s) => [s.harness, s])),
    attempts: led, matrix: m, pair: prov.paired_task_bootstrap,
  });
}
/** The desk campaign the overview and results pages point to, beside the release. */
export const DESK_CAMPAIGN = "complete-desk-comparison-2026-09-28";

/** mulberry32: a small deterministic generator, so every build draws the same bootstrap resamples. */
function prng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** Percentile bootstrap of a mean over tasks. Tasks are resampled with replacement and each task's repetitions stay
 *  together, so the interval reflects variation across these tasks, not across unseen ones. */
export function taskBootstrap(perTask: number[], B = 20000, seed = 20260916): [number, number] {
  const draw = prng(seed), n = perTask.length, means = new Float64Array(B);
  for (let b = 0; b < B; b++) { let s = 0; for (let i = 0; i < n; i++) s += perTask[Math.floor(draw() * n)]; means[b] = s / n; }
  means.sort();
  return [means[Math.floor(0.025 * (B - 1))], means[Math.ceil(0.975 * (B - 1))]];
}

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

/** Retain original grader errors as ungraded, rather than classifying them as agent failures. */
export function scorerTransitions(rows: Pick<Attempt, "passed" | "raw_passed" | "raw_grader_error_count">[]) {
  const counts = { passToPass: 0, failToPass: 0, ungradedToPass: 0, passToFail: 0, failToFail: 0, ungradedToFail: 0 };
  for (const row of rows) {
    if (row.raw_grader_error_count) counts[row.passed ? "ungradedToPass" : "ungradedToFail"]++;
    else if (row.raw_passed) counts[row.passed ? "passToPass" : "passToFail"]++;
    else counts[row.passed ? "failToPass" : "failToFail"]++;
  }
  const rawPasses = counts.passToPass + counts.passToFail;
  const frozenPasses = counts.passToPass + counts.failToPass + counts.ungradedToPass;
  return { ...counts, rawPasses, frozenPasses, net: frozenPasses - rawPasses, attempts: rows.length };
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
  return { ...scorerTransitions(rs), up: up.length, down: down.length, upEq, upOther: up.length - upEq, byCat };
}

/** Two distinct partial-check metrics. Only the attempt-weighted mean shares the
 * acceptance rate's weighting, so its gap has the per-attempt conjunction interpretation. */
export function contractMetrics(rows: Pick<Attempt, "passed" | "checks">[]) {
  if (!rows.length) throw new Error("Contract metrics require at least one attempt.");
  let requiredChecks = 0, checksPassed = 0, fractionSum = 0, accepted = 0;
  for (const row of rows) {
    const checks = row.checks.filter((check) => check.required);
    if (!checks.length) throw new Error("An acceptance contract must contain required checks.");
    const count = checks.filter((check) => check.passed).length;
    if (row.passed !== (count === checks.length)) throw new Error("Acceptance disagrees with required-check conjunction.");
    requiredChecks += checks.length;
    checksPassed += count;
    fractionSum += count / checks.length;
    accepted += Number(row.passed);
  }
  const attemptRate = accepted / rows.length;
  const meanCheckFraction = fractionSum / rows.length;
  return { attempts: rows.length, accepted, requiredChecks, checksPassed, attemptRate,
    meanCheckFraction, pooledCheckRate: checksPassed / requiredChecks, gap: meanCheckFraction - attemptRate };
}

/** Reweight the observed within-category rates; this is a sensitivity calculation,
 * not a prediction for new tasks. Omitted categories receive zero weight. */
export function workloadComparison(weights: Record<string, number>) {
  const known = new Set(CATEGORIES.map((category) => category.id));
  for (const [id, weight] of Object.entries(weights)) {
    if (!known.has(id) || !Number.isFinite(weight) || weight < 0) throw new Error("Use nonnegative finite weights for known desk categories.");
  }
  const total = Object.values(weights).reduce((sum, weight) => sum + weight, 0);
  if (!(total > 0) || !Number.isFinite(total)) throw new Error("At least one category must have positive weight.");
  const normalized = Object.fromEntries(CATEGORIES.map((category) => [category.id, (weights[category.id] ?? 0) / total]));
  const rates: Record<ArmId, number> = {};
  for (const arm of ARMS) {
    rates[arm.id] = CATEGORIES.reduce((sum, category) => {
      const rows = attempts().filter((row) => row.harness === arm.id && row.category === category.id);
      return sum + normalized[category.id] * passes(rows) / rows.length;
    }, 0);
  }
  return { weights: normalized, rates, difference: rates["proto-deepseek"] - rates["codex-sol"] };
}

/** Stable orientation: every difference is Proto + DeepSeek minus Codex + Sol,
 * in rate units (multiply by 100 for percentage points), irrespective of ranking. */
export function deskComparison() {
  const left = "proto-deepseek", right = "codex-sol";
  const leftRows = attempts().filter((row) => row.harness === left);
  const rightRows = attempts().filter((row) => row.harness === right);
  const categories = CATEGORIES.map((category) => {
    const l = leftRows.filter((row) => row.category === category.id);
    const r = rightRows.filter((row) => row.category === category.id);
    const leftPassed = passes(l), rightPassed = passes(r);
    return { ...category, tasks: new Set(l.map((row) => row.task)).size, attempts: l.length,
      leftPassed, rightPassed, leftRate: leftPassed / l.length, rightRate: rightPassed / r.length,
      passDifference: leftPassed - rightPassed, difference: leftPassed / l.length - rightPassed / r.length };
  });
  const released = workloadComparison(Object.fromEntries(categories.map((category) => [category.id, category.tasks])));
  const equalCategories = workloadComparison(Object.fromEntries(categories.map((category) => [category.id, 1])));
  const rawDifference = rawPasses(leftRows) / leftRows.length - rawPasses(rightRows) / rightRows.length;
  const frozenDifference = passes(leftRows) / leftRows.length - passes(rightRows) / rightRows.length;
  return { left, right, categories, released, equalCategories, rawDifference, frozenDifference,
    scorerSensitivity: frozenDifference - rawDifference, passDifference: passes(leftRows) - passes(rightRows) };
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
  /** checkRate is the legacy pooled alias; use an explicit metric in new presentation. */
  checkRate: number; pooledCheckRate: number; meanCheckFraction: number; taskRate: number; gap: number;
  singleFail: number; failedDist: Record<number, number>; meanFracInFailures: number;
  singleFailTypes: [string, number][];
  pass1: number; passAny: number; passAll: number; mixedTasks: number;
  costPerPass: number; medianWall: number;
  byCategory: Record<string, { checkRate: number; pooledCheckRate: number; meanCheckFraction: number; taskRate: number; attempts: number }>;
}
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };
export function findings(armId: ArmId): Findings {
  const ar = attempts().filter((r) => r.harness === armId);
  const req = ar.flatMap((r) => r.checks.filter((c) => c.required));
  const contract = contractMetrics(ar);
  const checkRate = contract.pooledCheckRate;
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
    const cr = ar.filter((r) => r.category === c.id);
    const metrics = contractMetrics(cr);
    byCategory[c.id] = { checkRate: metrics.pooledCheckRate, pooledCheckRate: metrics.pooledCheckRate, meanCheckFraction: metrics.meanCheckFraction, taskRate: metrics.attemptRate, attempts: cr.length };
  }
  return {
    arm: armId, attempts: ar.length, failed: failedRows.length, requiredChecks: req.length, checkRate, pooledCheckRate: checkRate, meanCheckFraction: contract.meanCheckFraction, taskRate, gap: contract.gap,
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

/** Pass rate and pass^k per system with task-clustered 95% intervals. */
export function intervals(armId: ArmId) {
  const byTask: Record<string, boolean[]> = {};
  for (const r of attempts()) if (r.harness === armId) (byTask[r.task] ??= []).push(r.passed);
  const tasks = Object.keys(byTask).sort().map((t) => byTask[t]);
  const frac = tasks.map((v) => v.filter(Boolean).length / v.length);
  const all = tasks.map((v) => (v.every(Boolean) ? 1 : 0));
  const any = tasks.map((v) => (v.some(Boolean) ? 1 : 0));
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  return {
    pass1: { value: mean(frac), ci: taskBootstrap(frac) },
    passAll: { value: mean(all), ci: taskBootstrap(all) },
    passAny: { value: mean(any), ci: taskBootstrap(any) },
  };
}
