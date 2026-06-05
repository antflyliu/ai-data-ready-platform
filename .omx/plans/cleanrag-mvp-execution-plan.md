# CleanRAG MVP Execution Plan

## Requirements Summary

Build the first product as **CleanRAG**, a RAG document dataset readiness tool. The first implementation should prove the core pipeline before a full web platform:

```text
Import -> Parse -> DocumentIR -> Clean -> Chunk -> Score -> Export -> Report
```

Primary users are RAG integrators, enterprise knowledge-base owners, and solution architects who need clean, traceable, quality-scored document datasets.

## Decision

Start with a CLI prototype and filesystem-backed artifacts. Do not start with a broad SaaS platform or full data governance system.

## Principles

- Keep the MVP narrow: RAG document readiness only.
- Preserve traceability from every chunk back to source elements.
- Treat rules and reports as product assets.
- Keep raw source files immutable.
- Design parser adapters so the platform is not coupled to one parser.

## Decision Drivers

1. Fastest path to a paid PoC.
2. Reusable core for later platform expansion.
3. Evidence-backed quality improvement instead of vague cleanup claims.

## Alternatives Considered

| Option | Result | Reason |
|---|---|---|
| Build full AI Data Readiness Platform first | Rejected | Too broad; high delivery risk before validating customer value. |
| Build only a PDF parser wrapper | Rejected | Too easy to replace; does not capture quality scoring, traceability, and reporting value. |
| Build CLI prototype first | Chosen | Fastest way to validate data contracts, reports, and benchmark quality. |

## Implementation Steps

### Step 1: Contracts and Docs

Files:

- `README.md`
- `docs/PRD-CleanRAG-MVP.md`
- `docs/ARCHITECTURE.md`
- `docs/DOCUMENT_IR.md`
- `docs/QUALITY_SCORE_MODEL.md`
- `docs/RULE_ENGINE_SPEC.md`
- `docs/RAG_EVALUATION_PLAN.md`
- `docs/DATASET_CARD_TEMPLATE.md`
- `docs/ACCEPTANCE_REPORT_TEMPLATE.md`
- `docs/ROADMAP.md`

Acceptance criteria:

- MVP scope is explicit.
- Deferred capabilities are explicit.
- Data contracts exist for DocumentIR, rules, scores, exports, and reports.

### Step 2: CLI Skeleton

Create a Python package and CLI entrypoint.

Suggested commands:

```text
cleanrag init <dataset>
cleanrag import <input_dir>
cleanrag parse
cleanrag clean
cleanrag chunk
cleanrag score
cleanrag export
cleanrag report
cleanrag run <input_dir> --out <output_dir>
```

Acceptance criteria:

- CLI can create a dataset workspace.
- CLI can process Markdown and HTML with no external parser dependency.
- PDF adapter can be stubbed or implemented with the first available local parser.

### Step 3: DocumentIR Implementation

Implement typed models and JSONL persistence.

Acceptance criteria:

- Documents, pages, elements, chunks, cleaning events, and reports serialize predictably.
- Source hashes are stored.
- Every chunk references source element ids.

### Step 4: Rule Engine And Cleanup

Implement generic noise rules:

- repeated header/footer.
- page number.
- watermark-like repeated text.
- duplicate paragraph.

Acceptance criteria:

- Every rule hit creates a cleaning event.
- Cleaning does not mutate raw source records.
- Export excludes records through a cleaned projection.

### Step 5: Chunking And Scoring

Implement chunk generation and MVP quality metrics.

Acceptance criteria:

- Chunk length thresholds are configurable.
- Title path and page range are preserved where available.
- Dataset score can be traced to metrics and failed records.

### Step 6: Export And Reports

Generate:

- `documents.jsonl`
- `elements.jsonl`
- `chunks.jsonl`
- `cleaning_events.jsonl`
- `quality_report.json`
- `quality_report.md`
- `dataset_card.md`
- `acceptance_report.md`

Acceptance criteria:

- Every run produces a complete output package.
- Reports include before/after counts, score summary, traceability summary, and risks.

### Step 7: Benchmark And Tests

Create small fixtures and regression tests.

Acceptance criteria:

- Markdown and HTML fixture tests pass.
- Rule engine tests cover include/exclude/mask/flag actions.
- Report generation tests produce stable outputs.
- Source traceability is asserted.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Parser performance varies by document type | Use adapter contract and parser benchmark records. |
| Quality score is not trusted | Make every score drill down to concrete metrics and evidence. |
| Scope drifts into full governance | Keep database quality, full compliance center, and Agent CleanOps deferred. |
| Reports become marketing text | Generate reports from stored events and metrics only. |

## Verification Steps

Run after implementation:

```text
python -m pytest
cleanrag run <fixture_dir> --out <tmp_output>
```

Verify:

- Output package exists.
- Every chunk has source mapping.
- Cleaning events link to rules.
- Reports render without missing sections.

## ADR

Decision: Implement CleanRAG as a CLI-first RAG document readiness MVP.

Drivers: fastest PoC path, reusable core, evidence-backed quality claims.

Alternatives considered: full platform first, parser wrapper only, CLI-first core.

Why chosen: CLI-first keeps scope small while proving the contracts needed for future platformization.

Consequences: Web UI and compliance center are delayed, but core contracts become stronger.

Follow-ups: implement CLI skeleton, fixtures, typed models, rule engine, scoring, and reports.
