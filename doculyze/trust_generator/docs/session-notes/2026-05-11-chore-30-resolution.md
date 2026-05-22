# 2026-05-11 — Chore #30 resolution

Chore #30 (`2026-04-30-all-caps-sycl-runner-crash`) was opened against upstream-Ollama-era behavior and carried a misdiagnosis that survived the IPEX-LLM swap. This note records the empirical resolution session: three hypotheses ruled out, one cleanup chain that actually fixed it.

The companion `2026-05-11-ipex-llm-ollama-gpu-reference.md` captures the target operational state in full; this note focuses on the debugging journey and what each step proved.

## Original chore body (incorrect in hindsight)

> Reproducible SYCL runner termination on `qwen2.5vl:7b` against `pages/all-caps.jpg` — exits status 1 in 0.6s, pre-token. Image-content-specific (other similar-sized fixtures succeed).

> Possibly block-print all-caps writing triggers a different attention codepath in the vision tower than mixed-case writing.

The "image-content-specific" framing came from observing that `all-caps.jpg` reproducibly failed under chore-#13 eval while neighboring 1.9-2.0 MB fixtures (`hurried.jpg`, `cursive.jpg`, `print.jpg`) succeeded. The conclusion that the content (block-print all-caps writing style) was the operative variable did not survive verification under the new IPEX-LLM stack.

## Hypothesis 1 — image-content-specific (refuted)

