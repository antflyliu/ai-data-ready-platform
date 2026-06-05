# Quality Score Model

## Purpose

Quality scores must explain whether a cleaned dataset is ready for RAG. Scores are not cosmetic; each score must map to metrics and evidence.

## Score Layers

```text
Dataset Readiness Score
├── Parse Quality
├── Noise Control
├── Chunk Quality
├── Source Traceability
├── Safety Risk
└── RAG Evaluation
```

## MVP Metrics

| Layer | Metric | Direction |
|---|---|---|
| Parse Quality | parse completion rate | higher is better |
| Parse Quality | parse warning rate | lower is better |
| Parse Quality | table extraction confidence | higher is better |
| Noise Control | repeated header/footer hit rate | evidence metric |
| Noise Control | residual noise rate | lower is better |
| Chunk Quality | chunk length pass rate | higher is better |
| Chunk Quality | title-path coverage | higher is better |
| Chunk Quality | cross-page break risk | lower is better |
| Source Traceability | chunk-source mapping rate | higher is better |
| Source Traceability | page/bbox retention rate | higher is better |
| Safety Risk | sensitive hit count | risk metric |
| Safety Risk | unresolved sensitive hit count | lower is better |
| RAG Evaluation | top-k retrieval hit rate | higher is better |
| RAG Evaluation | citation accuracy | higher is better |

## Default Weights

MVP default:

| Layer | Weight |
|---|---:|
| Parse Quality | 20 |
| Noise Control | 20 |
| Chunk Quality | 25 |
| Source Traceability | 20 |
| Safety Risk | 10 |
| RAG Evaluation | 5 |

RAG Evaluation has a low default weight because it requires a customer question set. When a question set exists, increase RAG Evaluation to 20 and reduce other weights proportionally.

## Score Evidence

Every score must support drill-down:

```text
score -> metric -> failed records -> rule or detector -> source document -> element or chunk
```

## Pass/Fail Thresholds

MVP default thresholds:

| Score | Meaning |
|---:|---|
| >= 85 | Ready for pilot RAG ingestion |
| 70-84 | Usable with review and remediation |
| 50-69 | Not ready; cleanup issues remain |
| < 50 | Parser or source quality failure |

## Report Requirements

Quality reports must include:

- Before and after scores.
- Metric table.
- Top issues by severity.
- Evidence samples.
- Unresolved review items.
- Recommended remediation.
- Known limitations.
