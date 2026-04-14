# SWE-bench Lite Validation Log

This file records the milestone-by-milestone validation work for the generic
`clawgraph proxy + mini-SWE-agent + SWE-bench Lite` flow.

## M1. Proxy standalone

Status: completed

Work:

- started `clawgraph proxy` against DeepSeek's OpenAI-compatible endpoint
- verified a raw chat-completions request through the proxy
- confirmed new sessions and facts were persisted to the SQLite store

Issues found:

- the proxy only matched `/v1/chat/completions` and `/v1/responses`
- OpenAI SDK and LiteLLM commonly call `/chat/completions` or `/responses`

Fix:

- added generic root-path handling in [`src/clawgraph/proxy/server.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/proxy/server.py)
- added regression coverage in [`tests/test_proxy.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/tests/test_proxy.py)

## M2. Agent through proxy

Status: completed

Work:

- configured `mini-SWE-agent` to point its OpenAI-compatible base URL at the proxy
- verified a `mini` task created `/tmp/clawgraph_m2_probe.txt` with exact content `OK`
- confirmed the run was captured as one session with one stable run id

Issues found:

- first-run `mini-SWE-agent` setup blocked non-interactive execution
- LiteLLM cost calculation failed for OpenAI-compatible DeepSeek model names
- proxy originally required the agent to send the real upstream bearer token

Fix:

- initialized `mini-SWE-agent` global config once using `mini-extra config set`
- added `cost_tracking: "ignore_errors"` to the benchmark proxy template
- added generic proxy-side upstream bearer injection via `CLAWGRAPH_UPSTREAM_API_KEY`

## M3. Single-instance SWE-bench Lite smoke

Status: completed

Work:

- loaded `sqlfluff__sqlfluff-1625` from `princeton-nlp/SWE-Bench_Lite`
- prepared a local checkout at the benchmark's `base_commit`
- ran `mini-extra swebench-single` against that instance with the model traffic routed through proxy
- captured the full benchmark session into ClawGraph
- validated the prepared local env with working `python`, `pip`, and editable
  repo install

Issues found:

- Docker Desktop was not available for the default benchmark container runtime
- local benchmark runs inherited a broken Homebrew `python` / `pip`

Fix:

- added a generic local-instance preparation helper at
  [`benchmarks/swebench_lite/prepare_local_instance.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/prepare_local_instance.py)
- the helper pins the repo to the benchmark base commit, creates a local venv,
  and writes a `mini.local.yaml` environment override for `mini-extra`
- the helper also pins `setuptools<81` so older repos that still import
  `pkg_resources` keep working in the local benchmark venv

## M4. Stable session/run identity

Status: completed

Work:

- inspected the `sqlfluff__sqlfluff-1625` benchmark session in ClawGraph
- verified all captured LLM requests landed in one session and one run

Evidence:

- session: `sess_7b5b39853f894300ab6dcf393d39d262`
- run: `run_499f38739caf4e54b066878143594ae2`

## M5. Generic artifact bootstrap and SFT readiness

Status: completed

Work:

- persisted `openclaw-defaults` artifacts for the benchmark session
- verified `clawgraph readiness --builder sft --json`
- exported `/tmp/clawgraph-exports/sqlfluff.sft.jsonl`

Evidence:

- persisted artifacts: `21`
- predicted SFT records: `20`
- exported SFT records: `20`

## M6. Generic scoring and binary RL readiness

Status: completed

Work:

- verify the benchmark session has enough score/annotation artifacts for
  `binary_rl`
- exported one binary RL dataset file using the generic path

Evidence:

- `binary_rl` readiness: ready
- predicted binary RL records: `20`
- exported file: `/tmp/clawgraph-exports/sqlfluff.binary_rl.jsonl`

## P1. Phase-1 dashboard completion

Status: completed

Work:

- added a shared dashboard snapshot at
  [`src/clawgraph/dashboard.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/dashboard.py)
- added `clawgraph inspect dashboard` with `--watch`, `--interval-seconds`,
  and `--iterations`
- added a shared web bundle builder at
  [`src/clawgraph/dashboard_bundle.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/dashboard_bundle.py)
- rewired
  [`web/scripts/prod_dashboard_bundle.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/scripts/prod_dashboard_bundle.py)
  to reuse the same dashboard read model instead of inferring its own E2 logic
