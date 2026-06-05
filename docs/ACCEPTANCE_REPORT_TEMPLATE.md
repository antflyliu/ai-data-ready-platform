# Acceptance Report Template

## 1. Project Summary

- Customer:
- Dataset:
- Version:
- Processing date:
- Intended RAG application:

## 2. Executive Result

```text
Before quality score:
After quality score:
Readiness verdict:
Main improvement:
Remaining risk:
```

## 3. Source Data Scope

| Item | Count |
|---|---:|
| Documents |  |
| Pages |  |
| Parsed elements |  |
| Generated chunks |  |

## 4. Processing Pipeline

```text
Import -> Parse -> Clean -> Chunk -> Score -> Review -> Export
```

## 5. Cleaning Results

| Cleaning Type | Hits | Auto Accepted | Needs Review | Reverted |
|---|---:|---:|---:|---:|
| Header/footer |  |  |  |  |
| Page number |  |  |  |  |
| Watermark |  |  |  |  |
| Repeated paragraph |  |  |  |  |
| Sensitive information |  |  |  |  |

## 6. Quality Evaluation

| Layer | Before | After | Delta |
|---|---:|---:|---:|
| Parse Quality |  |  |  |
| Noise Control |  |  |  |
| Chunk Quality |  |  |  |
| Source Traceability |  |  |  |
| Safety Risk |  |  |  |
| RAG Evaluation |  |  |  |

## 7. RAG Evaluation

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Top-k hit rate |  |  |  |
| Citation mapping rate |  |  |  |
| Noise chunk rate |  |  |  |
| Low-quality chunk rate |  |  |  |

## 8. Traceability

- Source hash policy:
- Cleaning event count:
- Chunks with source mapping:
- Page/bbox coverage:
- Reversible actions:

## 9. Risks And Limitations

- Low-confidence parser zones:
- Unresolved sensitive hits:
- Unsupported document types:
- Customer review requirements:

## 10. Acceptance Recommendation

```text
Recommended verdict: accepted / accepted with remediation / not accepted
Required remediation:
Next dataset version:
```
