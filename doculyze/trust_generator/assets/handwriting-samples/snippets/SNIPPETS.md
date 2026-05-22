# Handwriting Snippet Corpus — Atomic OCR Fixtures

Single-purpose fixtures for the empirical vision-model selection exercise
(chore index 13 — `2026-04-27-empirical-vision-model-selection`).

Sibling to `../pages/` (full-payload narrative fixtures, `BASELINE.md`).
The two directories live in different test layers:

| Directory | Fixture form | Test layer | Oracle requirement |
| --------- | ------------ | ---------- | ------------------ |
| `pages/`  | Full-payload narrative | Smoke-shape (cycle 9b-5) + chore-13 narrative scoring | Paralegal-truth + structural |
| `snippets/` | Single-purpose atomic | Chore-13 automated assertions + qualitative scoring | Mixed (see per-fixture row below) |

The smoke test in plan 9b cycle 9b-5 reads ONE photo path via
`OCR_SMOKE_FIXTURE_PATH` and defaults to `../pages/print.jpg`. None of
the snippet fixtures here are smoke-test inputs; they are evaluation
fixtures for the chore-13 exercise.

## Per-fixture ground truth and assertion-cleanliness

### `punctuation-stress.jpg`

Tests §8.1 verbatim punctuation preservation. Six lines, every
punctuation decision is unambiguous at the stroke level.

| Line | Expected `raw_value` | Cleanly assertable |
| ---- | -------------------- | ------------------ |
| 1    | `John Smith, Jr.`     | Yes — comma, period, suffix preserved |
| 2    | `Mary-Beth O'Brien`   | Yes — hyphen, apostrophe preserved |
| 3    | `$250,000.00`         | Yes — `$`, thousands separator, trailing `.00` |
| 4    | `$35,500`             | Yes — `$`, thousands separator, no trailing decimal |
| 5    | `1500.50`             | Yes — no `$`, decimal preserved |
| 6    | `$99.5`               | Yes — `$`, single-decimal place (not normalized to `.50`) |

**Oracle:** none required for character-level assertion (the strokes
are unambiguous).

**Failure mode this catches:** model normalizes `$99.5 → $99.50`,
strips `.00` from `$250,000.00`, drops the `$` sign, or replaces the
suffix-comma with a different separator.

### `absent-fields.jpg`

Tests §8.3 omit-if-absent guardrail. Four lines, two with values, two
with blank value-side.

| Line | Source | Expected behavior |
| ---- | ------ | ------------------ |
| 1    | `Beneficiary 1 name:`            | NO `FieldExtraction` emitted (blank value) |
| 2    | `Beneficiary 1 share %: 50`      | `FieldExtraction(raw_value="50")` |
| 3    | `Beneficiary 2 name: Michael Thompson` | `FieldExtraction(raw_value="Michael Thompson")` |
| 4    | `Beneficiary 2 share %:`         | NO `FieldExtraction` emitted (blank value) |

**Asserted property:** `len(trace.fields) == 2`, with `raw_value`
values `{"50", "Michael Thompson"}`.

**Oracle:** none required — absence of writing is observable from the
photo alone. This is the only fixture in the corpus whose ground truth
is verifiable without paralegal-truth.

**Failure mode this catches:** model invents values for blank lines
("hallucination on absent fields"), or emits `FieldExtraction` entries
with `raw_value=""` rather than omitting.

### `illegibility-stress.jpg`

Tests §8.1 illegibility-as-first-class. Three fields, three distinct
illegibility regimes.

| Field | Source | Expected behavior | Assertion-clean? |
| ----- | ------ | ----------------- | ---------------- |
| A     | Heavy scribble obscuring any value | `illegible=True` | Yes |
| B     | `Sarah Lin Thompson`               | `illegible=False, raw_value="Sarah Lin Thompson"` | Yes |
| C     | `sixty-four` struck through, `^sixty-five` carat-inserted below | **Judgment-call** — see note | **No** |

**Note on Field C — the proofreader-correction pattern.**