- added regression coverage in
  [`tests/test_dashboard.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/tests/test_dashboard.py)

Issues found:

- the terminal-only snapshot was not enough for "real-time observability"
- the web bridge had drifted from CLI semantics and incorrectly promoted
  `E1 + any ready builder` to `E2`
- the old web bridge also counted `facts` as export-ready learning data

Fix:

- introduced a polling watch mode in the CLI
- centralized web bundle aggregation on the shared dashboard read model
- aligned readiness/export-ready statistics to learning builders only

## P1-live. Proxy + mini-SWE-agent + dashboard joint validation

Status: completed

Work:

- started a live proxy against DeepSeek with store
  `/tmp/clawgraph-live-phase1.db`
- verified a direct request through proxy returned exact content `OK`
- started `clawgraph inspect dashboard --watch` against the same store
- started the local web dashboard in prod/local-store mode
- ran one live `mini-extra swebench-single` instance for
  `sqlfluff__sqlfluff-1625` through the proxy using the prepared local testbed

Evidence:

- direct proxy smoke request returned `OK`
- dashboard watch first showed one probe session, then a new benchmark session:
  `sess_c8dfae9a2c404ef2860d3fa55bac0808`
- the live benchmark run was captured as
  `run_2e6aae5a35084d7f9b9e4ea90865528c`
- during the live run, dashboard request count increased from `11` to `26`
  while `open_count=1`, matching the in-progress agent state
- the web dashboard returned HTTP 200 and rendered
  `当前使用本地 ClawGraph Store` together with the same live
  `session_id` / `run_id`

Issues found:

- sandboxed local commands could not talk to the elevated proxy or bind local
  dashboard ports

Fix:

- ran the live proxy, dashboard dev server, and live verification curls in the
  same elevated context when needed

## P2. Phase-2 workflow read model and friendly UI

Status: completed

Work:

- extended the shared dashboard snapshot with `workflow_overview` and
  `workflow_runs`
- added run-scoped `stage`, `blockers`, `review_status`, and `next_action`
- extended the web bundle with `workflowLanes`, `workflowRuns`, and
  `ingestSummary`
- rewrote the main dashboard entry points to present a real-data workflow:
  overview, access, sessions, replay, supervision, and navigation

Issues found:

- the phase-1 UI still used too many internal terms (`E1/E2`, `readiness`,
  `artifact`, `cohort`) without telling the user what to do next
- overview and access still contained hard-coded demo numbers or routes
- replay and supervision pages still leaked scenario-specific mock text

Fix:

- shifted the UI to the user-facing sequence `采集 -> 补标签 -> 复核 ->
  导出/评估`
- replaced hard-coded value storytelling with live store-derived metrics
- exposed blockers and next actions directly from the shared Python read model

## P2-live. Proxy + mini-SWE-agent + dashboard with live workflow stages

Status: completed

Work:

- started a fresh live proxy against DeepSeek with store
  `/tmp/clawgraph-live-phase2.db`
- started `clawgraph inspect dashboard --watch`
- started the production Next.js dashboard against the same store
- sent a direct proxy smoke request
- prepared a fresh local `sqlfluff__sqlfluff-1625` testbed
- started a live `mini-extra swebench-single` run through the proxy

Evidence:

- direct proxy smoke created
  `sess_fa375504d7ab4e778d603dd836df39af` /
  `run_9333a326446b4b59813ff0bf0c7a2228`
- the live benchmark run created
  `sess_1b17b5951ed74455a7f626157f59ee9d` /
  `run_1ddd17283cb2467494734d2bb3577ed8`
- dashboard watch promoted the benchmark run to `stage=capture` while the
  request span was still open
- the web overview, access, sessions, and replay pages all rendered the same
  live `session_id` / `run_id` and displayed friendly next-step guidance such
  as `先等待运行闭合，或在回放里定位 open span`

Issues found:

- local repo preparation could fail on `git fetch` timeout when GitHub was slow

Fix:

- added a generic archive-download fallback to
  [`benchmarks/swebench_lite/prepare_local_instance.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/prepare_local_instance.py)
  so local testbed preparation can fall back to GitHub `codeload` tarballs
  without adding any benchmark-specific logic to ClawGraph itself

## P2.1. Judge + review queue automation

Status: completed

Work:

- added `clawgraph inspect workflow` so one run can be checked without going
  through the full dashboard snapshot
- added `clawgraph judge annotate` with `heuristic` and
  `openai-compatible` providers
- added `preview_slice_review_queue(...)` and `clawgraph feedback sync`
- kept human override on the existing generic path:
  `artifact append --supersedes-artifact-id ...`

Issues found:

- phase-2 workflow logic only lived inside dashboard aggregation and was not
  callable from CLI automation
- low-confidence review reasons could diverge between dashboard and curation
- feedback queue sync needed duplicate protection when the same run was judged
  more than once

