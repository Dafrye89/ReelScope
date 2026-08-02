# ReelScope

<img src="assets/reelscope-icon-256.png" alt="ReelScope icon" width="96" />

ReelScope is a private, local-first video workspace for Windows. Drop in a video, extract exact frames with CPU or NVIDIA CUDA acceleration, scrub or play the source video, reopen past jobs, create timestamped SRT transcripts, and export a single PNG or sampled ZIP.

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

For server ownership, persistence, security boundaries, capacity behavior, and known production gaps, see [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md).

## Privacy, data, and network use

ReelScope has no analytics or telemetry. Frame extraction and local Whisper transcription remain on the host. When a user selects ElevenLabs, ReelScope sends only that user's source video and chosen speech-to-text options to the ElevenLabs API. Browser mode binds to all local interfaces by default so registered users on the LAN can reach it. The built-in server is intended for a trusted local network; before exposing it to the public internet, place it behind an HTTPS reverse proxy and set `REELSCOPE_SECURE_COOKIES=1`.

## License

ReelScope is released under the [MIT License](LICENSE). Bundled font and icon licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