This fixture intentionally probes a gap in the spec's prompt strategy.
Three behaviors are all defensible under §8.1:

1. **Strict verbatim:** `raw_value="sixty-four (struck through, replaced by sixty-five)"`
2. **Pragmatic resolution:** `raw_value="sixty-five"` plus a `note`
   channel referencing the strikethrough
3. **Naive concatenation:** `raw_value="sixty-four sixty-five"` (a
   failure mode)

The §8.1 prompt covers "multiple readings are plausible" but a
*correction* is not a plurality of readings — the spec text doesn't
quite cover this case. Field C's value is *diagnostic*, not assertable:
candidate-model convergence on (2) is evidence to harden the prompt;
divergence is evidence for a §8 spec amendment.

**Oracle:** paralegal-truth (you, marking which line is intentionally
illegible, and which is the corrected reading).

### `date-format-variance.jpg`

Tests §8.1 verbatim format preservation across writer-convention drift.
Four date renderings of the same conceptual date (March 15, 1958).

| Line | Expected `raw_value` |
| ---- | -------------------- |
| 1    | `3/15/58`            |
| 2    | `March 15, 1958`     |
| 3    | `15-Mar-1958`        |
| 4    | `1958-03-15`         |

**Asserted property:** each `raw_value` matches its source format
character-for-character; no normalization to a canonical form.

**Oracle:** paralegal-truth (you confirmed all four refer to the same
date), but format-preservation is observable from the strokes alone.

**Failure mode this catches:** model normalizes all four to a single
canonical form (`1958-03-15` or similar), or coerces partial-year
`58` to `1958` in line 1's `raw_value`.

### `label-on-line-N.jpg`

Tests field-association across line breaks. Two lines: a label on line N,
its value on line N+1.

| Line | Source |
| ---- | ------ |
| N    | `Grantor 1 Full Legal Name:` |
| N+1  | `James William Thompson, Jr.` |

**Asserted property:** trace contains exactly **1** `FieldExtraction`
with `raw_value="James William Thompson, Jr."` and `field_path` mapped
to grantor-1's full-legal-name slot. The model must associate the
label on line N with the value on line N+1, NOT emit two separate
fields (one with empty value, one with no associated label).

**Oracle:** paralegal-truth (you wrote it as one logical field).

**Failure mode this catches:** model treats blank line-N value as a
field (emitting `illegible=True` or `raw_value=""`) and emits a second
field for line N+1 with no `field_path` mapping.

## Fixture-fitness hierarchy

The corpus stratifies by oracle requirement. This stratification
matches the test-layer fitness needed for each fixture:

| Tier | Fixtures | Oracle | Test-layer fit |
| ---- | -------- | ------ | -------------- |
| 1    | `absent-fields.jpg` | None (absence is observable) | Automated tests with no human curation |
| 2    | `punctuation-stress.jpg`, `date-format-variance.jpg` | Paralegal-truth, but strokes are unambiguous | Paralegal-curated harness, character-equality assertions |
| 3    | `illegibility-stress.jpg` Field C | Paralegal-truth + spec-interpretation judgment | Qualitative scoring, spec-amendment evidence-gathering |
| 2/3  | `illegibility-stress.jpg` Fields A/B, `label-on-line-N.jpg` | Paralegal-truth (binary observable) | Paralegal-curated harness, boolean / structural assertions |

Tier 1 fixtures can run unattended in CI; tier 2 requires the harness
to know paralegal-truth; tier 3 requires human scoring.

## Repo hygiene

EXIF/GPS metadata stripped from all photos in this directory. If new
photos are added, run before commit:

```bash
exiftool -all= -overwrite_original assets/handwriting-samples/snippets/*.jpg
exiftool -gps:all assets/handwriting-samples/snippets/*.jpg   # verify empty
```

## Not in scope for this corpus

- The pages-form narrative fixtures (live in `../pages/`)
- Per-firm representative handwriting variability beyond this single
  writer (a future expansion of chore #13 if the single-writer corpus
  proves insufficient for production-class evaluation)
- PHI-bearing real intakes — these never enter the repo