Fix:

- exposed the shared run workflow row from
  [`src/clawgraph/dashboard.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/dashboard.py)
- added generic judge planning in
  [`src/clawgraph/judge.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/judge.py)
- deduplicated review reasons at curation time and deduplicated feedback items
  at queue-sync time
- added regression coverage in
  [`tests/test_phase2.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/tests/test_phase2.py)

## P2-live. Real judge -> slice -> feedback -> dashboard loop

Status: completed

Work:

- reused the live store `/tmp/clawgraph-live-phase2.db`
- ran a real DeepSeek-backed `clawgraph judge annotate` on the closed smoke run
- registered one generic slice for captured proxy runs
- synced review items into the feedback queue
- rechecked `inspect workflow` and `inspect dashboard`

Evidence:

- persisted judge artifact:
  `art_8f51519336204531b5b2128902861f6c`
- feedback queue item:
  `fb_f0224cbf46c34e179744071fb4d3b0f8`
- run `run_9333a326446b4b59813ff0bf0c7a2228` moved from `annotate` to
  `review`
- dashboard overview changed to:
  `e1_ready_runs=1`, `export_ready_runs=1`, `feedback_queue_open=1`
- workflow overview changed to:
  `needs_review_runs=1`

Issues found:

- feedback sync was first attempted before the slice registration write had
  completed

Fix:

- reran queue sync after the slice registration persisted; no framework change
  was needed

## P2.2. Human override and feedback closure

Status: completed

Work:

- added `clawgraph judge override`
- added `clawgraph feedback resolve`
- changed workflow/read-model logic so only queued feedback blocks a run
- exposed human-reviewed runs as `review_status=human`

Issues found:

- resolved feedback items were still being counted as open review pressure
- there was no operator-friendly way to supersede a judge result and close the
  corresponding feedback loop

Fix:

- added generic feedback status updates in
  [`src/clawgraph/store/sqlite_store.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/store/sqlite_store.py)
- added manual override planning in
  [`src/clawgraph/judge.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/judge.py)
- updated dashboard/web copy to distinguish automated review from human
  confirmation

## P2-local. Terminal-only override flow

Status: completed

Work:

- bootstrapped a local demo store at `/tmp/clawgraph-phase2-override.db`
- registered a generic slice and enqueued one feedback item
- confirmed `inspect workflow` reported `stage=review`
- ran `judge override --feedback-status resolved`
- confirmed `inspect workflow` reported `stage=dataset` and
  `review_status=human`

Evidence:

- source annotation superseded:
  `art_c731173c524745f89d275f61673cbf9b`
- manual override annotation:
  `art_504ea3f4901f4e91a137113ec99dfe15`
- resolved feedback item:
  `fb_0647a6f0cc8641008e70579de2a92919`

## P2-final. Full live phase-2 automation and benchmark ingress

Status: completed

Work:

- added generic trajectory preparation and cleaning in
  [`src/clawgraph/prepare.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/prepare.py)
- added generic redaction helpers in
  [`src/clawgraph/redaction.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/redaction.py)
- added a reusable phase-2 orchestrator in
  [`src/clawgraph/phase2.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/phase2.py)
- added `clawgraph phase2 run` and `clawgraph eval ...` CLI entry points
- added the reusable live validation script
  [`benchmarks/swebench_lite/run_phase2_live_validation.sh`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/run_phase2_live_validation.sh)
- rewrote the web wording from engineering jargon toward
  `数据准备 -> 人工复核 -> 数据筛选 -> 导出与评测`

Issues found:

- the original `resolve_e1_annotation_for_run(...)` path could merge non-E1
  artifacts and make `phase2 run` fail with
  `task_family is required to build the phase2 slice`
- live environments may already have a running proxy, so validation cannot
  assume it always owns proxy startup
- mini-SWE-agent needs a longer observation window than a simple smoke request
  before the first benchmark LLM calls appear

Fix:

- filtered `resolve_e1_annotation_for_run(...)` down to active E1 annotations
- made `phase2 run` build slices only when all required E1 fields are present
- extended the live validation script so it can either start a fresh proxy or
  reuse an existing live proxy and store

Evidence:

- final live store:
  `/tmp/clawgraph-phase2-final-live.db`
- final phase-2 slice:
  `slice.captured_agent_task.generic_proxy_capture.7513daa2`
- training cohort:
  `cohort_b3ac60f7d61549dd9c39b57684ee5db2`
- evaluation cohort:
  `cohort_4e9f9996c32843c18680c63a29d7a09c`
- eval suite:
  `eval_11063756a6894d3f88f65f43076b99f3`
