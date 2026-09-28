# Harness adapter contract

`harnesses/<name>.sh <workspace_dir> <prompt_file> <out_dir>`

The adapter runs headlessly on the prompt, using the supplied workspace for requested
deliverables. Harness event streams and final messages belong in `out_dir`; some
runtimes also create session files in their home or workspace, which remain private.
The runner records the adapter's exit code, wall time and timeout separately from
artifact acceptance. Desk and process runners allow a 60-second shutdown margin
beyond the declared turn timeout before terminating the process group.

## Effective configuration defines the cell

Adapter names identify defaults, not immutable runtime settings. For example,
`codex-sol.sh` defaults to `gpt-5.6-sol` and high reasoning but accepts `CODEX_MODEL`
and `CODEX_BIN`. Proto adapters accept runtime paths and budget overrides; model and
provider settings also come from the configured home. Record effective model, route,
reasoning, runtime revision, tools/skills, home template, image digest and resource
limits before claiming replication. A changed configuration is a new cell.

The runners provide `BENCH_TIMEOUT_MS`, `BENCH_ROOT`, and host-side `BENCH_RUN_DIR`.
Containerized adapters receive the explicitly forwarded environment, not every host
variable. Proto receives `PROTO_BENCH_HOME` where a template is copied.

## Actual state and isolation boundaries

| Track/cell | Home handling | Execution boundary |
|---|---|---|
| Desk/build Proto | Copies `homes/<cell>` per attempt/turn; template contents can include skills and credentials | Optional Docker; local mode remains host-accessible |
| Desk/build Codex | Uses the configured `CODEX_HOME`; Docker mounts `homes/codex-sol` writable and shared between attempts | Optional Docker; home/session state is not reset per attempt |
| Process adapters | Copies `homes/<cell>` per turn when present, preserving symlinks; workspace and ERP state persist across turns | Local processes only; no container/filesystem isolation |

A dedicated home is an operator requirement, not proof that personal skills,
connectors, plugins or prior state cannot load. Codex's optional fake home applies
only if that directory exists; its behavior depends on the files the operator puts
there. Set and record account app/plugin configuration and inspect the actual tool
inventory. Historical connector errors are not guarantees about later environments.

Container desk runs mount the run directory and adapter scripts, excluding the host
task/reference tree. Network access remains enabled, and public task definitions may
still be discoverable. Local runners inherit host access and must not be described as
answer-isolated evaluations.

## Process turns

The runner supplies `ERP_URL`, `ERP_TOKEN`, and an `erp` executable on `PATH`.
Each turn is a fresh agent invocation with the persistent workspace and ERP state.
For Proto it points provider traces at the turn output directory. If a home template
is missing, adapter defaults can still apply; verify the intended template exists.

After a turn, `process_run._scrub` removes credential files and file symlinks from
the copied home and redacts recognized secret-valued JSON fields. This is targeted
cleanup, not a guarantee that logs or arbitrary files contain no secrets. Desk/build
raw attempt directories retain homes without that scrub. Keep raw results private;
review any artifact or trace before sharing, and use the public exporters' allowlist.
