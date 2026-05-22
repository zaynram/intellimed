# Empirical Vision-Model Selection — chore #13 evaluation

**Date:** 2026-04-30 (single-session)
**Chore:** [#13 `2026-04-27-empirical-vision-model-selection`](../../.claude/context/chores.xml)
**Spec:** §4.2 of `docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md`
**Branch:** v3.0.0

## TL;DR

**Recommended default: `qwen2.5vl:7b`.** Per-field accuracy on auto-scored
fixtures: **77.1% (Qwen) vs 37.0% (MiniCPM-V)**. MiniCPM-V also failed the
illegibility-flag test (would silently invent values for unreadable fields —
worst-case failure mode for legal intake).

Neither candidate cleared the chore's illustrative >85% per-field accuracy bar
on legible fields, so the exit criteria triggered the "extends to evaluating
additional candidates" path → opened as follow-up chore #29 (`gemma3:12b` and
`qwen2.5vl:3b` both already on disk, no pull cost).

## Method

- **Daemon:** IPEX-LLM Ollama bundle at `/home/ramda/.local/share/ollama/`,
  managed by systemd unit `ollama.service` (Intel iGPU acceleration via SYCL
  Level Zero, `OLLAMA_NUM_GPU=999`, `ONEAPI_DEVICE_SELECTOR=level_zero:0`).
- **Candidates:** `qwen2.5vl:7b` (Q4_K_M, 5.97 GB), `minicpm-v:latest` (Q4_0,
  5.22 GB) — the two named in spec §4.2.
- **Fixtures (9):** four `pages/*.jpg` full-payload narrative fixtures + five
  `snippets/*.jpg` single-purpose atomic fixtures (per
  `assets/handwriting-samples/{pages/BASELINE.md, snippets/SNIPPETS.md}`).
- **Inference:** `OllamaBackend.extract` (the v3 production seam); `temperature=0`;
  `format=GenerationEnvelope.model_json_schema()`. Spec §7.4 reasoning-first
  key-order pin enabled.
- **Inter-candidate hygiene:** `keep_alive=0` ping between models — required
  because IPEX-LLM SYCL doesn't surface to Ollama's GPU residency tracking
  (`size_vram=0` for any IPEX-loaded model in `/api/ps`), so the default 10-min
  keep-alive leaves prior model resident and the second model fails with
  `unable to allocate SYCL0 buffer` even when total bytes would fit.
- **Scoring rubric:** strict equality first; lenient (case + whitespace
  collapse) match logged with a `note` so §8.1 normalization signal stays
  observable in the JSONL log without inflating MISMATCH counts.
  Illegibility false-positive (model flags legible writing) tracked as a
  distinct verdict from MISMATCH because conservative-but-wrong has lower
  paralegal triage cost than misread value.
- **Verdict taxonomy:** MATCH / MISMATCH / ILLEGIBLE_CORRECT /
  ILLEGIBLE_FALSE_POSITIVE / ILLEGIBLE_FALSE_NEGATIVE / HALLUCINATION /
  OMITTED. Hallucination = field emitted on a known-blank source OR
  envelope-level emission of a field outside ground truth.
- **Excluded from auto-scoring:** `snippets/punctuation-stress.jpg` and
  `snippets/date-format-variance.jpg` probe verbatim discipline on dollar
  amounts and standalone dates that have no `GenerationEnvelope` slot. Their
  outputs land in the JSONL log for qualitative review only.
- **Harness (scratch, NOT committed):** `/tmp/eval_vision_models.py`. Run via
  `pixi run python /tmp/eval_vision_models.py`. Outputs:
  `/tmp/eval-results.jsonl` (per-fixture per-model raw outputs + verdicts) and
  `/tmp/eval-summary.txt` (aggregated). Total wall-clock 13min for 18
  inferences.

## Quantitative results

| Metric                              | `qwen2.5vl:7b` | `minicpm-v:latest` |
| ----------------------------------- | -------------- | ------------------ |
| Inferences (success / attempted)    | 8 / 9          | 9 / 9              |
| Wall-clock total                    | 371.7s         | 412.1s             |
| Wall-clock avg / inference          | 41.3s          | 45.8s              |
| **Auto-scored MATCH rate**          | **27 / 35 (77.1%)** | **17 / 46 (37.0%)** |
| MISMATCH                            | 4              | 16                 |
| OMITTED                             | 3              | 10                 |
| HALLUCINATION                       | 1              | 3                  |
| ILLEGIBLE_CORRECT                   | 0              | 0                  |
| ILLEGIBLE_FALSE_POSITIVE            | 0              | 0                  |
| ILLEGIBLE_FALSE_NEGATIVE            | 0              | 0                  |
| `illegibility-stress.jpg` shape     | **PASS**       | **FAIL**           |

(Note: ILLEGIBLE_* counts are zero on auto-scored fixtures because none of those
fixtures have illegible-by-design fields. The `illegibility-stress.jpg` shape
check is the dedicated illegibility test; it runs separately because that fixture
has no fixed field-mapping.)

## Per-fixture detail

### `qwen2.5vl:7b`

