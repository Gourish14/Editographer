# 03 — Tech stack (all free)

## Already on the machine

| Tool | Version found | Used for |
| --- | --- | --- |
| Java | 25.0.1 LTS | Spring Boot backend |
| Node.js | 24.19.0 | Building the Angular app |
| Python (system) | 3.13.9 | Not used by the worker (see below) |
| NVIDIA driver | installed | CUDA for PyTorch, NVENC for encoding |

## Installed by `setup.bat`

| Tool | How | Why |
| --- | --- | --- |
| uv | official installer, into `tools/uv` | Creates a private Python 3.12 (`tools/python`) used by `worker/.venv` (some AI libraries are not yet stable on 3.13) |
| FFmpeg (full build with NVENC) | `winget install Gyan.FFmpeg`, or portable copy into `tools/ffmpeg` | Decode, encode, filters, v360 |
| Ollama | `winget install Ollama.Ollama` | Local LLM runtime |

## Frontend

| Component | Tool | License |
| --- | --- | --- |
| Framework | Angular (latest) + Angular Material | MIT |
| Resumable uploads | tus-js-client | MIT |
| Waveform and beat preview | wavesurfer.js | BSD-3 |
| 360 clip preview | three.js (equirect sphere viewer) | MIT |

## Backend

| Component | Tool | License |
| --- | --- | --- |
| Framework | Spring Boot 4 (Web, Data JPA, Validation, Scheduling) | Apache-2.0 |
| Database | H2 (file mode) + Flyway migrations | MPL-2.0 / EPL-1.0, Apache-2.0 |
| Uploads | tus-java-server | MIT |
| Live progress | Spring `SseEmitter` | Apache-2.0 |
| HTTP client to worker | Spring `RestClient` | Apache-2.0 |

## Worker (Python 3.12)

| Component | Tool | License |
| --- | --- | --- |
| API | FastAPI + Uvicorn | MIT / BSD-3 |
| ML runtime | PyTorch (CUDA build) | BSD |
| Video I/O | FFmpeg + PyAV | LGPL/GPL / BSD |
| Beats and downbeats | [Beat This!](https://github.com/CPJKU/beat_this) | MIT |
| Energy, onsets | librosa | ISC |
| Shot detection | PySceneDetect | BSD-3 |
| Faces and pose | MediaPipe | Apache-2.0 |
| Object detection | Ultralytics YOLO (nano) | AGPL-3.0 |
| Tags and aesthetics | OpenCLIP ViT-B/32 | MIT |
| Cutout and tracking | [SAM 2.1](https://ai.meta.com/blog/segment-anything-2/) small | Apache-2.0 |
| Photo depth | [Depth Anything V2 Small](https://github.com/DepthAnything/Depth-Anything-V2) through Transformers | Apache-2.0 (Small only) |
| Frame interpolation | [Practical-RIFE](https://github.com/hzwer/Practical-RIFE) 4.25 (model definition vendored in `worker/app/adapters/vendor/`) | MIT |
| Upscaling | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) realesr-general-x4v3 (model definition vendored in `worker/app/adapters/vendor/`) | BSD-3 |
| Effects and transitions | ModernGL shaders + gl-transitions | MIT |
| Equirect ↔ cube faces | py360convert | MIT |
| Text rendering | skia-python | BSD-3 |
| Speech captions | faster-whisper (small) | MIT |
| Loudness | pyloudnorm | MIT |
| Content hash | xxhash | BSD-2 |
| Optical flow, sharpness | OpenCV (headless) | Apache-2.0 |
| GPU monitoring | nvidia-ml-py (NVML) | BSD-3 |

## AI director (Ollama)

| Role | Model | License |
| --- | --- | --- |
| Planner | Qwen3 4B, 4-bit (`qwen3:4b`) | Apache-2.0 |
| Shot captions | Qwen2.5-VL 3B, 4-bit (`qwen2.5vl:3b`) | check model card before commercial use |

## Free assets from DJI

| Asset | Use |
| --- | --- |
| DJI official D-Log M to Rec.709 LUT | Normalize Osmo D-Log M footage |
| DJI Studio / DJI Mimo | Optional stitched 360 export |

## Vendored model definitions

Practical-RIFE is not a package, and the `realesrgan` package replaces the CUDA build of PyTorch with a CPU one. So the worker keeps only the two small network definitions, with their licenses next to them. The RIFE 4.25 weights come from the `vs-rife` release because upstream publishes them only on Google Drive; the file has the same SHA-256 as `flownet.pkl` in the upstream 4.25 archive.

## License note

YOLO (AGPL-3.0) is fine for personal, local use. If the app is ever sold or offered as a public service, swap YOLO for an Apache-licensed detector (e.g. RT-DETR) or comply with AGPL.
