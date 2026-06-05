# Roadmap

## Strategy

Build a narrow, provable product first. Expand only after the reusable data contracts, scoring, rule assets, and reports work.

## Phase 0: Product Contracts

Status: current.

Deliverables:

- MVP PRD.
- Architecture.
- DocumentIR spec.
- Quality score model.
- Rule engine spec.
- RAG evaluation plan.
- Dataset card and acceptance report templates.

Exit criteria:

- Team can implement CLI pipeline without redefining product scope.
- Every report claim has a backing data contract.

## Phase 1: CLI Prototype

Target:

```text
Import -> Parse -> DocumentIR -> Clean -> Chunk -> Score -> Export -> Report
```

Deliverables:

- CLI command.
- Filesystem dataset workspace.
- One PDF parser adapter.
- Markdown and HTML adapters.
- Generic noise cleanup rules.
- JSONL export package.
- Quality report generation.
- Regression fixtures.

Exit criteria:

- Process at least 20 benchmark documents end to end.
- Generate dataset package and reports for every run.
- Preserve source mapping for at least 95% of chunks.

## Phase 2: Benchmark And PoC Hardening

Deliverables:

- 100-200 document benchmark set.
- Manual gold labels for noise and chunk quality.
- Parser comparison harness.
- Review queue data model.
- Sensitive detection policy.
- RAG retrieval evaluation.

Exit criteria:

- Noise cleanup precision >= 85% on gold set.
- Chunk quality pass rate >= 80%.
- Acceptance report can support a customer PoC.

## Phase 3: Lightweight Web Console

Deliverables:

- Dataset project list.
- Upload and processing status.
- Quality dashboard.
- Review queue.
- Report viewer.
- Export download.

Exit criteria:

- Non-engineer can run a dataset through the workflow.
- Review actions generate trace events.

## Phase 4: Industry Pack

Initial candidate:

- Legal contract documents, or
- Manufacturing knowledge-base documents.

Deliverables:

- Industry rules.
- Industry scoring thresholds.
- Report template variants.
- Demo dataset.
- RAG question templates.

Exit criteria:

- One repeatable paid PoC package.

## Deferred Platform Work

- Structured database quality.
- Standard compliance center.
- Data exchange APIs.
- Full annotation platform.
- Dataset lifecycle operations.
- Agent CleanOps.
