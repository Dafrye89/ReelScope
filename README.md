# ReelScope

<img src="assets/reelscope-icon-256.png" alt="ReelScope icon" width="96" />

ReelScope is a private, local-first video workspace for Windows or a self-hosted CPU server. Drop in a video, extract exact frames with CPU or NVIDIA CUDA acceleration, scrub or play the source video, reopen past jobs, create timestamped SRT transcripts, and export a single PNG or sampled ZIP.

![ReelScope desktop workspace](docs/reelscope-preview.png)

## What it does

- Persistent project history with search and instant reopening
- Ratio-aware frame stage for landscape, portrait, square, and ultrawide video
- Filmstrip, grid, keyboard navigation, playback, and precise frame selection
- Original-video playback synchronized to the selected extracted frame
- Automatic speech-to-text for every new upload using local Whisper or an optional per-user ElevenLabs account
- Word-by-word SRT output with live word highlighting beneath the main viewer, timestamp seeking, and in-app correction
- Simple username/password accounts with strict per-user video, frame, export, and transcript isolation
- Light and dark themes
- CPU extraction everywhere; CUDA acceleration when a compatible FFmpeg build and NVIDIA driver are available
- Web UI plus a native Edge WebView2 desktop window with no background command prompt
- Local-first processing: uploads stay on your computer unless their owner explicitly selects ElevenLabs transcription

## Quick start

### CUDA web app

Run `run_web_cuda.bat`, then open `http://localhost:8003`. The launcher pins the CUDA-capable FFmpeg installed at `%USERPROFILE%\anaconda3\Library\bin` so a different FFmpeg earlier on `PATH` cannot be selected accidentally.

### CPU web app

Run `run_web.bat`, then open `http://localhost:8002`.

### Desktop shortcut

From PowerShell:

```powershell
.\install_desktop.ps1 -Launch
```

This creates a `ReelScope` shortcut on the Windows desktop and launches it through `pythonw.exe`, so no console window remains open. When run from source it reuses the existing `web_data_cuda` history.

### Standalone desktop build

```powershell
.\build_desktop.ps1 -InstallShortcut
```

The packaged app is written to `dist\ReelScope\ReelScope.exe`. Packaged builds store their library under `%LOCALAPPDATA%\ReelScope\data`.

## Docker self-hosting (CPU)

Docker Engine with Compose v2 is the only host prerequisite. The provided configuration builds the app, runs it as an unprivileged user with all Linux capabilities removed, keeps the container filesystem read-only, and persists the database, uploads, transcripts, models, session key, and credential-encryption key in one Docker volume.

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

Create the first administrator without placing its password in a command argument. On PowerShell 7:

```powershell
Read-Host "Admin password" -MaskInput | docker compose run --rm reelscope python manage_users.py admin --data-dir /data --password-stdin
```

On Bash:

```bash
read -rsp "Admin password: " password; printf '%s\n' "$password" | docker compose run --rm reelscope python manage_users.py admin --data-dir /data --password-stdin; unset password
```

Open `http://127.0.0.1:8002`. Public registration is disabled by default; set `REELSCOPE_ALLOW_REGISTRATION=1` only if you are prepared to operate a multi-user service.

The default port is bound to loopback, so it is not directly exposed to the LAN or internet. For remote access, keep that restriction and place ReelScope behind an HTTPS reverse proxy or outbound tunnel. Set these values in `.env` for the public hostname:

```dotenv
REELSCOPE_SECURE_COOKIES=1
REELSCOPE_HSTS=1
REELSCOPE_PROXY_HOPS=1
REELSCOPE_TRUSTED_HOSTS=reelscope.example.com,localhost,127.0.0.1
```

Only set `REELSCOPE_PROXY_HOPS` when the app can be reached solely through that exact number of trusted proxies. Keep Gunicorn at one worker: extraction and transcription queues are process-local. Threads handle concurrent HTTP requests while the two bounded background executors serialize CPU-heavy work.

Before an upgrade, stop the service and copy the complete `/data` directory so SQLite and the filesystem remain consistent:

```bash
docker compose stop
docker compose cp reelscope:/data ./reelscope-data-backup
docker compose start
```

Protect that backup like account data. Losing `.session_key` signs everyone out; losing `.credential_key` makes stored ElevenLabs keys unreadable. Test restoration on another machine before relying on the backup.

This is deliberately a low-volume self-hosted design. It does not provide account recovery, storage quotas, automatic retention/deletion, a distributed job queue, or multi-node scaling. The default 95 MB upload cap fits common proxied-service limits; lower it if your reverse proxy or available storage requires that.

