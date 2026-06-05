# Dataset Card Template

## Dataset Basic Information

- Dataset name:
- Dataset id:
- Version:
- Owner:
- Created at:
- Updated at:
- Intended use:
- Not intended for:

## Source Data

- Source systems or folders:
- Document types:
- Document count:
- Total pages:
- Source hash policy:
- Rights and ownership notes:

## Processing Pipeline

```text
Import -> Parse -> Clean -> Chunk -> Score -> Review -> Export
```

## Parser Information

- Parser adapters used:
- Parser versions:
- Fallback parser usage:
- Parse warning count:
- Known parser limitations:

## Cleaning Rules

| Rule | Version | Hits | Review Items |
|---|---:|---:|---:|
|  |  |  |  |

## Quality Summary

| Layer | Score | Notes |
|---|---:|---|
| Parse Quality |  |  |
| Noise Control |  |  |
| Chunk Quality |  |  |
| Source Traceability |  |  |
| Safety Risk |  |  |
| RAG Evaluation |  |  |

## Sensitive Information

- Total hits:
- Unresolved hits:
- Masking policy:
- Accepted risks:

## RAG Readiness

- Chunk count:
- Average chunk length:
- Chunk quality pass rate:
- Citation mapping rate:
- Retrieval evaluation result:

## Limitations

- Unsupported formats:
- Low-confidence parsing zones:
- Known unresolved quality issues:
- Data freshness limitations:

## Export Package

- documents.jsonl:
- elements.jsonl:
- chunks.jsonl:
- cleaning_events.jsonl:
- quality_report:
- acceptance_report:
