# 2026-05-11 — IPEX-LLM GPU-accelerated Ollama reference (Meteor Lake + WSL2 Debian)

Concrete-state reference for IPEX-LLM SYCL-accelerated Ollama on Intel iGPU under WSL2 Debian. Composed from the maintainer's setup history (`~/history.bak` lines 4730–5256) plus chore-#30 debugging findings (this same date). Intended as a teardown-and-rebuild guide for other workstations, and a known-good baseline to revert to when debugging future regressions.

This is not a chronological session log — it's the *target end state*. The closing section ("Pitfalls + anti-patterns") records what went wrong, so re-installers can avoid the same dead ends.

## 1. Hardware + OS prerequisites

| Component | This workstation | Tested values |
| --- | --- | --- |
| Host OS | Windows 11 | WSL2 GPU paravirtualization requires Win10 21H2+ or Win11 |
| WSL distro | Debian Trixie | Ubuntu 22.04+ also works; older Debian/Ubuntu may not have new-enough Intel L0/OpenCL packages |
| iGPU | Intel Arc Graphics 0x7d55 (Meteor Lake Xe-LPG) | Anything from Tiger Lake forward should work with the same stack; older (Gen9/Gen11) needs older driver bundles |
| WSL kernel | 6.6.114.1-microsoft-standard-WSL2 | `CONFIG_DXGKRNL=y` must be set (verify via `zcat /proc/config.gz \| grep DXGKRNL`) |

**Windows-side prerequisite:** the host must have an up-to-date Intel iGPU driver installed (via Intel Driver & Support Assistant or Windows Update). The Linux-side L0 driver talks to Windows DirectX via `libdxcore.so`; if the Windows driver is stale or missing, all the Linux stack is futile.

**WSL device nodes:**
- `/dev/dxg` (Microsoft DirectX paravirt device): **required**. Created automatically by WSL2 when GPU is supported.
- `/dev/dri/` (standard DRM nodes): **not required** for this stack. IPEX-LLM's `libur_adapter_level_zero.so.0` reaches the GPU via `libze_intel_gpu.so` → `libdxcore.so` → `/dev/dxg`, completely bypassing DRM. If `/dev/dri/` is missing, do nothing — it's a non-signal.

## 2. APT repositories

One source list file. Intel's official oneAPI repo:

```sh
# /etc/apt/sources.list.d/oneAPI.list
deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main
```