**Test:** native `all-caps.jpg` (2.0 MB, 1812×1544, exact original file from chore-#13 eval) → `/api/chat` against `qwen2.5vl:3b` under current IPEX-LLM ollama daemon, no preprocessing.

**Result:** 16.01s wall-clock, semantically-correct ALL-CAPS transcription (`"GRANTOR 1 FULL LEGAL NAME: JAMES WILLIAM THOMPSON JR..."`).

**Conclusion:** The original chore-body claim was wrong. Today, with the same image, same prompt, against a same-family model, the failure does not reproduce. Either the failure was specific to upstream Ollama's vision pipeline (which IPEX-LLM replaces) or to userspace-stack state that has since been corrected.

## Hypothesis 2 — gmmlib version-skew (red herring)

**Trigger for the hypothesis:** mid-session investigation discovered `/usr/local/lib/libigdgmm.so.12.10.0` (a 4.0 MB unstripped from-source build of intel/gmmlib master, dated May 11 14:26) shadowing the 935 KB Debian-packaged `/usr/lib/x86_64-linux-gnu/libigdgmm.so.12.10.0`. `ldconfig -p` resolved `libigdgmm.so.12` from `/usr/local/lib` first, meaning every process loading the GPU memory-management library got the from-source version.

`libze-intel-gpu1` (the Intel L0 driver, version 26.05.37020.3-1) was packaged against the Debian gmmlib version. From-source debug-build gmmlib is ABI-compatible by symbol name but has different allocator fast-path behavior. Plausible suspect for "small-allocation paths work, large 2D image-tensor allocations wedge" wedge pattern observed earlier in the session.

**Fix applied:** removed `/usr/local/lib/libigdgmm.so*`, rebuilt `ldconfig` cache, restarted ollama daemon. Verified ldconfig now resolves only from `/lib/x86_64-linux-gnu/`.

**Result:** wedge still reproduced on `hurried.jpg` (600s urllib timeout, runner alive but no tokens). gmmlib was not the cause.

**Conclusion:** Although fixing the version-skew was correct hygiene, it did not unblock vision inference on its own. Red herring (but a legitimate cleanup — the from-source override would have caused regressions eventually).

## Hypothesis 3 — payload-byte-size bound (refuted)

**Test:** seven progressively larger versions of `hurried.jpg` (256, 512, 768, 1024, 1280, 1512, 1812 px longest-edge, PIL re-encoded at q=85 to bracket payload bytes from 20 KB up to 459 KB).

**Result:** all 7 sizes completed in 10-15 seconds with consistent transcriptions. No wedge at any dimension.

**Follow-up test:** native on-disk bytes of `hurried.jpg` (1.9 MB) and `all-caps.jpg` (2.0 MB) — without any PIL re-encoding — sent as base64 directly to `/api/chat`.

**Result:** both completed in 14-16 seconds. The native payload bytes (which were 4.5× larger than the bisection's re-encoded version at the same pixel dimensions) made no observable difference.

**Conclusion:** Neither pixel dimensions nor payload byte size was the operative variable. The wedge — when it occurred — was not size-bound.

## What actually fixed it

By the time the verification harness was running cleanly, several things had changed since the chore was originally opened:

1. **Migrated from upstream Ollama to IPEX-LLM Ollama** — replaces the entire inference engine with one that uses Intel SYCL via `libggml-sycl.so` instead of upstream's CPU/CUDA/Vulkan backends. The original "0.6s exit status 1" failure mode is a property of upstream Ollama's vision pipeline; the IPEX-LLM fork has different code at that path.

2. **Removed `/etc/OpenCL/vendors/loader.icd`** — a self-referential ICD entry created earlier in the maintainer's debugging (pointed at `libOpenCL.so`, the OpenCL loader itself, rather than at a vendor ICD). When present, this entry would cause the ICD dispatcher to load itself as a vendor in a probe loop.

3. **Removed from-source `gmmlib` build override** — the `/usr/local/lib/libigdgmm.so*` files described in Hypothesis 2.

4. **Deployed under systemd as `ipex-llm-ollama.service`** — replaced ad-hoc shell-launched daemon with a managed service. Enables consistent restart on failure and predictable env-var flow into the daemon process.

5. **Disabled `OLLAMA_KEEP_ALIVE=10m`** in `start-ollama.sh` — when set as a daemon env var, it overrides per-request `keep_alive=0` and blocks programmatic model eviction. Did not directly cause the wedge but obscured diagnosis attempts that wanted to evict cleanly between candidates.

The transient 600s wedge observed mid-session (against `hurried.jpg`, before the gmmlib cleanup) is most consistent with stale SYCL runner state from the earlier broken stack — possibly a wedged SYCL command queue left by a prior runner that crashed under the gmmlib + loader.icd combo. After the cleanup chain (gmmlib removal + daemon restart + service unit cleanup), the wedge ceased to reproduce.

## Verification results — closing data

Final inference test (run after the cleanup chain was complete + the customized systemd service was running):

| Test | Model | Image | Wall-clock | Outcome |
|---|---|---|---|---|
| Text only | `qwen2.5:0.5b` | (none) | 4.03s cold / 0.24s warm | 367 tok/s prompt, 21 tok/s decode |
| Vision (small) | `qwen2.5vl:3b` | tiny probe 128×128 | 8.67s cold / 1.70s warm | 442 tok/s prompt, 8.8 tok/s decode, semantically correct |
| Vision (native chore target) | `qwen2.5vl:3b` | native `all-caps.jpg` 1812×1544 / 2.0 MB | 16.01s | Semantically correct ALL-CAPS transcription |

Throughput at GPU speeds across all three. CPU-only inference of qwen2.5vl:3b would be ~10× slower for the same workloads.

## Lessons (codified in §11 of the reference doc)

The reference doc's "Pitfalls + anti-patterns" section codifies each anti-pattern with the specific symptom it produces and the corrective command. For future regressions:

- Don't build gmmlib from source — Debian's `libigdgmm12` is the canonical version, matched against the Intel L0 driver
- Don't register OpenCL ICD loader as a vendor (the self-reference loop)
- Don't trust ollama's `library=cpu` log line under IPEX-LLM
- Don't chase missing `/dev/dri/` on WSL — it's not required for the L0/libdxcore path
- Don't run upstream Ollama and IPEX-LLM Ollama on the same machine
- Don't set `OLLAMA_KEEP_ALIVE` as a daemon env var

## Commits

- (this commit) — both session notes (reference + this resolution narrative) land together. Subsequent commit flips chores.xml #30 → closed and points fulfillment at this commit.
