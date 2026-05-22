# Handwriting Sample — OCR Smoke Test Baseline

Reference payload for the live-vision-model smoke test in plan
`2026-04-27-ocr-protocol-ollama-9b`, cycle 9b-5
(`tests/v3/extraction/test_ollama_backend_integration.py`,
`pytest.mark.integration`).

The smoke test asserts only **structural shape** — that
`OllamaBackend.extract(<photo>)` returns an `ExtractionResult` with at
least one `FieldExtraction`, and that the live model's raw JSON output
emits the `reasoning` key first (the integration-level pin for spec
§7.4). It does **not** validate per-field accuracy. Per-field accuracy
is the empirical-model-selection chore's domain (chore index 13 —
`2026-04-27-empirical-vision-model-selection`).

This baseline is a single-writer single-payload smoke fixture, not a
representative corpus. Realistic handwriting variability across firm
clients is gathered separately under chore 13.

## Instructions for the writer

Hand-write the **same payload** (the block in §"Sample payload" below)
once per technique listed. Use a blank lined or unlined sheet —
whichever feels natural. Photograph in good light, the whole sheet in
frame, roughly flat-on (oblique angles degrade OCR quality more than
they need to for a baseline).

Save each photo with the filename listed, in this directory
(`assets/handwriting-samples/`):

| Filename       | Technique                      | Remarks                                       |
| ---------------| ------------------------------ | --------------------------------------------- |
| `print.jpg`    | Neat block printing            | - Does not preserve aligned value spacing     |
| `cursive.jpg`  | Cursive                        | - Has the order of beneficiaries swapped      |
| `hurried.jpg`  | Deliberately rushed / scrawled | n/a                                           |
| `all-caps.jpg` | ALL CAPS                       | - Does not preserve address section spacing   |

## Sample payload

Write each line verbatim, including the punctuation| and spacing.
Suffix, hyphen, apostrophe, comma, dollar sign, and period are
deliberate — they exercise §8.1 verbatim-transcription discipline
(no normalization in `raw_value`).

```yaml
Grantor 1 full legal name:    James William Thompson, Jr.
Grantor 1 date of birth:      March 15, 1958

Grantor 2 full legal name:    Mary-Beth O'Brien
Grantor 2 date of birth:      11/08/1960

Trust street address:         1428 Elm Street
Trust city, state, zip:       Springfield, OH 45503

Beneficiary 1 name:           Sarah Lin Thompson
Beneficiary 1 relationship:   daughter
Beneficiary 1 share %:        50

Beneficiary 2 name:           Michael Thompson
Beneficiary 2 relationship:   son
Beneficiary 2 share %:        50

Real property value:          $250,000.00
Personal property value:      $35,500.00
Successor trustee:            Eleanor Vance
```

## Why these particular values

- **Names with suffix, hyphen, apostrophe** — Thompson, Jr.;
  Mary-Beth; O'Brien — pin §8.1 "verbatim transcription, no
  normalization" against the model's tendency to regularize.
- **Two date formats** (long-form and slash-form) on consecutive
  fields — exercise raw-value preservation across writer-convention
  drift on the same sheet.
- **Currency with thousands separator and decimal** — `$250,000.00`,
  `$35,500.00` — pin punctuation transcription. The model should not
  silently drop the `$` or the trailing `.00`.
- **Relationship vocabulary** — `daughter`, `son` — align with
  `relationship_enum_design` (spec §3.1). Cycle 9b-3's mocked happy
  path will exercise the enum mapping; this fixture does the same
  shape under live conditions.
- **Two share percentages summing to 100** — coincides with the
  existing `shares.sum_not_100` SCHEMA rule (plan 8, closed). A
  follow-up end-to-end smoke can pipe extraction → `diagnose()` to
  confirm no false-positive emission on this sample. (Out of scope
  for 9b — this is a 9c integration concern.)