Keyring install (from Intel's docs):
```sh
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
  | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
  | sudo tee /etc/apt/sources.list.d/oneAPI.list
sudo apt update
```

The maintainer also has a *disabled* `intel-gpu-jammy.list.disabled` from an earlier attempt at Intel's Ubuntu-jammy GPU repo. **Do not re-enable it** — Debian's native `intel-opencl-icd` package supersedes it and the Ubuntu repo's packages conflict with Debian Trixie's library versions.

## 3. APT packages (the canonical set)

GPU userspace + compiler frontend:
```sh
sudo apt install \
  intel-opencl-icd \
  libze1 \
  libze-intel-gpu1 \
  libigc1 libigc2 \
  libigdgmm12 \
  libigdfcl1 libigdfcl2 libigdfcl2-dev \
  libopencl-clang22.1 \
  ocl-icd-libopencl1 \
  clinfo
```

oneAPI runtime (pulled by depends, but worth being explicit):
```sh
sudo apt install \
  intel-oneapi-runtime-opencl \
  intel-oneapi-runtime-dpcpp-sycl-opencl-cpu \
  intel-oneapi-runtime-dpcpp-cpp \
  intel-oneapi-runtime-tbb \
  intel-oneapi-runtime-openmp
```

Verify the right versions landed:
```sh
dpkg -l | grep -E '(intel-opencl-icd|libze-intel|libze1|libigdgmm|libigc|libopencl-clang|ocl-icd)'
```

Expected output should match what's on this workstation today (versions may drift, but presence of all packages is the invariant):
```
intel-opencl-icd        26.05.37020.3-1
libigc1:amd64           1.0.17791.18+1-3
libigc2:amd64           2.28.4-4
libigdfcl1:amd64        1.0.17791.18+1-3
libigdfcl2:amd64        2.28.4-4
libigdfcl2-dev:amd64    2.28.4-4
libigdgmm12:amd64       22.10.0+ds1-1
libopencl-clang22.1     22.1.0-1+b1
libze-intel-gpu1        26.05.37020.3-1
libze1:amd64            1.28.2-2
ocl-icd-libopencl1      2.3.3-1
```

**Critical version-coupling invariant**: `libze-intel-gpu1` and `libigdgmm12` are co-released. They must be the **Debian-packaged** versions, not from-source builds (see Pitfalls §11).

OpenCL ICD vendor registration (Debian-packaged):
```sh
ls /etc/OpenCL/vendors/
# Expected: intel.icd, intel64.icd (both point to libigdrcl.so)
cat /etc/OpenCL/vendors/intel.icd
# Expected: /usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so
```

`intel64.icd` is a symlink to `/etc/alternatives/opencl-intel-runtime-icd` managed by `update-alternatives` — Debian-native; leave it alone.

## 4. IPEX-LLM Ollama bundle

Self-contained tarball from IPEX-LLM releases. The currently-installed version:
- **Bundle:** `ollama-ipex-llm-2.3.0b20250725-ubuntu.tgz`
- **Source:** https://github.com/intel-analytics/ipex-llm/releases (the `ollama-ipex-llm-<version>-ubuntu.tgz` asset)
- **Extracted to:** `~/.local/share/ollama/`
- **Bundled libraries (do NOT touch):**
  - `libsycl.so.8` — Intel SYCL runtime
  - `libggml-sycl.so` — ggml's SYCL backend
  - `libmkl_sycl_blas.so.5`, `libmkl_intel_ilp64.so.2`, `libmkl_tbb_thread.so.2`, `libmkl_core.so.2` — Intel MKL
  - `libur_loader.so.0`, `libur_adapter_level_zero.so.0` — Intel Unified Runtime + L0 adapter
  - `libtbb.so.12`, `libimf.so`, `libsvml.so`, `libintlc.so.5`, `libiomp5.so`, `libirng.so` — Intel runtime libs
  - `libdnnl.so.3` — oneDNN
  - CPU-fallback ggml backends: `libggml-cpu-{alderlake,haswell,icelake,skylakex,sapphirerapids}.so` (symlinked from `libggml-cpu.so` to the host-appropriate one)

The bundle is **fully self-contained**: it ships its own complete oneAPI runtime so it doesn't depend on the system oneAPI install. `LD_LIBRARY_PATH=~/.local/share/ollama` (set in `start-ollama.sh`) is all that's needed for runtime resolution.

Models live at `~/.local/share/ollama/.ollama/` (the bundle's `.ollama` subdir is the equivalent of `~/.ollama` for a standard install).

The bundle ships a SYCL device-probe tool to verify GPU visibility:
```sh
cd ~/.local/share/ollama
./ls-sycl-device
# Expected: "Found 1 SYCL devices: ... Intel Graphics [0x7d55] ... level_zero:gpu:0"
```

## 5. `start-ollama.sh` (env + invocation)

Lives at `~/.local/share/ollama/start-ollama.sh`. Current canonical content:

```bash
#!/bin/bash
export OLLAMA_NUM_GPU=999
export no_proxy=localhost,127.0.0.1
export ZES_ENABLE_SYSMAN=1
# export OLLAMA_KEEP_ALIVE=10m
# ^ DELIBERATELY DISABLED: when set as an env var, it overrides per-request
# keep_alive=0 and blocks programmatic model eviction. The runner's default
# 5-minute idle timer is sufficient.

# IPEX-LLM-recommended SYCL perf tweak. May regress under some workloads;
# remove if encountering hangs that don't reproduce without it.
export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1

export OLLAMA_HOST='127.0.0.1:11434'
export ONEAPI_DEVICE_SELECTOR=level_zero:0
# ^ pin to the first L0 device (Intel iGPU). Multi-GPU machines may want
# `level_zero:*` or specific indices.

# Single-stream constraint — IPEX-LLM on Meteor Lake iGPU degrades under parallel
# requests because the iGPU has no parallel-execution units to share.
export OLLAMA_NUM_PARALLEL=1
unset SYCL_CACHE_PERSISTENT
# ^ disable SYCL kernel cache (filesystem-backed compiled-kernel cache). On WSL
# the cache file lives on the Windows-backed filesystem and adds I/O latency
# on warm-start that exceeds the kernel-recompilation cost of cold-start.

# [debug] Uncomment for diagnostic-level SYCL kernel logging. Produces
# extremely high log volume during inference (~10K kernel calls per request)
# but is the ONLY way to see what kernels are firing when the SYCL backend
# wedges or returns silently.
# export OLLAMA_DEBUG=1
# export GGML_SYCL_DEBUG=1

./ollama serve
```

The script is what the systemd unit invokes. Its `export`s only apply to the `./ollama serve` child process — checking `/proc/<systemd-MainPID>/environ` will *not* show them, because the bash interpreter at MainPID is the parent. Check `/proc/<ollama-serve-PID>/environ` instead.

## 6. systemd service

```ini
# /etc/systemd/system/ollama.service
[Unit]
Description=Ollama (IPEX-LLM SYCL-accelerated)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ramda
Group=ramda
WorkingDirectory=/home/ramda/.local/share/ollama
ExecStart=/home/ramda/.local/share/ollama/start-ollama.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Install + enable:
```sh
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
systemctl status ollama
```

Logs flow to journald, prefixed `start-ollama.sh[<PID>]`:
```sh
journalctl -u ollama -f
journalctl -u ollama -n 50 --no-pager
```

## 7. PATH integration

Profile script puts the bundle's `ollama` wrapper script on `PATH` for interactive shells:
```sh
# /etc/profile.d/ollama.sh
export PATH="/home/ramda/.local/share/ollama:${PATH}"
```

The wrapper at `~/.local/share/ollama/ollama` is part of the IPEX-LLM bundle — it sets `LD_LIBRARY_PATH` to the bundle dir before exec'ing `ollama-bin`, so manual `ollama list` / `ollama pull <model>` etc. from a terminal work without the systemd service in the picture.

(Optional, maintainer-specific) Nushell autoload helper:
```nu
# ~/.config/nushell/autoload/ollama.nu
use std/util "path add"
path add ($nu.home-dir | path join .local share ollama)
```

## 8. Verification chain (rebuild-time sanity)

After install or after any "did I break the GPU" incident, run these in order. Each step is independent — failure at step N tells you what to fix without continuing:

```sh
# (a) Device visibility — does the SYCL runtime see the iGPU?
cd ~/.local/share/ollama && ./ls-sycl-device
# Expected: "Found 1 SYCL devices: ... Intel Graphics [0x7d55] ... level_zero:gpu:0"

# (b) Daemon health — is the systemd service up?
systemctl is-active ollama
# Expected: "active"

# (c) GPU-detection path — does ollama's startup probe find the iGPU?
journalctl -u ollama -n 50 --no-pager | grep -E '(GPU|sycl|library)'
# Expected: "using Intel GPU" line. The "inference compute id=0 library=cpu"
# line that follows is a known mislabel — IPEX-LLM doesn't update ollama's
# upstream-GPU-detection labels (which only know nvidia/amd/vulkan).

# (d) Functional test — text-only inference (no vision tower).
curl -sS http://localhost:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:0.5b","messages":[{"role":"user","content":"Reply with: OK"}],"stream":false}' \
  | jq -r '.message.content + " | " + (.total_duration | tostring) + " ns"'
# Expected: response in <10s on warm load. >60s = CPU fallback.

# (e) Vision-tower test — image inference.
# (run /tmp/native_bytes_probe.py or any image-bearing /api/chat call against
# qwen2.5vl:3b. Expected: ~15s wall-clock at 1812px native, ~5-8s at 512px.)
```

The Windows Task Manager → Performance → GPU panel is the most authoritative ground-truth: if the iGPU "Compute_0" engine shows activity during a `/api/chat` call, GPU acceleration is working. CPU-only inference shows zero GPU activity.

## 9. Model management

Models live at `~/.local/share/ollama/.ollama/` (bundle-internal). Standard `ollama pull <model>` commands work via the PATH-injected wrapper from §7.

Vision-language models tested on this workstation:
- `qwen2.5vl:3b` — ~5GB, 4-bit quant, ~15s/page at native dimensions (1812×1546, ~2MB JPG). Use for development/dev-eval.
- `qwen2.5vl:7b` — ~8GB, 4-bit quant, ~100s/page at native dimensions. Production-recommended per chore #13 eval (77.1% accuracy on handwriting OCR vs MiniCPM-V's 37%).
- `minicpm-v` — eliminated from production after chore #13 eval; do not pull on fresh installs unless re-evaluating.

Text-only models for testing:
- `qwen2.5:0.5b` — ~400MB, sub-second responses, ideal for daemon-health smoke tests.

## 10. Daemon control patterns

```sh
# Restart after env or service-file edit
sudo systemctl daemon-reload && sudo systemctl restart ollama

# Watch for GPU/SYCL activity in real time
journalctl -u ollama -f | grep -E '(sycl|GPU|library|ggml_)'

# Manually evict a loaded model (does NOT work if OLLAMA_KEEP_ALIVE env var is set
# in start-ollama.sh — that override has been disabled by design)
curl -sS -X POST http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5vl:7b","keep_alive":0}'

# Check what's resident
curl -sS http://localhost:11434/api/ps | jq '.models[] | {name, vram: .size_vram, expires: .expires_at}'

# Kill a wedged runner without restarting the daemon (forces a clean re-spawn
# on the next /api/chat request)
pgrep -f 'ollama-bin runner' | xargs -r kill
```

## 11. Pitfalls + anti-patterns

These are mistakes made (or considered) during the chore-#30 debugging session that produced this reference. Avoid on fresh installs:

### Do NOT build `gmmlib` from source

`libigdgmm12` ships with Debian (`/usr/lib/x86_64-linux-gnu/libigdgmm.so.12`, ~935KB stripped release build). The from-source build of intel/gmmlib master into `/usr/local/lib/libigdgmm.so.12.10.0` (~4MB unstripped) **wins ldconfig priority over the Debian package** and produces silent vision-encoder wedges (Q4_K_M qwen2.5vl:3b infinite hang on >1.9MB image inputs). The `libze-intel-gpu1` package was compiled against a specific gmmlib version; the from-source version is ABI-similar but allocator-path-different, and large 2D tensor allocations (vision-tower patch embedding) hit the divergence.

If you've already done this:
```sh
sudo rm /usr/local/lib/libigdgmm.so /usr/local/lib/libigdgmm.so.12 /usr/local/lib/libigdgmm.so.12.10.0
sudo ldconfig
ldconfig -p | grep igdgmm
# Expected: ONLY /lib/x86_64-linux-gnu/libigdgmm.so.12 — NO /usr/local hit.
```

### Do NOT manually register the OpenCL ICD loader as a vendor

The Debian-packaged `intel-opencl-icd` already creates `/etc/OpenCL/vendors/intel.icd` and `intel64.icd` pointing at the correct vendor library (`/usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so`). **Adding a `loader.icd` file that points to the OpenCL loader itself** (e.g. `libOpenCL.so`) creates a self-reference loop — the ICD dispatcher loads itself as a vendor and either crashes or returns no platforms.

The specific broken command from history is:
```sh
sudo bash echo "/.../libOpenCL.so" > /etc/OpenCL/vendors/loader.icd  # WRONG
```
That command is also double-broken: `sudo bash echo` runs `bash` with `echo` as a script filename (which fails), and the `>` redirect runs in the current shell (without sudo). If somehow created anyway:
```sh
sudo rm /etc/OpenCL/vendors/loader.icd
```

### Do NOT set `OLLAMA_KEEP_ALIVE` in `start-ollama.sh`

When set as a daemon-level env var, it overrides per-request `keep_alive=0`, blocking programmatic model eviction. Comment out or remove. The runner's default 5-minute idle timer handles unload cases adequately, and the override prevents test harnesses from forcing clean state between candidates.

### Do NOT chase `/dev/dri/`

It will probably not exist on WSL2 even when GPU acceleration works. The Intel L0 driver uses `libdxcore.so` → `/dev/dxg` → Windows DirectX, which is parallel to the standard DRM device path. `wsl --shutdown` and similar attempts to "fix" the missing `/dev/dri/` are no-ops. Run `./ls-sycl-device` from the IPEX-LLM bundle; if it lists the GPU, you have GPU access regardless of `/dev/dri/`.

### Do NOT trust ollama's `library=cpu` log line

Upstream Ollama's GPU detection module only knows about CUDA, ROCm, and Vulkan. IPEX-LLM slots its SYCL backend in below that detection layer, so the user-visible log line will *always* say `library=cpu` even when SYCL inference is running at full GPU speed. The authoritative signals are: (a) `using Intel GPU` line during startup, (b) `call ggml_sycl_*` lines during inference (only visible with `GGML_SYCL_DEBUG=1`), (c) wall-clock comparison against CPU baseline, (d) Windows Task Manager GPU activity.

### Do NOT use upstream Ollama and IPEX-LLM Ollama on the same machine

The `/usr/local/bin/ollama` and `/usr/share/ollama/.ollama/` paths from the upstream installer conflict with the bundle. The maintainer's history (lines 4847–4877) shows the migration: stop+disable+uninstall the upstream service, move the upstream `.ollama/` models dir to `~/.local/share/ollama/.ollama/`, then deploy the IPEX-LLM bundle. Verify only one ollama install via `which ollama` and confirm it resolves to the bundle path.

### Avoid manually re-symlinking SYCL versions

The maintainer's history (lines 8089–8104) shows recovery from a broken `libsycl-preview.so.9` symlink chain. The bundle's bundled `libsycl.so.8` is what's actually used at inference time — the oneAPI-installed `libsycl-preview.so.9` is for compilation, not runtime. If you see SYCL version-confusion, prefer reinstalling the bundle over manual `ln -s` reconstruction.

## 12. Provenance + cross-references

- **History source:** `~/history.bak` (~9K lines of maintainer's nushell history); relevant lines: 4730–5256 (initial setup), 8643–8810 (debugging), 8089–8104 (sycl-preview recovery).
- **Today's debugging chain:** chore #30 close-out — see `2026-05-11-chore-30-resolution.md` (the diagnostic narrative).
- **Auto-memory note:** `~/.claude/projects/-home-ramda-code-trust-generator/memory/project_wsl2_gpu_compute_dead_end.md` — superseded by this doc; should be revised to point here.
- **Earlier OCR eval session:** `docs/session-notes/2026-04-30-vision-model-eval.md` — chore #13 eval that established qwen2.5vl:7b as production-recommended.
- **Project consumer:** `src/trust_generator/v3/extraction/ollama_backend.py` — the production-side `OllamaBackend` that uses this stack via the documented HTTP API at `http://localhost:11434`.
