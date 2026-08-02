# ReelScope DevOps Handoff

Last verified: 2026-08-01  
Repository: <https://github.com/Dafrye89/ReelScope>  
Verified commit: `eff25eb` (`agent/auth-video-transcription`, draft PR #1 at the time of writing)

This document describes what ReelScope is, how it behaves, what it stores, and which production concerns are currently unresolved. It is intentionally not an infrastructure runbook.

## Application summary

ReelScope is an authenticated video-analysis web application. Users upload videos, extract timestamped JPG or PNG frames, inspect the source video and frame carousel/grid, generate editable word-timed SRT transcripts, and download individual or grouped artifacts.

Transcription can use either:

- local Faster-Whisper models on CPU or NVIDIA CUDA; or
- the account owner's ElevenLabs API key with Scribe v2 or v1.

Users can access only jobs and artifacts assigned to their account. Registration is currently open to anyone who can reach `/register`.

## Current runtime shape

| Concern | Current implementation |
|---|---|
| Server framework | Flask 3 |
| Tested runtime | Windows, Python 3.13 |
| Browser runtime | Plain HTML, CSS, and JavaScript; no Node.js runtime is required in production |
| Persistence | Local filesystem plus SQLite in WAL mode |
| Background work | Two in-process `ThreadPoolExecutor` pools |
| Default extraction concurrency | `1` |
| Default transcription concurrency | `1` |
| CPU extraction | OpenCV |
| CUDA extraction | FFmpeg/FFprobe with NVIDIA CUVID decoders |
| Local speech-to-text | Faster-Whisper; CUDA float16 or CPU int8 |
| Cloud speech-to-text | ElevenLabs synchronous batch API, called from a background worker |
| Current web listener | `0.0.0.0:8002` for CPU or `0.0.0.0:8003` for CUDA |
| Built-in web server | Flask development server, threaded, with debug disabled |
| Desktop application | Separate PyInstaller/Edge WebView2 package; not the intended server artifact |

The current launchers are Windows batch files. `run_web.bat` starts the CPU extractor. `run_web_cuda.bat` starts the CUDA extractor and is workstation-specific: it currently expects FFmpeg under `%USERPROFILE%\anaconda3\Library\bin`.

Setting `VIDEO_FRAMES_ENGINE=CUDA` only changes the displayed engine label. CUDA extraction is selected by starting `web_app_cuda.py`, which replaces the extraction function before exposing the Flask application.

## Python dependencies

Runtime dependencies are declared in `requirements.txt`:

- OpenCV
- Flask
- Pillow
- Faster-Whisper and its CTranslate2 runtime
- cryptography
- requests

CI runs on `windows-latest` with Python 3.13. Linux/container hosting has not been validated by this project. Node.js 22 is used by CI only to syntax-check the frontend JavaScript.

## Configuration surface

All environment variables must be present before the application module is imported.

| Variable | Default | Meaning |
|---|---|---|
| `VIDEO_FRAMES_DATA_DIR` | `<application directory>/web_data` | Persistent database, jobs, model cache, and generated secret files |
| `VIDEO_FRAMES_MAX_UPLOAD_MB` | Unlimited | Application-level request size limit; positive integer in MB |
| `VIDEO_FRAMES_WORKERS` | `1` | In-process frame-extraction workers |
| `REELSCOPE_TRANSCRIPTION_WORKERS` | `1` | In-process transcription workers |
| `VIDEO_FRAMES_ENGINE` | `CPU` | UI label only |
| `VIDEO_FRAMES_PORT` | `8003` in CUDA entrypoint | CUDA web listener port |
| `VIDEO_FRAMES_FFMPEG` | Search `PATH` | Exact FFmpeg executable for CUDA extraction |
| `VIDEO_FRAMES_FFPROBE` | Search `PATH` | Matching FFprobe executable |
| `REELSCOPE_STT_DEVICE` | `auto` | `auto`, `cuda`, or `cpu` for local Faster-Whisper |
| `REELSCOPE_AUTO_TRANSCRIBE_MODEL` | `whisper-turbo` | Default local model for accounts without saved settings |
| `REELSCOPE_SESSION_SECRET` | Generated in the data directory | Flask session-signing secret |
| `REELSCOPE_CREDENTIAL_KEY` | Generated in the data directory | Fernet key used to encrypt saved ElevenLabs API keys |
| `REELSCOPE_SECURE_COOKIES` | `0` | Set to `1` when the public origin is HTTPS |

Valid automatic local transcription model keys are:

- `whisper-turbo`
- `distil-large-v3.5`
- `whisper-large-v3`

`REELSCOPE_CREDENTIAL_KEY` must be a valid Fernet key. Losing or changing it makes existing encrypted ElevenLabs keys unreadable. Changing `REELSCOPE_SESSION_SECRET` invalidates existing browser sessions.

## Persistent data

Everything under `VIDEO_FRAMES_DATA_DIR` should be treated as application state.

```text
<data-dir>/
├── reelscope.sqlite3
├── reelscope.sqlite3-wal          # may exist while live
├── reelscope.sqlite3-shm          # may exist while live
├── .session_key                   # generated if not supplied by environment
├── .credential_key                # generated if not supplied by environment
├── models/                        # recreatable Faster-Whisper cache
└── jobs/
    └── <32-character-job-id>/
        ├── upload.<video-extension>
        ├── meta.json
        ├── transcription.json
        ├── transcript.srt
        ├── elevenlabs-transcript.* # optional provider exports
        ├── elevenlabs-entities.json # optional
        └── frames/
            ├── .done
            └── <timestamped frame files>
```

SQLite contains:

- users and scrypt password hashes;
- the mapping between users and job IDs; and
- per-user transcription settings and encrypted ElevenLabs API keys.

The jobs directory contains the original uploaded videos and all derived media. A usable backup/restore therefore needs the database, job directories, and encryption keys as one consistent set. The model cache can be rebuilt.

Important restore behavior:

- Job folders without corresponding ownership rows are not visible to users.
- Ownership rows without a completed `meta.json` and frames produce no usable restored job.
- `manage_users.py --claim-existing` can assign currently unowned job directories to an administrator; this is a recovery action, not an automatic migration.
- The SQLite WAL/SHM files can be active while the process is running, so backup consistency matters.

No schema migration framework is present. Tables are created opportunistically by `AuthStore` during startup.

## Storage and capacity behavior

ReelScope retains all of the following unless they are removed outside the application:

- the full original upload;
- every extracted frame at the chosen sample rate;
- transcripts and optional document exports; and
- downloaded local speech models.

There is currently no job deletion endpoint, retention policy, per-user quota, disk quota, or automatic orphan cleanup. The default upload limit is unlimited. Selecting every frame or lossless PNG can expand a video into a very large number of files.

ZIP downloads are assembled in memory before being returned. Large all-frame exports or concurrent ZIP requests can therefore consume substantial RAM in addition to the disk used by the source and frames.

## Job and scaling behavior

Extraction and transcription queues live only inside the Python process. They are not durable and are not shared between replicas.

Consequences:

- Restarting the process interrupts active extraction and transcription.
- An interrupted upload or extraction can leave an owned database row and partial job directory without a restorable completed job.
- Active job progress is stored in process memory; completed jobs are reconstructed from disk.
- Multiple web processes or horizontally scaled replicas do not share active-job state or background queues.
- Local filesystem paths are assumed everywhere; object storage is not currently supported.
- One process with one persistent data directory is the topology the application currently matches.

Increasing worker counts increases concurrent disk, CPU, RAM, GPU, and provider usage. Faster-Whisper also keeps one model loaded globally per process.

## CPU, CUDA, and media requirements

### CPU mode

CPU frame extraction uses OpenCV's video decoder. It does not use the CUDA FFmpeg path.

### CUDA mode

CUDA frame extraction requires:

- an NVIDIA driver visible to the application process;
- FFmpeg and matching FFprobe executables;
- `ffmpeg -hwaccels` to report `cuda`; and
- an available CUVID decoder for the uploaded codec.

Configured CUVID codecs are AV1, H.264, HEVC, MJPEG, MPEG-1/2/4, VC-1, VP8, and VP9. An unsupported codec fails that job; the CUDA extractor does not automatically fall back to CPU.

Local Faster-Whisper has separate GPU detection. With `REELSCOPE_STT_DEVICE=auto`, it attempts CUDA float16 first and then CPU int8. Explicitly forcing `cuda` disables that fallback.

## Network dependencies

The application does not require a CDN or frontend package service at runtime.

Outbound access can be required for:

- downloading Faster-Whisper model files from Hugging Face on first local use; and
- `https://api.elevenlabs.io/v1/user` and `/v1/speech-to-text` when a user saves an ElevenLabs key or chooses cloud transcription.

When ElevenLabs is selected, the original user-owned video is uploaded to ElevenLabs. This may consume the user's provider quota, and optional keyterm/entity/speaker features can add provider surcharges.

Video playback uses conditional file responses and should retain byte-range behavior through the public delivery path. Large browser uploads and long downloads are normal application traffic.

## Authentication and security behavior

Implemented controls:

- username/password registration and login;
- scrypt password hashes;
- signed, HTTP-only, SameSite=Lax sessions;
- a 14-day permanent session lifetime;
- CSRF checks on POST, PUT, PATCH, and DELETE requests;
- per-user ownership checks for videos, frames, transcripts, and exports;
- encrypted per-user ElevenLabs API keys that are never returned to the browser;
- no-store responses, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a no-referrer policy, and a restrictive camera/microphone/location permissions policy.

Current limitations that matter before public exposure:

- Registration is open and has no approval or invitation mode.
- There is no login/registration rate limiting, lockout, CAPTCHA, MFA, email verification, or password-reset flow.
- Upload validation is primarily extension-based before the decoder examines the file.
- There is no malware scanning, content moderation, or abuse workflow.
- There is no audit log or security-event stream.
- The application does not terminate TLS and does not set HSTS.
- Secure cookies are opt-in through `REELSCOPE_SECURE_COOKIES=1`.
- There is no Content Security Policy header.
- The built-in Flask server is explicitly described by the project as suitable for a trusted local network, not as the final public serving layer.

The `is_admin` role currently adds access to an owned-job debug endpoint and an Admin badge. It is not a global superuser view of every user's videos.

The development ElevenLabs key used for live testing should be rotated before production. No API key or administrator password belongs in the repository, image, service definition, or handoff document.

## Accounts and initial administration

Users self-register with a username and password. Usernames are 3-32 characters and support letters, numbers, dot, dash, and underscore. Passwords are 8-128 characters.

Administrators are created or reset with `manage_users.py`, reading the password from standard input. The command must point at the same `VIDEO_FRAMES_DATA_DIR` as the running application. `--claim-existing` is optional and changes ownership only for unowned job directories.

There is no browser-based user administration, password reset, account disable, account deletion, or registration toggle.

## Health, logging, and observability

Current state:

- There is no dedicated unauthenticated `/health` endpoint.
- There is no readiness endpoint for data-directory write access, SQLite, FFmpeg/CUDA, model availability, disk space, or external providers.
- There are no application metrics, traces, structured logs, queue-depth metrics, or built-in alerts.
- Flask access/error output goes to standard output and standard error.
- Per-job extraction errors are stored in memory while active; transcription state/errors are written to each job's `transcription.json`.

The login page can prove that the HTTP process responds, but it does not prove that uploads, persistence, extraction, GPU access, local transcription, or ElevenLabs are operational. Public ingress availability and end-to-end application health are separate signals.

## Public delivery considerations

These are requirements and constraints, not a prescribed platform:

- The public origin needs HTTPS before secure cookies are enabled.
- The application currently binds to all interfaces; the intended internal exposure boundary should be explicit.
- Uploaded videos and generated frames are private user content and should not be directly exposed from the filesystem.
- A public reverse proxy or ingress must account for large request bodies, long downloads, conditional/range responses, and no-cache headers.
- The data directory, SQLite database, encryption keys, and media files require host-level access controls.
- The app has no reason to expose SQLite, management interfaces, or GPU/runtime control ports publicly.
- A tunnel or reverse proxy proves routing, not application health; off-host availability checks and host/storage/backup monitoring remain separate concerns.

## Decisions for the product owner and operator

The deployment owner needs explicit answers for:

- whether public self-registration should remain enabled;
- who is allowed to use local GPU transcription and ElevenLabs;
- the maximum upload size and accepted workload size;
- per-user storage quotas and job-retention expectations;
- whether original uploads must be retained after extraction;
- backup frequency, retention, restore objectives, and credential-key custody;
- acceptable downtime during process or host restarts;
- whether a single-node deployment is sufficient;
- who pays for ElevenLabs usage and how abuse is handled;
- expected concurrent users, upload volume, and export sizes;
- domain, TLS, ingress, network-segmentation, and monitoring ownership; and
- development credential rotation before go-live.

## Known production gaps

The following are not implemented in the current repository:

- a production web-server configuration;
- durable background jobs or retry scheduling;
- multi-instance coordination;
- object storage;
- health/readiness endpoints;
- structured operational telemetry;
- rate limiting and public-registration controls;
- user/account administration;
- storage quotas, retention, and deletion;
- versioned database migrations;
- automated backup/restore validation;
- Linux/container deployment validation; and
- a production security review or load test.

These gaps do not prevent a controlled low-volume deployment, but they define its operating and risk envelope.

## Validation available in the repository

The standard checks are:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check assets/reelscope.js
python -m py_compile web_app.py web_app_cuda.py reelscope_desktop.pyw
```

At the verified commit, 16 tests passed locally and both GitHub Actions runs passed. The tests cover authentication, CSRF, account isolation, history restoration, frame/video delivery, ZIP/PNG exports, automatic transcription queueing, editable word-timed SRT, encrypted account-scoped ElevenLabs keys, provider option validation, and protected transcript exports.

A live ElevenLabs Scribe v2 test also completed against a 21.08-second video, returned 19 word-timed cues, and synchronized with the playback transcript highlighter. This verifies the integration path, not production capacity or provider availability.

## Source map

| Area | File |
|---|---|
| Main Flask application and routes | `web_app.py` |
| CUDA Flask entrypoint | `web_app_cuda.py` |
| Accounts and SQLite schema | `auth_store.py` |
| CPU extraction | `frame_extractor.py` |
| CUDA FFmpeg extraction | `frame_extractor_cuda.py` |
| Local Faster-Whisper transcription | `transcriber.py` |
| ElevenLabs integration | `elevenlabs_transcriber.py` |
| SRT parsing/editing | `transcript_store.py` |
| User/admin utility | `manage_users.py` |
| Web UI | `templates/` and `assets/` |
| Windows launchers | `run_web.bat`, `run_web_cuda.bat` |
| Automated tests | `tests/` |
| CI and release workflows | `.github/workflows/` |

