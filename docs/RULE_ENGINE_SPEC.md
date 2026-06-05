# Rule Engine Specification

## Purpose

Rules turn cleanup behavior into versioned assets. The product should avoid one-off cleanup scripts that cannot be explained, reused, or audited.

## Rule Shape

```yaml
id: remove_repeated_header
version: 1
name: Remove repeated page header
scope: element
enabled: true
condition:
  all:
    - field: type
      op: in
      value: [header, footer, page_number]
    - field: repeated_across_pages_ratio
      op: gte
      value: 0.6
action:
  type: exclude_from_export
  reason: repeated_page_noise
confidence:
  default: 0.9
review:
  required_when_confidence_lt: 0.8
```

## MVP Rule Categories

| Category | Examples |
|---|---|
| Structural noise | header, footer, page number, watermark |
| Repetition | repeated paragraph, duplicated disclaimers |
| Chunk quality | too short, too long, broken heading context |
| Sensitive content | phone, email, ID-like values, configured keywords |
| Export projection | include, exclude, mask, flag |

## Rule Actions

MVP actions:

```text
exclude_from_export
mark_as_noise
mask_text
flag_for_review
set_metadata
```

Rules must not mutate raw source files.

## Rule Event Contract

Each rule application creates a cleaning event with:

- `rule_id`.
- `rule_version`.
- target record id.
- action.
- before and after snapshot.
- confidence.
- review status.
- reason.

## Review Statuses

```text
auto_accepted
needs_review
human_accepted
human_reverted
false_positive
```

## Industry Packs

Industry packs are collections of:

- Rules.
- Score thresholds.
- Sensitive keyword lists.
- Report wording.
- RAG evaluation question templates.

MVP should only implement the generic pack. Legal and manufacturing packs are later extensions.
