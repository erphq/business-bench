// Build-time loader. Everything on the site derives from the repo itself:
// tasks/**/task.yaml, results/latest/*, SPEC.md. Nothing is hand-copied.
import fs from "node:fs";
import path from "node:path";

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

export type ArmId = "codex-sol" | "proto-deepseek" | "proto-glm" | "proto-qwen";
export interface Arm {
  id: ArmId;
  system: string;
  harness: string;
  model: string;
  route: string;
  slot: number; // categorical palette slot, fixed per arm
}
export const ARMS: Arm[] = [
  { id: "codex-sol", system: "Codex / GPT-5.6 sol", harness: "Codex CLI 0.154.0", model: "gpt-5.6-sol", route: "ChatGPT subscription (Codex OAuth), high reasoning", slot: 1 },
  { id: "proto-deepseek", system: "Proto / DeepSeek V4.1 Flash", harness: "Proto CLI", model: "deepseek/deepseek-v4.1-flash", route: "OpenRouter, pinned to DeepSeek", slot: 2 },
  { id: "proto-glm", system: "Proto / GLM-5.3 Flash", harness: "Proto CLI", model: "z-ai/glm-5.3-flash", route: "OpenRouter, pinned to Z.ai", slot: 3 },
  { id: "proto-qwen", system: "Proto / Qwen 3.8 Flash", harness: "Proto CLI", model: "qwen/qwen3.8-flash", route: "OpenRouter, pinned to Alibaba", slot: 4 },
];
export const ARM_BY_ID = Object.fromEntries(ARMS.map((a) => [a.id, a])) as Record<ArmId, Arm>;

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

import tasksJson from "../data/tasks.json";

/** Task metadata exported by site/scripts/export_tasks.py with the grader's own YAML parser. */
export function deskTasks(): DeskTask[] { return (tasksJson as any).desk as DeskTask[]; }
export function buildTasks(): BuildTask[] { return (tasksJson as any).build as BuildTask[]; }

export interface Attempt {
  task: string; category: string; harness: ArmId; run: number; passed: boolean; timed_out: boolean; exit_code: number | null;
  wall_s: number | null; cost_usd: number | null; grader_error_count: number;
  checks: { name: string; type: string; required: boolean; passed: boolean }[];
}
export interface ArmSummary {
  harness: ArmId; tasks: number; attempts: number; passed: number; pass_rate: number; all_three_pass: number;
  by_repetition: Record<string, number>; timed_out: number; nonzero_exit: number; passing_abnormal_exit: number;
  grader_error_attempts: number; usage_missing: number; cost_observations: number; estimated_cost_sum_usd: number;
  estimated_cost_mean_usd: number; median_wall_s: number; by_category: Record<string, { attempts: number; passed: number }>;
}

let _ledger: Attempt[] | null = null;
export function attempts(): Attempt[] {
  if (_ledger) return _ledger;
  const p = path.join(ROOT, "results", "latest", "attempts.jsonl");
  _ledger = fs.readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  return _ledger;
}
export function summary(): ArmSummary[] {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "results", "latest", "summary.json"), "utf8"));
}
export function provenance(): any {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "results", "latest", "provenance.json"), "utf8"));
}
export function prices(): Record<string, any> {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "bench", "prices.json"), "utf8"));
}

/** Per task, per arm: the three repetitions in order. */
export type Matrix = Record<string, Record<ArmId, Attempt[]>>;
let _matrix: Matrix | null = null;
export function matrix(): Matrix {
  if (_matrix) return _matrix;
  const m: Matrix = {};
  for (const a of attempts()) {
    m[a.task] ??= { "codex-sol": [], "proto-deepseek": [], "proto-glm": [], "proto-qwen": [] };
    m[a.task][a.harness].push(a);
  }
  for (const t of Object.values(m)) for (const arr of Object.values(t)) arr.sort((x, y) => x.run - y.run);
  _matrix = m;
  return m;
}

export function passes(list: Attempt[]) { return list.filter((a) => a.passed).length; }

export function readRepoFile(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

export const fmt = {
  pct: (x: number, d = 1) => `${(x * 100).toFixed(d)}%`,
  usd: (x: number, d = 2) => `$${x.toFixed(d)}`,
  min: (s: number) => `${(s / 60).toFixed(1)} min`,
  int: (n: number) => n.toLocaleString("en-US"),
};
