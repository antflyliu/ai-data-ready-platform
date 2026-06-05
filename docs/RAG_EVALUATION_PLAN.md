# RAG Evaluation Plan

## Purpose

The product must prove that cleaning improves RAG readiness. Evaluation should be repeatable and evidence-backed.

## Evaluation Inputs

Each dataset can define a question set:

```json
{
  "question_id": "q_001",
  "question": "How do I reset the device after an alarm?",
  "expected_document_ids": ["doc_010"],
  "expected_title_keywords": ["Reset", "Alarm"],
  "expected_answer_notes": "Should cite the reset procedure section.",
  "must_not_answer": false
}
```

## MVP Evaluation Modes

### Retrieval-Only

No LLM required.

Metrics:

- Top-k retrieval hit rate.
- Expected source coverage.
- Irrelevant chunk rate.
- Duplicate chunk rate.

### Citation Sanity

Checks whether retrieved chunks have valid source mapping.

Metrics:

- chunk-source mapping rate.
- page retention rate.
- bbox retention rate.
- broken citation count.

### Optional Answer Evaluation

LLM-based evaluation is optional and disabled by default for private deployments.

Metrics:

- answer support rate.
- citation accuracy.
- unsupported claim count.

## Before/After Comparison

Reports should compare:

```text
raw parsed chunks
vs
cleaned and scored chunks
```

Required comparison:

- Retrieval hit rate delta.
- Noise chunk rate delta.
- Duplicate chunk rate delta.
- Low-quality chunk rate delta.
- Citation mapping delta.

## Acceptance Criteria

For a paid PoC, the dataset should meet at least:

- Top-5 retrieval hit rate improves or remains above customer baseline.
- Low-quality chunk rate decreases.
- Noise chunk rate decreases.
- Citation mapping rate is at least 95%.
- Unresolved sensitive hits are reviewed or explicitly accepted as known risk.