## Accounts

Registration asks only for a username and password. Passwords are stored as salted scrypt hashes, browser sessions use a persistent local signing key, and state-changing requests require a CSRF token. A user receives a not-found response when attempting to request another user's job or artifact.

Create or reset an administrator without placing the password in shell history:

```powershell
Read-Host "Admin password" | .\.venv\Scripts\python.exe .\manage_users.py admin --password-stdin --claim-existing
```

Use `--data-dir web_data_cuda` for the CUDA web library, or the packaged data location for a standalone installation. `--claim-existing` assigns only currently unowned jobs to that administrator.

## Local transcription

ReelScope uses Faster-Whisper with three selectable local models. Model files download from Hugging Face on first use and remain in the selected ReelScope data directory.

- **Whisper Large-v3 Turbo** — recommended multilingual speed/accuracy balance
- **Distil-Whisper Large-v3.5** — fastest high-quality English choice
- **Whisper Large-v3** — slower full-size accuracy choice

Every new upload automatically starts transcription with Whisper Large-v3 Turbo after frame extraction completes. Set `REELSCOPE_AUTO_TRANSCRIBE_MODEL` to `distil-whisper` or `whisper-large-v3` to change that default.

Each spoken word becomes its own precisely timed SRT cue. The transcript appears directly beneath the main image or video and highlights the matching word during playback. Click a word timestamp to seek the video, correct any word directly in the workspace, and choose **Save SRT edits** to regenerate the job's subtitle file.

The RTX 3090 path uses CUDA float16. If CUDA model loading is unavailable, ReelScope automatically retries with CPU int8. Transcript text and SRT files remain in the owning user's local job directory.

## Optional ElevenLabs transcription

Each account can choose **ElevenLabs · cloud API** in the Transcription panel, paste its own API key, configure the provider, and save it as the automatic default for future uploads. ReelScope validates the key with ElevenLabs, encrypts it on the server, never returns it to the browser, and keeps the setting isolated to that account. Removing the saved key switches the account back to local transcription.

The panel exposes the ElevenLabs options that apply to ReelScope's synchronous, owned-file workflow: Scribe v2 or v1, language hints, word or character timestamps, audio-event tagging, diarization and speaker settings, multichannel output, logging, temperature, seed, keyterms, entity detection and redaction, and DOCX/HTML/PDF/SRT/TXT/segmented-JSON exports. URL, webhook, single-use-token, and raw PCM transport modes are handled by ReelScope rather than exposed as user settings. Word timing is always retained so playback highlighting continues to work.

Selecting ElevenLabs sends that user's original video to ElevenLabs and may incur usage charges on their ElevenLabs account. Several advanced options have separate provider surcharges; ReelScope labels those options in the panel.

By default, the credential-encryption key is generated once at `<data directory>/.credential_key`. Back up this file with the data directory. A deployment can instead supply a stable Fernet key through `REELSCOPE_CREDENTIAL_KEY`; changing or losing the key makes previously saved API keys unreadable.

## CUDA requirements

ReelScope checks the output of `ffmpeg -hwaccels` and selects CUDA only when the chosen build reports it. The CUDA launcher expects matching `ffmpeg.exe` and `ffprobe.exe` files in the Anaconda installation. The NVIDIA driver must support the decoder used by the source video.

If CUDA is unavailable, the desktop app falls back to the CPU extractor. The web CUDA launcher stops with a clear error instead of silently using an unrelated FFmpeg build.

## Controls

- Left/right arrow: previous or next frame
- Space: play or pause the filmstrip
- Home/End: first or last frame
- `G`: toggle filmstrip/grid view
- Theme button: follow system, light, or dark appearance

## Development

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The UI is plain HTML, CSS, and JavaScript served by Flask. No external CDN is required at runtime.

For server ownership, persistence, security boundaries, capacity behavior, and remaining operational limits, see [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md).

## Privacy, data, and network use

ReelScope has no analytics or telemetry. Frame extraction and local Whisper transcription remain on the host. The first use of a local model downloads its files from Hugging Face. When a user selects ElevenLabs, ReelScope sends only that user's source video and chosen speech-to-text options to the ElevenLabs API. The Windows development server binds to local interfaces and is intended only for a trusted network. Public deployments should use the provided Gunicorn container behind an HTTPS reverse proxy or outbound tunnel.

## License

ReelScope is released under the [MIT License](LICENSE). Bundled font and icon licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