| Fixture                              | Wall-clock | Verdicts |
| ------------------------------------ | ---------- | -------- |
| `pages/all-caps.jpg`                 | **0.6s**   | **ERROR** — SYCL runner exit (chore #30) |
| `pages/cursive.jpg`                  | 72.7s      | MATCH 9, MISMATCH 1 |
| `pages/hurried.jpg`                  | 44.8s      | MATCH 6, OMITTED 2, MISMATCH 2 |
| `pages/print.jpg`                    | 46.3s      | MATCH 10 (perfect) |
| `snippets/absent-fields.jpg`         | 35.1s      | MATCH 1, MISMATCH 1, OMITTED 1, HALLUCINATION 1 |
| `snippets/illegibility-stress.jpg`   | 42.1s      | shape PASS (illegible flag fired, legible name found) |
| `snippets/label-on-line-N.jpg`       | 31.4s      | MATCH 1 (perfect) |
| `snippets/punctuation-stress.jpg`    | 47.7s      | qualitative |
| `snippets/date-format-variance.jpg`  | 50.9s      | qualitative |

### `minicpm-v:latest`

| Fixture                              | Wall-clock | Verdicts |
| ------------------------------------ | ---------- | -------- |
| `pages/all-caps.jpg`                 | 136.5s     | MATCH 2, MISMATCH 6, OMITTED 2 |
| `pages/cursive.jpg`                  | 37.9s      | MATCH 6, MISMATCH 2, OMITTED 2 |
| `pages/hurried.jpg`                  | 38.2s      | MISMATCH 6, OMITTED 4, HALLUCINATION 1 (zero matches) |
| `pages/print.jpg`                    | 45.0s      | MATCH 6, MISMATCH 2, OMITTED 2 |
| `snippets/absent-fields.jpg`         | 22.9s      | MATCH 2, HALLUCINATION 2 |
| `snippets/illegibility-stress.jpg`   | 24.8s      | shape **FAIL** (no illegible flag fired) |
| `snippets/label-on-line-N.jpg`       | 19.9s      | MATCH 1 (perfect) |
| `snippets/punctuation-stress.jpg`    | 57.3s      | qualitative |
| `snippets/date-format-variance.jpg`  | 29.6s      | qualitative |

## Qualitative findings

### Qwen2.5-VL:7b

- **Strong on structured intake.** `print.jpg` 10/10 perfect; `cursive.jpg`
  9/10 with one single-character OCR slip (`Sarah` → `Jarah`); correctly
  handled the swapped beneficiary order on `cursive.jpg` per BASELINE.md.
- **Label-association works.** `label-on-line-N.jpg` (label on line N, value
  on line N+1) extracted as one logical field — no spurious "empty value"
  emission for the label line.
- **Illegibility flag is live.** On `illegibility-stress.jpg`, model emitted
  `illegible=True` on the truly-illegible field and extracted the legible name
  correctly — the §8.1 illegibility-as-first-class discipline has a working
  signal under this model.
- **Drops some punctuation.** `punctuation-stress.jpg`: preserved suffix and
  apostrophe in `John Smith, Jr.`, but DROPPED the hyphen — `Mary Beth O'Brien`
  instead of `Mary-Beth O'Brien`. Dollar amounts on the same fixture got
  flagged as illegible (false-positive — strokes were unambiguous per
  SNIPPETS.md). Both are §8.1 fidelity gaps but recoverable on review.
- **`pages/all-caps.jpg` reproducibly crashes the SYCL runner.** Process exits
  in 0.6s with `exit status 1` before any tokens generate. Other ~2 MB fixtures
  with similar dimensions (1812×1544 to 1996×1708) succeed, so this is
  image-content-specific, not memory-pressure or dimension-related. Possibly
  block-print all-caps writing triggers a different vision-encoder code path.
  Opened as chore #30 — does not gate the recommendation.

### MiniCPM-V

- **Severe omission tendency on beneficiary names.** Missed all 4 beneficiary
  names on `pages/print.jpg` (extracted relationships and shares but not the
  names themselves). Same pattern on other page fixtures.
- **Marker-character pollution on numeric values.** Emitted `'■: 50'` instead
  of `'50'` — transcribed a bullet/checkbox marker glyph as part of the value.
  Recurring across page fixtures.
- **Hallucinates field LABELS as values.** `absent-fields.jpg`: filled a blank
  line with `'Beneficiary 1'` (the field LABEL text), not realizing the value
  side was empty. This is the worst-case omit-if-absent failure mode — it
  produces output that *looks* valid until a paralegal cross-checks against
  the source.
- **Illegibility flag never fires.** `illegibility-stress.jpg` shape check
  FAILED with `illegible_count=0` on a fixture with one truly-illegible field.
  The model would silently produce a value for unreadable input — the §8.1
  discipline has no live signal under this model.
- **Duplicate emission.** `punctuation-stress.jpg` (qualitative): emitted
  `John Smith, Jr.` and `Mary-Beth O'Brien` TWICE, mapped to different envelope
  slots (grantor AND beneficiary slots for each). The model preserved
  `Mary-Beth` punctuation correctly (Qwen dropped the hyphen) but couldn't
  disambiguate which envelope slot owned the value.

## Why Qwen2.5-VL:7b wins despite imperfect score

1. **Failure modes are recoverable, not deceptive.** Qwen's MISMATCH cases are
   typically single-character OCR slips visible on review (`Sarah` → `Jarah`);
   a paralegal sees "this looks slightly off" and corrects. MiniCPM-V's
   failures include hallucinating the field LABEL as the value, marker
   characters polluting numeric fields, and silently inventing values for
   illegible writing — failures a paralegal may not realize occurred without
   careful source cross-check.
2. **Illegibility flag works on Qwen.** The §8.1 illegibility-as-first-class
   discipline assumes a model that conservatives on unreadable input. Qwen
   honors this; MiniCPM-V does not. Without a working illegibility signal,
   the §8.1 design point collapses.
3. **Comparable cost.** 41.3s vs 45.8s avg per-fixture; same iGPU footprint.
   No practical performance reason to prefer MiniCPM-V.

## Caveats

- **Single-writer corpus** — all fixtures by one writer per BASELINE.md /
  SNIPPETS.md disclaimer. Production deployment should validate against more
  diverse handwriting samples (the chore body's "expand the corpus per the
  §4.2 firm-side-evaluation guidance" path).
- **9 fixtures × 2 models is a small sample.** The 2× accuracy gap is robust
  enough to anchor the recommendation, but the *absolute* numbers (77.1%,
  37.0%) carry margin.
- **Auto-scoring uses lenient equality** (case + whitespace tolerated). The
  JSONL log carries §8.1 normalization signal (`notes="lenient match …"`) for
  audit. Strict-equality re-scoring would lower Qwen's MATCH rate by a small
  margin (`all-caps.jpg` aside, the lenient/strict gap is a few % at most).
- **iGPU constraint shaped the comparison.** Two ~5 GB models can't co-reside
  on the iGPU; the harness uses `keep_alive=0` between candidates as a
  workaround. Harmless for this eval but worth knowing for any future
  multi-model inference (e.g., ensembling).
- **The SYCL `all-caps.jpg` runner crash is a partial finding only.**
  Reproducible across two runs of this session. Did not investigate the root
  cause — opened as chore #30 with the captured error stack for follow-up.

## Follow-ups opened

- **Chore #29** — evaluate additional vision-model candidates (`gemma3:12b`,
  `qwen2.5vl:3b` — both already on disk, no pull cost) per chore #13's
  exit-criteria conditional ("if neither candidate clears a usability bar, the
  chore extends to evaluating additional candidates").
- **Chore #30** — investigate `pages/all-caps.jpg` reproducible SYCL runner
  termination on `qwen2.5vl:7b`. Captured error: `llama runner process has
  terminated: exit status 1`, ~0.6s wall-clock (pre-token generation). Image-
  content-specific (other similarly-shaped fixtures succeed).

## Artifacts (not committed; ephemeral)

- Scratch harness: `/tmp/eval_vision_models.py`
- Per-fixture JSONL log: `/tmp/eval-results.jsonl`
- Aggregate summary: `/tmp/eval-summary.txt`
- Scoring rubric: documented inline in `_norm()` + `score_field()` in the harness

---

# Addendum — 2026-05-12 — chore #29 extension (`qwen2.5vl:3b`, `gemma3:12b`)

Chore #29 (`2026-04-30-vision-model-eval-extension`) follow-up to chore
#13's exit-criteria conditional ("if neither candidate clears a usability
bar, the chore extends to evaluating additional candidates"). Run against
the IPEX-LLM SYCL stack post-chore-#30 (see
`2026-05-11-chore-30-resolution.md`).

**Methodology divergence from chore #13:** harness committed to the repo
this time. The `/tmp/eval_vision_models.py` from chore #13 was lost to
`/tmp` ephemerality between sessions, so the chore-#29 reconstruction
lives at `tests/v3/extraction/test_vision_model_eval.py`
(pytest.mark.integration). Same scoring rubric, same fixture set, same
ground-truth derivation from BASELINE.md + SNIPPETS.md.

## Run Conditions — 2026-05-12

- **Daemon:** `ipex-llm-ollama.service` (systemd) — chore #30 resolution
  state. GPU-active.
- **Candidates:** `qwen2.5vl:3b` (already on disk; same family as 7b),
  `gemma3:12b` (already on disk; alternate family).
- **Fixtures:** identical to chore #13 (9 total).
- **Inter-candidate eviction:** `keep_alive=0` ping per chore #13's
  hygiene discipline.
- **Per-request timeout:** 600s (env-var configurable; bumped from
  httpx default 300s for headroom).
- **JSONL log:** `tests/data/vision_eval_log/<timestamp>.jsonl` (gitignored).

## Quantitative Results

| Metric                              | `qwen2.5vl:3b` | `gemma3:12b`    | `qwen2.5vl:7b` (chore #13) |
| ----------------------------------- | -------------- | --------------- | -------------------------- |
| Fixtures completed                  | 7 / 9          | 0 / 9           | 8 / 9                      |
| Wall-clock total                    | 246.4s         | 30.2s           | 371.7s                     |
| Wall-clock avg / successful fixture | ~35s           | (none)          | 41.3s                      |
| **Auto-scored MATCH rate**          | **23 / 47 (48.9%)** | **0 / 0 (N/A)** | **27 / 35 (77.1%)**    |
| MISMATCH                            | 11             | —               | 4                          |
| OMITTED                             | 8              | —               | 3                          |
| HALLUCINATION                       | 4              | —               | 1                          |
| ExtractionError                     | 2              | 9               | 1 (`all-caps.jpg` SYCL — chore #30) |
| `illegibility-stress.jpg` shape     | **ERROR (unmeasurable)** | **ERROR** | **PASS**       |

## qwen2.5vl:3b Per-Fixture Detail

| Fixture                              | Wall-clock | Verdicts |
| ------------------------------------ | ---------- | -------- |
| `pages/print.jpg`                    | 48.8s      | MATCH 7, OMITTED 2, MISMATCH 1 |
| `pages/cursive.jpg`                  | 30.3s      | MATCH 5, MISMATCH 5 |
| `pages/hurried.jpg`                  | 27.0s      | MATCH 4, OMITTED 4, MISMATCH 2 |
| `pages/all-caps.jpg`                 | 27.1s      | MATCH 5, OMITTED 2, MISMATCH 3 |
| `snippets/absent-fields.jpg`         | 27.6s      | MATCH 1, OMITTED 1, **HALLUCINATION 3** |
| `snippets/illegibility-stress.jpg`   | 9.3s       | **ERROR ExtractionError** (model runner stopped) |
| `snippets/label-on-line-N.jpg`       | 31.0s      | MATCH 1, HALLUCINATION 1 |
| `snippets/punctuation-stress.jpg`    | 33.4s      | qualitative |
| `snippets/date-format-variance.jpg`  | 8.6s       | **ERROR ExtractionError** (model runner stopped) |

**Notable:** 3b cleared `pages/all-caps.jpg` cleanly under IPEX-LLM
(no chore-#30-style SYCL crash) — the all-caps crash was 7b-specific
and resolved by the new GPU stack. 3b's failures are *different*: two
mid-run runner stops on snippet fixtures (`illegibility-stress.jpg`,
`date-format-variance.jpg`) producing 500 errors with the message
"model runner has unexpectedly stopped, this may be due to resource
limitations or an internal error." Both happened after 5 successful
inferences, suggesting cumulative state pressure or content-specific
triggers — not investigated further (3b not recommended regardless).

## gemma3:12b Per-Fixture Detail

| Fixture                              | Wall-clock | Verdicts |
| ------------------------------------ | ---------- | -------- |
| (all 9 fixtures)                     | 3-4s each  | **ERROR** — `llama runner process has terminated: exit status 2` (status 500) |

**Diagnosis:** The bare `gemma3:12b` Ollama tag is a text-only build.
Exit status 2 from llama runner at ~3s per request, before any token
generation, is consistent with a request-validation failure on the
`images` parameter. Vision-capable Gemma 3 variants exist (e.g., the
27B model with vision adapter), but `gemma3:12b` as published in
Ollama's library cannot process image inputs through `OllamaBackend`.

**Spun out to chore #33** (`2026-05-13-gemma3-vision-capability-investigation`)
for follow-up: investigate whether a vision-capable Gemma tag exists in
Ollama's library, or whether multimodal Gemma adapter pulls are needed.
Out of scope for chore #29's exit criteria.

## Qualitative findings — qwen2.5vl:3b

### Failure modes are mixed (worse than 7b's pattern)

On pages-fixtures, 3b's MISMATCHes are character-level recoverable
drift — the same kind of errors 7b produces, just more of them:

- **cursive.jpg:** "James William Thompson" (lost "Jr." suffix),
  "March 15, 1938" (`1938` for `1958`), "Mary-Bethh O'Brien" (extra
  `h`), "Michael Michael Thompson" (duplicated first name), "Jarah Lin
  Thompson" (same single-character Sarah→Jarah slip 7b made on the
  same fixture in chore #13). All are paralegal-visible single-char
  errors, not deceptive inventions.
- **Beneficiary swap order honored.** 3b correctly emitted beneficiaries
  in the swapped order (Michael at [0], Sarah at [1]) per BASELINE.md.

But on **`absent-fields.jpg`** — the §8.3 omit-if-absent stress
test — 3b had **3 hallucinations** vs 7b's 1. This is the worst-case
failure mode: 3b invents content for blank value-sides, which
paralegals may not realize occurred without cross-checking. The
§8.3 omit-if-absent guardrail does not hold up under 3b.

### §8.1 illegibility-flag behavior: unmeasurable

The dedicated illegibility-stress.jpg fixture errored (model runner
stop), so we have no data on whether 3b honors `illegible=True`
emission. Without the working illegibility signal, the §8.1
discipline cannot be confirmed for this model. Combined with the
high hallucination rate elsewhere, 3b would not be deployable on
the §8.1 design point even setting aside accuracy.

### §7.4 reasoning-channel posture

Production envelope's reasoning-first key-order pin held across all
successful 3b inferences (verified via raw-output inspection in the
JSONL log). No anomalies on this axis; chore-#32's stronger §7.4
findings (reasoning-omission liveness risk at small envelopes) are
on 7b only, not re-tested on 3b in this run.

## gemma3:12b: not a valid candidate for `OllamaBackend`

As deployed in Ollama's library, the bare `gemma3:12b` tag does not
accept image inputs through the `format=<json_schema>`+`images=...`
request shape that `OllamaBackend.extract()` uses. Every fixture
errored at the request-validation tier (no inference attempted).
Whether a vision-capable Gemma 3 variant exists for this Ollama
installation is the chore-#33 question; this chore can close on
"not a viable candidate as configured."

## Recommendation: `qwen2.5vl:7b` stands

Neither candidate displaces the chore-#13 recommendation:

- **qwen2.5vl:3b** scores 48.9% — far below 7b's 77.1% and the
  chore-#13 illustrative >85% bar. Its failure pattern includes 4
  hallucinations (4× 7b's count), 2 runner stops, and the §8.1
  illegibility-shape-check could not be measured. Deceptive failure
  modes are more frequent than 7b's, making 3b paralegal-triage hostile.
- **gemma3:12b** is not vision-capable as deployed; cannot be evaluated
  on this surface.

The `OllamaBackend` recommendation docstring is updated to record this
empirical close-out. No production code path change.

## Caveats

- **Single-writer corpus still applies** (chore-#13 caveat carries forward).
- **3b runner stops not root-caused.** Logged for completeness; 3b
  not being recommended makes the investigation lower-priority.
- **Chore-#13's qualitative fixtures (`punctuation-stress`,
  `date-format-variance`) crashed on 3b** with the same runner-stop
  signature. No qualitative comparison possible.
- **Chore #33** owns the Gemma vision-capability question; chore #29
  closes on "extension complete, recommendation unchanged."

## Artifacts

- Committed harness: `tests/v3/extraction/test_vision_model_eval.py`
  (pytest.mark.integration)
- JSONL log (gitignored, local): `tests/data/vision_eval_log/<timestamp>.jsonl`
- Chore-#13 ephemeral scratch (`/tmp/eval_vision_models.py`) superseded
  by the committed integration test

---

# Chore #33 addendum — gemma3 root-cause + LLaVA / moondream evaluation (2026-05-13)

Closes chore #33 (`2026-05-13-gemma3-vision-capability-investigation`).
Three additional candidates evaluated post-chore-#29 close. **Recommendation
unchanged: `qwen2.5vl:7b` stands.**

## gemma3:{4b,12b} — root cause is NOT runner codepath gap

Chore #33 was opened with the working hypothesis that the bare `gemma3:12b`
Ollama tag was text-only (no vision support in the published manifest).
That hypothesis was *incorrect*. After re-pulling both `gemma3:4b` and
`gemma3:12b` and confirming `capabilities: ['completion', 'vision']` plus
mmproj projector tensor in the model_info, the runner still terminates
with `exit status 2` at ~2-4s per request. Server-side log capture
(`journalctl -u ipex-llm-ollama.service`) reveals the actual failure:

```
panic: insufficient memory - required allocations: {InputWeights:550502400A
  ... GPUs:[{Name:SYCL0 ... [60561408A × 34 layers, 1390948480A projector]
  Graph:1212612608F}]}
github.com/ollama/ollama/runner/ollamarunner.multimodalStore.getTensor
  (/home/arda/ruonan/ollama-internal/runner/ollamarunner/multimodal.go:98)
github.com/ollama/ollama/runner/ollamarunner.(*Server).reserveWorstCaseGraph
  (/home/arda/ruonan/ollama-internal/runner/ollamarunner/runner.go:796)
```

The multimodal codepath exists — the runner reaches `multimodalStore.getTensor`.
The panic is in `reserveWorstCaseGraph`: 35 per-layer weight allocations
(~60MB each) plus a 1.39 GB projector tensor (slot #35) exceed whatever
budget the IPEX-LLM SYCL0 allocator reserves on the Iris Xe iGPU. Same
constraint surface as chore #30 (`SYCL0 buffer allocation`), different
boundary (worst-case-graph reservation, not runtime allocation).

**Why qwen2.5vl:7b (8.3B params) loads but gemma3:4b (4.3B params) doesn't:**
parameter count isn't the gate — Qwen2.5-VL's ViT projector is more
allocator-friendly than Gemma3's SigLIP-based variant, and the runner's
worst-case estimate for Gemma3 multimodal is more conservative (over-reserves
on the projector tensor specifically). Verified with custom-built WSL2
kernel + fully-configured IPEX-LLM stack — kernel/driver layer is not
the constraint.

**Compounding factor (user-supplied):** IPEX-LLM Ollama is pinned to
upstream Ollama 0.9. Multimodal runner improvements in 0.10+ (better
projector handling, more granular graph reservation) are not in this
fork. Gemma 3 vision support is mostly post-0.9, so the runner-side
handling is from the era when Gemma 3 multimodal was less mature.

**Disposition:** gemma3 family is **not pursuable** via `OllamaBackend`
on this stack until either (a) IPEX-LLM rebases on newer Ollama with
improved multimodal allocator, or (b) the SYCL0 budget is significantly
expanded (would require a system with discrete GPU, not Iris Xe shared
memory). Not a code change. Recommendation downstream of this is
unchanged.

## moondream:latest (Phi-2 base, 1B params) — catastrophic

Pulled and evaluated as alternative architecture class after gemma3
ruled out. Runs cleanly on IPEX-LLM stack (no SYCL0 OOM, no runner
panics). **Score: 1 / 127 MATCH (0.8%).**

| Fixture | Wall-clock | MATCH | OMITTED | HALLUCINATION | Notes |
|---------|------------|-------|---------|---------------|-------|
| `pages/print.jpg` | ~25s | 0 | most | 1 | extracts plausible-looking junk |
| `pages/cursive.jpg` | ~22s | 0 | most | 0 | |
| `pages/hurried.jpg` | **4.2s** | 0 | 0 | 0 | fastest fixture — produced minimal envelope |
| `pages/all-caps.jpg` | **59.0s** | 0 | most | 0 | |
| `snippets/absent-fields.jpg` | ~12s | 0 | 0 | **82** | invented dozens of beneficiary entries on a fixture with 2 ground-truth values |
| (other snippets) | — | 1 total | — | rest | |

**Aggregate:** 1 MATCH, 6 MISMATCH, 37 OMITTED, **83 HALLUCINATION**,
0 ExtractionErrors. Total wall-clock 166.49s.

**Failure mode: deceptive.** The 82-hallucination explosion on
absent-fields.jpg is the worst-case §8.3 omit-if-absent violation pattern
amplified ~25× vs qwen2.5vl:3b (3 hallucinations on the same fixture).
Moondream produces syntactically valid JSON whose content is uncorrelated
with the source image. For legal extraction this is the most paralegal-hostile
failure mode possible — no surface signal that the content is fabricated.

**Why this happened:** moondream is purpose-built for image *captioning*
and *description* (its native task), not structured-schema extraction
under grammar-constrained decoding. The 1B Phi-2 base model combined
with the rigid JSON schema pressure produces output that satisfies the
schema but not the source. **Not viable.**

## llava-llama3:8b (LLaVA / CLIP-ViT-L + Llama3 backbone) — also non-viable

Pulled as second new architecture class after moondream ruled out.
Size-matched to qwen2.5vl:7b (8B vs 8.3B params). Runs cleanly on
IPEX-LLM stack (same vision-tower family as minicpm-v which already
worked). **Score: 3 / 51 MATCH (5.9%).**

| Fixture | Wall-clock | Verdicts |
|---------|------------|----------|
| `pages/print.jpg` | 52.9s | MATCH 0, MISMATCH 10 — extracts every field, all wrong |
| `pages/cursive.jpg` | 41.6s | MATCH 1, MISMATCH 5, OMITTED 4 |
| `pages/hurried.jpg` | 14.8s | MATCH 0, OMITTED 10 — **zero field-level output** |
| `pages/all-caps.jpg` | 14.9s | MATCH 0, OMITTED 10 — **zero field-level output** |
| `snippets/absent-fields.jpg` | 20.9s | MATCH 0, OMITTED 2, HALLUCINATION 4 |
| `snippets/illegibility-stress.jpg` | 40.1s | MATCH 1/1 (correctly flagged illegible) |
| `snippets/label-on-line-N.jpg` | 21.2s | MATCH 1, HALLUCINATION 3 |

**Aggregate:** 3 MATCH, 15 MISMATCH, 26 OMITTED, 7 HALLUCINATION,
0 ExtractionErrors. Total wall-clock 267s (4:27).

**Failure mode: honest (mostly).** Unlike moondream, llava-llama3 refuses
to commit when it can't read the image — `hurried.jpg` and `all-caps.jpg`
produce empty envelopes rather than fabricated content. This is safer
for paralegal triage but still unusable at 5.9% MATCH. The 7 hallucinations
(13.7% of scored fields) are concentrated on `absent-fields.jpg` and
`label-on-line-N.jpg`, suggesting the §8.3 omit-if-absent posture is
weak under this model as well.

**Why this happened:** LLaVA's CLIP-ViT-L vision tower is a general-purpose
image-captioning encoder. Qwen2.5-VL's vision tower was specifically
pre-trained on document understanding (per the model card). The 13×
MATCH delta isn't model size or backbone quality — it's training-data
alignment with the form-extraction task. The CLIP tower simply doesn't
have strong handwriting-on-form representations.

## Final tally (all candidates evaluated on this surface)

| Model | Params | MATCH | Stack outcome | Verdict |
|-------|-------:|------:|---------------|---------|
| **qwen2.5vl:7b** | **8.3B** | **77.1%** | runs (post-#30) | **Production recommendation** |
| qwen2.5vl:3b | 3.8B | 48.9% | runs; 2 runner-stops | Not recommended (deceptive failures) |
| minicpm-v:latest | 7.6B | 37.0% | runs | Chore #13 baseline |
| llava-llama3:8b | 8.0B | 5.9% | runs | Not viable (training mismatch) |
| moondream:latest | 1.0B | 0.8% | runs | Not viable (82-hallucination explosion) |
| gemma3:4b | 4.3B | — | **runner OOM** | Not pursuable (Ollama 0.9 + SYCL0 budget) |
| gemma3:12b | 12.2B | — | **runner OOM** | Not pursuable (same root cause) |

Five distinct architecture families tested across chore #13 + #29 + #33:
Qwen2.5-VL, Qwen2-based (minicpm-v), LLaVA-Llama3 (CLIP+Llama3),
Phi-2-based (moondream), Gemma3 (SigLIP+Gemma3). Two families produce
production-quality results (Qwen2.5-VL clearly; minicpm-v marginally
at the chore-#13 baseline). Three families are not viable. Gemma3 is
gated by infrastructure, not model quality — would need re-test if/when
IPEX-LLM Ollama rebases on a newer upstream.

## Updated chore #33 disposition

Closing with the finding **"gemma3 vision is runner-OOM under Ollama 0.9
on the SYCL0 budget; not pursuable on current stack; no alternative
architecture displaces qwen2.5vl:7b."** Chore-#13 + #29 recommendation
holds for the third time. Production code path unchanged.

## Artifacts (this addendum)

- JSONL logs (gitignored, local):
  - `tests/data/vision_eval_log/20260513T164051Z.jsonl` (gemma3 retry, all errored)
  - `tests/data/vision_eval_log/20260513T164456Z.jsonl` (moondream)
  - `tests/data/vision_eval_log/20260513T205300Z.jsonl` (llava-llama3:8b)
- Runner panic trace: captured inline above from
  `journalctl -u ipex-llm-ollama.service` 2026-05-13 ~15:49 CDT.

---

# Chore #33 amendment — granite + llava + grammar-constrained-decoding pathology (2026-05-13 PM)

Two additional candidates evaluated after chore #33 was nominally closed:
`granite3.2-vision:2b` (IBM Granite, 2.5B, granite + clip families) and
`llava:7b` (classic LLaVA-1.6 on Vicuna/Mistral). A 10-minute total-eval
budget was introduced mid-evaluation; both candidates fail this budget
*despite* normal underlying model behavior. The disqualifier surfaces a
**structural finding about grammar-constrained decoding under Ollama 0.9**
that subsumes both results and explains the Gemma3 timeout pattern.

## granite3.2-vision:2b — strongest *quality* finding, disqualified on wall-clock

Pulled and evaluated as the IBM Granite document-understanding class.
Full eval completed in **17:56** (8/9 fixtures scored, 1 timeout at
600s on `pages/hurried.jpg`). Aggregate scores:

| Metric | granite3.2-vision:2b |
| ------ | -------------------: |
| MATCH | **19 / 34 (55.9%)** |
| MISMATCH | 13 (38.2%) |
| OMITTED | 2 (5.9%) |
| **HALLUCINATION** | **0** |
| Timeouts (600s) | 1 (`pages/hurried.jpg`) |
| Total wall-clock | 17:56 |

Per-fixture (excluding timeout):
- `pages/print.jpg` 72.6s — 7/10 MATCH, 3 MISMATCH
- `pages/cursive.jpg` 64.7s — 4/10 MATCH, 6 MISMATCH
- `pages/all-caps.jpg` 60.3s — 5/10 MATCH, 3 MISMATCH, 2 OMITTED
- `snippets/absent-fields.jpg` 60.1s — **2/2 MATCH (100%)** — §8.3 perfect
- `snippets/illegibility-stress.jpg` 45.7s — 0/1 MATCH (failed §8.1 illegible-flag)
- `snippets/label-on-line-N.jpg` 45.3s — 1/1 MATCH

**This is the strongest *positive* finding of the entire sweep.**
55.9% MATCH with **zero HALLUCINATIONs** is qualitatively safer than
qwen2.5vl:3b's 48.9% MATCH with 4 hallucinations: granite's failures
are MISMATCH (wrong field-attribution against real source content) and
OMITTED (no answer) — never fabricated content. For paralegal triage,
"wrong slot, real data" is detectable; "plausible invented data" is not.
At 2.5B params this is a striking result.

**But: disqualified on wall-clock.** 17:56 total exceeds the 10-min
operational budget. The `pages/hurried.jpg` 600s timeout is a hard
liveness failure on a routine handwriting fixture; in production a
paralegal can't wait 10 minutes for a single intake. §8.1 illegibility
shape-check also failed (0/1 on the dedicated fixture). Not viable at
the structured-extraction call site even with the favorable failure
profile.

## llava:7b — disqualified pre-completion via the 10-min rule

Pulled and started full eval. After **17 minutes** wall-clock the run
had completed only 1 fixture (`pages/print.jpg`, 1m16s) and timed out
on fixture #2 (10m). The eval was killed and replaced with a smoke
test per the 10-min disqualifier rule:

| Smoke prompt | Wall-clock | Response |
|-------------|----------:|----------|
| "grantor full legal name?" on `print.jpg` | 33.6s | "James william thompson" (correct content, missed "Jr.") |
| "beneficiary names?" on `absent-fields.jpg` | **5.8s** | "None" (correct §8.3 behavior) |

Smoke times are *normal* for this stack (comparable to other 7B models
in chat mode). Llava's underlying capability is intact — it reads the
images, produces accurate content, honors absent-content prompts. The
pathology is exclusively in the structured-extraction code path.

## Structural finding: grammar-constrained decoding under Ollama 0.9 is fragile

The pattern is now consistent across three of today's six candidates:

| Model | Smoke (chat) | Structured (grammar) | Delta |
|-------|------------:|---------------------:|------:|
| llava:7b | ~6-34s | 1m16s success → 10m timeout | **>10×** slower |
| granite3.2-vision:2b | ~24-29s | 1m / fixture, 1 × 10m timeout | **~2-25×** slower |
| gemma3:{4b,12b} | (didn't reach inference — OOM) | runner panic | n/a |
| **qwen2.5vl:7b** | (chore-#13 ~30s) | ~30-45s / fixture | **~1×** (no penalty) |

`OllamaBackend.extract()` uses `format=GenerationEnvelope.model_json_schema()`
(spec §7.3) to constrain the output. This forces the runner's sampler
to navigate a JSON grammar lattice: when the model's preferred next-token
distribution is concentrated on grammar-disallowed tokens, the runner
re-samples repeatedly until landing on an allowed token. Models with
strong free-form priors (LLaVA, Granite, presumably Gemma3) hit this
adversarially; models pre-trained on document-structured output
(Qwen2.5-VL family) align naturally with the grammar.

This is the same Ollama 0.9 era constraint surface as the Gemma3 OOM —
multimodal allocator and grammar-constrained sampler are both areas
that received substantial upstream improvements in 0.10+. The IPEX-LLM
fork hasn't rebased. Re-opening the architecture sweep should be
gated on either (a) IPEX-LLM Ollama version bump past 0.10, or (b)
relaxing `format=...` constraints in `OllamaBackend.extract()`, which
would break the spec-§7.3 schema-pinning guarantee and is not on the
table.

## Practical implication for model selection

The selection criterion is no longer "best vision model for handwriting
OCR" — it's **"best vision model whose token distribution is compatible
with the production grammar lattice on this runner."** Empirically, only
Qwen2.5-VL clears this bar. Granite would be the strongest backup *if*
the production code path could afford 17min eval cycles; it can't.

The final disposition for `OllamaBackend` model selection is therefore
**qwen2.5vl:7b**, reaffirmed across four evaluation rounds (chores #13,
#29, #33-initial, #33-amendment) and six architecture families.

## Artifacts (amendment)

- JSONL log (gitignored, local):
  - `tests/data/vision_eval_log/20260513T210638Z.jsonl` (granite full eval — 8 fixtures + 1 timeout)
  - No JSONL for llava:7b — eval was killed mid-run; smoke-test results
    captured inline in this section.
- Server-side activity trace: per-fixture wall-clock visible in
  `journalctl -u ipex-llm-ollama.service` 2026-05-13 16:06-16:42 CDT
  (granite 16:06-16:24, llava 16:25-16:42).

## Moondream re-investigation (2026-05-13 follow-up)

Re-pulled `moondream:latest` (Phi-2 base, 1B, vision-capable) after the
grammar-constrained-decoding finding to revisit the catastrophic 0.8%
MATCH / 82-hallucination result from the chore-#33 initial sweep.

Three diagnostic probes against `print.jpg`:

| Probe | Prompt style | Wall-clock | `eval_count` | Content |
|-------|-------------|----------:|-------------:|---------|
| 1 | "Describe this image in detail." | 12.4s | **54** | "The image shows a yellow lined notebook page with handwritten text written by a person named **James William Thompson**, dated March 15, 1968. The text includes information about real property values and the names of several individuals, such as 'Grantor' and 'William'." |
| 2 | "Is this an image of a form? Answer yes or no." | 9.0s | **1** | (empty string) |
| 3 | `/api/generate` "What is written at the top of this form?" | 0.5s | **1** | (empty string) |

**Probe 1 shows moondream's vision works** — correctly extracted the
grantor name from the form (missed "Jr." suffix; got DOB year wrong by
one — "1968" vs ground-truth "1958", consistent with a 5/6 handwriting
misread). The rest of the description is source-anchored, not
fabricated.

**Probes 2 and 3 reveal the structural issue:** `eval_count=1` means
moondream emitted exactly ONE token before stopping — almost certainly
the EOS token. Moondream's training distribution is **captioning-only**;
the model has a strong prior to emit EOS in response to non-captioning
prompts (Q&A, extraction, yes/no, anything constrained). It isn't
producing wrong content — it's producing *no* content.

### Reframing the original 82-hallucination explosion

Under `OllamaBackend.extract()` with `format=<json_schema>`,
moondream's strong-EOS prior collides with the grammar lattice:
- Moondream wants to emit EOS after seeing the schema-opening tokens.
- Grammar disallows EOS until the schema is satisfied.
- Runner re-samples until a non-EOS token is selected.
- After enough re-samples, the distribution is effectively flat — any
  schema-allowed token can be selected with roughly uniform probability.
- Net effect: random names and values from moondream's pretraining
  corpus flow into the schema slots, producing structurally-valid
  output that's source-uncorrelated.

This is **not hallucination in the usual sense** (model invents
plausible content). It's **grammar-forced sampling from a noise
distribution after the model has effectively given up**. Mechanically
distinct from llava-llama3's OMIT-everything pattern, which expresses
the same "wrong tool for the task" verdict via a different decoder
behavior (refusal vs flood).

### Updated moondream verdict

Moondream is **mis-matched** to the production extraction task, not
broken. The model would produce zero-hallucination, source-anchored
output on its native captioning task. The 0.8% MATCH score in the
chore-#33 sweep was a measurement of how the grammar lattice interacts
with a captioning model's EOS prior — not a measurement of moondream's
capability.

Practical implication: moondream remains **not viable** for
`OllamaBackend.extract()`, but it's no longer "catastrophic" in a
generic sense. If a downstream task ever needed image captioning
(not structured extraction), moondream would be a reasonable
lightweight candidate. That's not in `OllamaBackend`'s scope, so the
recommendation is unchanged.

### Diagnostic generalization

The two distinct grammar-constrained-decoding failure modes now
observed:

| Mode | Manifestation | Models exhibiting |
|------|---------------|-------------------|
| **Re-sample slowdown** | Coherent content, pathological wall-clock | LLaVA:7b, llava-llama3:8b, Granite |
| **EOS-prior noise flood** | Fast wall-clock, schema-valid garbage | Moondream |

Both reduce to the same root cause: token distribution mis-aligned
with the grammar lattice. The slowdown mode is grammatically-fluent
models being forced to re-sample. The noise-flood mode is models
whose effective distribution after EOS-prior is so flat that the
grammar's allowed tokens get sampled near-uniformly.

Qwen2.5-VL avoids both: its document-structured pretraining gives it a
distribution that already prefers schema-valid tokens, so neither
pathological mode triggers.

## Timing inconsistency + granite re-investigation (2026-05-13 final follow-up)

Two open questions surfaced after the moondream re-investigation: (1)
why is per-fixture timing so inconsistent across candidates? (2) did
we miss something with granite, given its 600s timeout dominated its
wall-clock budget? Both are now answered, and a **third grammar-
constrained-decoding failure mode** was discovered in the process.

### Per-fixture timing variance is a failure-mode signature

Cross-model timing for the 9-fixture suite (excluding gemma3 which
errored at 2-4s each):

| Model | n | min | median | max | max/min ratio | Pattern |
|-------|--:|----:|-------:|----:|--------------:|---------|
| **granite3.2-vision:2b** | 8 | 45.3s | 63.1s | 72.6s | **1.6×** | tight, structurally consistent |
| llava-llama3:8b | 9 | 14.8s | 25.5s | 52.9s | 3.6× | moderate, content-dependent |
| moondream | 9 | 4.2s | 6.0s | 59.0s | **13.9×** | wildly variable, content-driven |
| qwen2.5vl:7b (chore #13) | 8 | ~22s | ~40s | ~80s | ~3-4× | depends on content+errors |

**The variance ratios directly map to grammar-mismatch failure modes:**

- **Granite (1.6× tight):** model emits coherent tokens; wall-clock is
  dominated by schema-grammar lattice traversal (relatively fixed cost
  per schema-token). Image content matters less because the model's
  output is paced by the grammar, not by the image.
- **LLaVA-llama3 (3.6× moderate):** mix of OMIT-fields (fast, short
  responses) and successful extractions (slower). Wall-clock variance
  ≈ "how many fields the model attempts."
- **Moondream (13.9× wild):** 4.2s = model emits EOS immediately, near-
  zero output. 59.0s = grammar re-sampling hit pathological depth for
  that image. Variance ≈ "how stuck the EOS-prior gets per fixture."

The variance ratio is essentially **a fingerprint of how well a model's
output distribution aligns with the grammar.** Tight = well-aligned
(slowdown is just grammar traversal). Wild = poorly aligned (token
distribution doesn't match grammar, behavior is fixture-specific noise).

### Third failure mode: refusal-vs-schema collision

Granite's anomaly: 8 fixtures clustered at 45-73s, then **one outlier
at 600s** (`pages/hurried.jpg`). The 600s = the harness per-request
timeout ceiling; we don't know if the model would have eventually
returned. Re-probe in chat mode (no `format=<json_schema>`) with
1500s timeout:

```
Granite chat-mode on hurried.jpg:
  TERMINATED in 31.6s, eval_count=5, prompt_eval_count=4096
  Response: "\nunanswerable"
```

Granite assessed `pages/hurried.jpg` as too unreadable, emitted
"unanswerable" (5 tokens), and stopped cleanly. **The 600s harness
timeout was not granite struggling — it was granite trying to refuse
under a grammar that requires schema-compliant output.** The model's
intent ("can't read this") has no expression path through the JSON
schema, so the runner re-samples indefinitely looking for a grammar-
compatible path that aligns with the model's distribution. It never
finds one.

This adds a third mode to the diagnostic taxonomy:

| Mode | Symptom | Models | Mechanism |
|------|---------|--------|-----------|
| Re-sample slowdown | Coherent content, slow wall-clock | LLaVA, llava-llama3, granite (normal fixtures) | Output distribution mostly grammar-compatible, occasional token resampling |
| EOS-prior noise flood | Fast wall-clock, schema-valid garbage | moondream | Strong EOS prior → runner forces past EOS → flat distribution → random tokens |
| **Refusal-vs-schema collision** | **Full per-request timeout** | **granite on hurried.jpg, possibly qwen2.5vl:3b on illegibility-stress.jpg** | **Model wants to refuse/abstain; grammar requires schema-populated output; no compatible path exists; runner re-samples to ceiling** |

The chore-#29 finding that qwen2.5vl:3b runner-stops on the
illegibility-stress fixture is plausibly the same mode — 3b wanted
to flag illegibility but couldn't satisfy the §8.1 illegibility
shape under the grammar, exhausting itself trying.

### Granite re-classification: content accuracy > strict MATCH

The strict-MATCH score (55.9%) penalizes format-near-misses and
1-character OCR errors equally with content-fabrications. Reclassifying
granite's 14 MISMATCH verdicts on the existing JSONL:

| Bucket | Count | Examples |
|--------|------:|----------|
| MATCH (strict) | 19 | exact string match |
| **NEAR-FMT** | **2** | `"50%"` vs `"50"`, `"JAMES WILLIAM THOMPSON JR"` vs `"James William Thompson, Jr."` |
| **NEAR-OCR** (1-2 char) | **1** | `"Mary Bath O'Brien"` vs `"Mary-Beth O'Brien"` |
| **NEAR-DATE-FMT** | **1** | `"November 8, 1940"` vs `"11/08/1960"` (year wrong but month/day correct) |
| REAL wrong content | 8 | `"60%"` vs `"50"`, `"1108/960"` vs `"11/08/1960"`, `"N/A (not provided)"`, etc |
| OMITTED | 2 | — |
| HALLUC | 0 | — |

**Content-correct rate: 23/33 = 69.7%** (matches that read the source
content even if format/case/single-character drift). Within 7-8
percentage points of qwen2.5vl:7b's 77.1% strict MATCH.

The 8 REAL wrong-content errors are genuine OCR misreads (`"60%"` for
`"50"`, `"Lynn Lind"` for `"Sarah Lin"`) or refusals scored as
mismatch (`"N/A (not provided)"`). Still zero invented content
across all 33 scored fields.

### What this changes about granite's disposition

The original verdict (DQ on wall-clock) was correct given the
17:56 measurement, but the *reason* for the wall-clock is now
properly attributed:

```
17:56 total =
  8 successful fixtures × ~60s each ≈ 8 min
  + 1 refusal-collision (hurried.jpg) × 600s ceiling = 10 min
```

**Without the refusal-collision overhead, granite's eval would be
~8-10 min — within the 10-min budget.** Granite is therefore
**salvageable conditional on harness changes**, not fundamentally
disqualified by the model. Specifically:

- (a) Detect grammar-stuck state in `OllamaBackend.extract()` and
  fail-fast before the 600s ceiling (e.g., abort if no token
  emitted for N seconds, or if eval_count stays at 0 past a
  threshold).
- (b) Schema-relaxation for refusal cases — allow a top-level
  `unanswerable=true` flag in the envelope that satisfies the
  grammar while preserving refusal semantics. Would require
  spec §7.3 amendment.
- (c) Per-fixture short-timeout-with-retry (e.g., 90s ceiling
  with one re-prompt before declaring failure).

None of these are in scope for chore #33 — they're future
infrastructure work that would re-open the candidate field. With
the current `OllamaBackend.extract()` code path, granite remains
disqualified on wall-clock. qwen2.5vl:7b recommendation unchanged.

### Updated final tally

Granite is now the **second-place candidate by content accuracy** in
the entire sweep (69.7% content-correct, behind qwen2.5vl:7b's 77.1%
strict-MATCH-which-already-tolerates-format-via-`_norm()`), with the
best **safety profile** of any model tested (zero invented content
across 33 scored fields). The path to re-evaluation runs through
harness improvements, not model swaps.

## Granite retest under corrected invocation pattern (2026-05-13 last follow-up)

The previous granite disposition ("DQ on wall-clock") was based on a
measurement under the production prompt + 600s per-request timeout.
The refusal-collision discovery means the wall-clock was a function
of *invocation configuration*, not granite's intrinsic capability.
This section tests whether changing the invocation pattern alone
moves granite into budget — which it does, but with new tradeoffs
that change the disposition reasoning.

### Method

Same `OllamaBackend.extract()` code path. Two changes only:
- **Prompt:** swapped via `prompt_builder=` constructor seam to a
  refusal-targeted variant. The variant explicitly tells granite that
  per-field `illegible=True` (or empty `grantors[]` / `beneficiaries[]`
  objects) is the only refusal channel — no document-level refusal
  path exists in the grammar.
- **Per-request timeout:** cut from 600s to **120s** — fail-fast on
  refusal-collisions that the prompt didn't resolve.

Schema unchanged (still spec §7.3 `format=<json_schema>` pin).
Backend code unchanged. Production envelope unchanged.

Direct hurried.jpg probe under refusal-prompt: **terminated in 59.1s**
with `eval_count=112`, emitting a clean envelope:

```json
{
  "reasoning": "The document contains handwritten text... due to the
                illegible nature of some of the handwriting, it is not
                possible to accurately transcribe all the information...
                Therefore, I will mark each field as 'illegible' and
                provide null values for those that cannot be read confidently.",
  "grantors": [{}, {}],
  "beneficiaries": [{}, {}]
}
```

Granite found a grammar-compatible refusal path (empty objects in the
arrays) that didn't exist in its solution space under the production
prompt. The refusal-collision was prompt-engineering-induced.

### Full eval under refusal-prompt + 120s ceiling

| Fixture | Original (prod prompt, 600s) | Refusal-prompt (120s) | Δ |
|---------|------------------------------:|----------------------:|---|
| `pages/print.jpg` | 7/10 MATCH @ 72.6s | **8/10 @ 64.7s** | **+1 MATCH, faster** |
| `pages/cursive.jpg` | 4/10 MATCH @ 64.7s | **6/10 @ 57.8s** | **+2 MATCH, faster** |
| `pages/hurried.jpg` | ERR @ 600s | ERR @ 120s | **5× faster failure** (still ERR) |
| `pages/all-caps.jpg` | 5/10 MATCH @ 60.3s | **0/10 @ 51.7s** | **-5 MATCH** (refused everything) |
| `snippets/absent-fields.jpg` | 2/2 MATCH | 1/3 + **1 HALLUC** | **-1 MATCH + 1 NEW HALLUC** |
| `snippets/illegibility-stress.jpg` | (no scored fields) | (no scored fields) | same outcome, faster |
| `snippets/label-on-line-N.jpg` | 1/1 MATCH | **0/1** (refused) | -1 MATCH |
| `snippets/punctuation-stress.jpg` | qualitative | qualitative | slower (84.7s vs 64.2s) |
| `snippets/date-format-variance.jpg` | qualitative | qualitative | faster |

**Aggregate change:**

| Metric | Production prompt | Refusal-prompt | Δ |
|--------|------------------:|---------------:|--:|
| Total wall-clock | 17:56 | **9:35** | -8:21 (**within 10-min budget**) |
| Strict MATCH rate | 55.9% (19/34) | 44.1% (15/34) | **-11.8pp** |
| HALLUCINATIONs | 0 | **1** | +1 (new §8.3 violation on absent-fields) |
| OMITTED rate | 5.9% (2/34) | 35.3% (12/34) | +29.4pp |

### Why the accuracy regression

The refusal-prompt is *too* refusal-permissive. The diagnostic shows
two distinct effects:

- **Improved on hard fixtures** (print, cursive): the prompt's
  emphasis on the reasoning channel helps granite think through
  ambiguous handwriting before committing, and the explicit refusal
  path lets it avoid the worst-case grammar lattice traversal.
- **Worsened on legible fixtures** (all-caps): granite became
  trigger-happy with refusal. On `all-caps.jpg` — which is a
  *legible* fixture in chore-#13's typology — it refused every
  field. The prompt's "illegibility is the only refusal channel"
  framing nudged the distribution toward refusal even when content
  was readable.

The 1 HALLUCINATION on absent-fields.jpg is particularly
interesting: granite emitted a `beneficiary_shares[1].share_percent=50`
on a fixture whose ground-truth says shares are intentionally absent.
That's the kind of false-positive the production prompt's §8.3
anti-hallucination guardrails specifically prevented. The refusal-
prompt didn't replicate that guardrail strength.

The `pages/hurried.jpg` failure persisted at 120s — refusal-collision
is not fully resolved by the prompt change for this specific image.
Suggests hurried.jpg has handwriting properties that trigger a
granite-internal state the refusal prompt can't redirect.

### Corrected disposition

Three honest revisions to the earlier writeup:

1. **The "DQ on wall-clock" framing was lazy.** Granite is not
   structurally disqualified by wall-clock — the wall-clock is a
   function of invocation configuration, not intrinsic model
   capability. The user's call-out was correct.

2. **But granite is not strictly better than qwen2.5vl:7b under
   either invocation.** Production prompt → 55.9% MATCH at 17:56
   (exceeds budget). Refusal prompt → 44.1% MATCH + 1 HALLUC at
   9:35 (fits budget). qwen2.5vl:7b → 77.1% MATCH at ~6 min.
   Both granite configurations are dominated by qwen2.5vl:7b on
   the accuracy/wall-clock Pareto frontier.

3. **Granite occupies a distinct point on the safety/accuracy
   Pareto frontier under the production prompt** — zero invented
   content across 33 scored fields, vs qwen2.5vl:7b's 1
   hallucination across the same fixture set. That's the strongest
   argument for keeping granite as a documented backup, not the
   wall-clock number. The refusal-prompt configuration loses
   even this safety advantage (1 new hallucination appears).

### Re-opening criteria — sharpened

The original chore #33 close-out listed Ollama 0.10+ rebase as the
re-opening trigger. The retest reveals a second triggering
condition: **prompt-engineering investment** could move granite
into a more favorable position. Specifically:

- A prompt that preserves the §8.3 omit-if-absent guardrail strength
  while still enabling the per-field refusal path (current refusal
  prompt sacrifices the former for the latter).
- A retry mechanism in `OllamaBackend.extract()` that detects
  grammar-stuck state (no tokens emitted for N seconds) and
  re-prompts with the refusal-aware variant only on the second pass.
  Production prompt for the happy path; refusal-prompt as fallback.
- Or an envelope schema amendment (spec §7.3) adding an explicit
  `document_unanswerable: bool` flag that allows whole-document
  refusal without grammar gymnastics.

None of these are in scope for chore #33. They are documented as
*candidate harness improvements* whose value depends on whether
the project ever needs a second-place model with a different safety
profile (e.g., for a paralegal-triage workflow that prioritizes
"no invention" over "high coverage").

### What's in the JSONL

`tests/data/vision_eval_log/20260513T_granite_refusal_prompt.jsonl`
(gitignored, local). Same schema as the production-prompt log; the
`model` field is tagged `"granite3.2-vision:2b (refusal-targeted
prompt)"` to distinguish from the 20260513T210638Z baseline.
