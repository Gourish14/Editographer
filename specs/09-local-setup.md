# 09 — Local setup (Windows laptop, RTX 3050 6 GB)

## Target machine

| Item | Value |
| --- | --- |
| OS | Windows 11 |
| GPU | NVIDIA RTX 3050 Laptop, 6 GB VRAM |
| Java | 25.0.1 (installed) |
| Node.js | 24.19.0 (installed) |
| Python | 3.13.9 system; worker uses a private 3.12 via uv |
| RAM | 16 GB minimum, 32 GB recommended |
| Disk | Fast NVMe with plenty of space (8K `.OSV` ≈ 16 GB each) |

## 6 GB VRAM model profile

Only one AI model is on the GPU at a time (`GpuGuard` in `worker/app/adapters/nvml_gpu_guard.py` holds a lock; each stage loads its model, processes everything in a batch, then unloads and calls `torch.cuda.empty_cache()`).

| Stage | Model | Approx. VRAM | Setting |
| --- | --- | --- | --- |
| Beats | Beat This! (small) | CPU | — |
| Shots, faces, objects | PySceneDetect, MediaPipe, YOLO nano | < 1 GB | Proxies only |
| Tags and aesthetics | OpenCLIP ViT-B/32 | < 1 GB | Batch 32 frames |
| Shot captions | Qwen2.5-VL 3B, 4-bit | ≈ 3 GB | Top 40 shots only |
| AI director | Qwen3 4B, 4-bit | ≈ 3 GB | Ollama `keep_alive: 0` |
| Cutout and tracking | SAM 2.1 small | ≈ 1–2 GB | Only segments that need it |
| Photo depth | Depth Anything V2 Small | < 1 GB | — |
| Slow-mo | RIFE 4.x | ≈ 1–2 GB | `scale 0.5` above 4K |
| Upscale | Real-ESRGAN realesr-general-x4v3 | ≈ 1–2 GB | Tiles of 512 px, fp16 |
| Encode | FFmpeg `hevc_nvenc` | dedicated chip | 10-bit |

## Speed rules

- **Proxies:** all analysis runs on 720p proxies or Osmo `.LRF`.
- **Analysis cache:** keyed by file hash; a new version or ratio skips straight to planning.
- **Render only what is used:** only the chosen windows are decoded, interpolated, upscaled and encoded.
- **Hardware decode/encode:** NVDEC for decoding, NVENC for encoding.
- **Preview first:** 1080p preview before the final render.

## Render modes

Rough times for a 60-second edit on this laptop:

| Mode | What it does | Approx. time |
| --- | --- | --- |
| Preview | 1080p, all cuts and effects, simple scaling | 2–5 min |
| Fast (default) | Target resolution with Lanczos + sharpening; RIFE only on slow-mo segments | 4K ≈ 5–15 min |
| Max quality | Real-ESRGAN upscaling + full RIFE | 6K/8K ≈ 45 min or more |

## Cool mode

Toggle in render settings. When on:
- One job at a time (always true) plus a 10 s pause between GPU stages.
- NVML temperature watch every 2 s: pause at 83 °C, resume at 75 °C.
- Real-ESRGAN tile size drops to 256 px.
- "Render tonight" option: queue the final render to start at a chosen time.

## setup.bat (run once)

1. Check Java ≥ 25, Node ≥ 24.15 and the NVIDIA driver (`nvidia-smi`); stop with a clear message if missing or too old.
2. Install FFmpeg (`winget install Gyan.FFmpeg`) if `ffmpeg -encoders` lacks `hevc_nvenc`, then confirm `hevc_nvenc` really opens in 10-bit.
3. Install Ollama (`winget install Ollama.Ollama`). `ollama pull qwen3:4b` and `ollama pull qwen2.5vl:3b` are added with Phase 2, the first phase that uses them.
4. Install uv into `tools/uv`, then `uv python install 3.12` (into `tools/python`) and `uv sync` in `worker/` (PyTorch CUDA wheels). `scripts/env.bat` points uv at these folders.
5. Download model weights into `models/` with checksums, resuming interrupted downloads. The list lives in `scripts/models.json`, tagged by phase: Beat This! and the MediaPipe face model in Phase 1, YOLO nano, OpenCLIP and the LAION aesthetic head in Phase 2, then SAM 2.1 small, Depth Anything V2 Small, RIFE and Real-ESRGAN with the phases that use them. The worker points torch hub, Hugging Face, Ultralytics and Matplotlib at `models/` before loading them, and sets them offline, which also turns off Ultralytics analytics and its automatic package installs (`adapters/model_runtime.py`).
6. Download free LUTs and SFX into `luts/` and `sfx/` (added with Phase 3 and Phase 4).
7. `npm ci` and `ng build` in `frontend/`, copy the build into `backend/src/main/resources/static/`.
8. `mvnw package` in `backend/`.
9. Create `config/local.env` (ports, paths, random worker token) and the `media/` and `data/` folders.

## start.bat

1. Start Ollama if not running.
2. Start the worker: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8090`.
3. Start the backend: `java -jar backend/target/editographer.jar`.
4. Wait for `/api/system` to answer, then open `http://localhost:8080`.

`stop.bat` stops all three.

## Phone access (optional)

A free Cloudflare Tunnel or Tailscale exposes `http://localhost:8080` to your phone while the laptop does the work.