- scorecard verdict:
  `pass`
- promotion decision:
  `promote`
- final live artifacts:
  `/tmp/clawgraph-phase2-existing-report`
- dashboard snapshot after live run:
  `captured_sessions=5`, `captured_runs=5`, `e1_ready_runs=2`,
  `export_ready_runs=2`, `dataset_snapshots=3`, `active_eval_suites=1`,
  `scorecards_pass=1`
- mini-SWE-agent ingress confirmed on live run:
  `sess_8021a8a3c45145b7a285692552e20fbf` /
  `run_20e905d5381d4810b26d14fd0b3713b8`
- live run captured repeated `/chat/completions` requests whose first prompt
  line was:
  `You are a helpful assistant that can interact with a computer shell...`

## P2-collection. Long-running proxy + dashboard + mini benchmark collection

Status: completed

Work:

- started a live proxy against DeepSeek with store
  `/tmp/clawgraph-benchmark-collection.db`
- started the web dashboard against the same store on `http://127.0.0.1:3402`
- ran
  [`benchmarks/swebench_lite/run_benchmark_collection.sh`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/run_benchmark_collection.sh)
  for two real `SWE-bench Lite` instances:
  `sqlfluff__sqlfluff-1625` and `sqlfluff__sqlfluff-2419`
- let the collector enrich each finished run through the generic artifact path
- let the collector run `clawgraph phase2 run` per run and once more at slice
  scope
- verified the dashboard and CLI both reflected the same two real sessions and
  two real runs while the second run was still in progress and again after it
  closed

Issues found:

- `mini-SWE-agent` still performed a remote HuggingFace metadata probe even
  when `SWE-Bench Lite` was already cached locally, which delayed first-run
  startup
- the second local testbed hit a transient GitHub `git fetch` HTTP2 failure
- the dashboard still exposed some internal terms such as `身份覆盖`,
  `语义覆盖`, `Builder`, and `Open`

Fix:

- updated the collection helper to auto-detect a cached local
  `SWE-Bench Lite` dataset and switch to offline-cache mode
- reused the existing archive-download fallback in
  [`benchmarks/swebench_lite/prepare_local_instance.py`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/prepare_local_instance.py)
  so the second testbed still completed after the GitHub fetch failure
- updated the user-facing dashboard wording in
  [`web/src/app/page.tsx`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/app/page.tsx),
  [`web/src/app/access/page.tsx`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/app/access/page.tsx),
  [`web/src/components/dashboard/session-inbox-workspace.tsx`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/components/dashboard/session-inbox-workspace.tsx),
  and
  [`web/src/components/dashboard/workflow-board.tsx`](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/components/dashboard/workflow-board.tsx)
  to use friendlier labels such as `请求归属清晰度`,
  `任务识别清晰度`, `未闭合`, and `可导出数据类型`

Evidence:

- final collection summary:
  `/tmp/clawgraph-benchmark-collection-out/summary.md`
- final collection store:
  `/tmp/clawgraph-benchmark-collection.db`
- dashboard after collection:
  `captured_sessions=2`, `captured_runs=2`, `e1_ready_runs=2`,
  `export_ready_runs=2`, `dataset_snapshots=3`, `active_eval_suites=1`
- real benchmark sessions/runs:
  `sess_7fb142ed9eab434988c25f9780e33e76` /
  `run_68e6a78fd0ce4482b8ae9a540fb2d731`
  and
  `sess_708bdf7708484874a16a1091f95f7fbe` /
  `run_bb5fdd532adb4d469ea96322b4463194`
- per-run SFT exports:
  `30` records for `sqlfluff__sqlfluff-1625`
  and `45` records for `sqlfluff__sqlfluff-2419`
- final slice:
  `slice.benchmark_coding_task.swebench_issue_fix.e9fd9678`
- final training cohort:
  `cohort_3a198cd33b434595876df24a4ba63abd`
- final evaluation cohort:
  `cohort_3d5d11e75b1c41b38b98326b84ad0a88`
- final evaluation suite:
  `eval_a38e9e1a0a014377a281166405062430`
- final slice-level SFT export:
  `/tmp/clawgraph-benchmark-collection-out/phase2/final-slice/cohort_3a198cd33b434595876df24a4ba63abd.sft.jsonl`
  with `30` records

Note:

- the final slice-level training export contains `30` records rather than
  `75`, because slice-scope freezing used `holdout_fraction=0.34` with
  `max_members_per_task_instance=1`
- the second benchmark run was intentionally routed into the holdout/evaluation
  cohort, not dropped
