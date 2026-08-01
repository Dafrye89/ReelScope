# ReelScope

<img src="assets/reelscope-icon-256.png" alt="ReelScope icon" width="96" />

ReelScope is a private, local-first video workspace for Windows. Drop in a video, extract exact frames with CPU or NVIDIA CUDA acceleration, scrub or play the source video, reopen past jobs, create timestamped SRT transcripts, and export a single PNG or sampled ZIP.

![ReelScope desktop workspace](docs/reelscope-preview.png)

## What it does

- Persistent project history with search and instant reopening
- Ratio-aware frame stage for landscape, portrait, square, and ultrawide video
- Filmstrip, grid, keyboard navigation, playback, and precise frame selection
- Original-video playback synchronized to the selected extracted frame
- Automatic local speech-to-text for every new upload, with downloadable SRT subtitles
- Live transcript highlighting during source-video playback, timestamp seeking, and in-app text correction
- Simple username/password accounts with strict per-user video, frame, export, and transcript isolation
- Light and dark themes
- CPU extraction everywhere; CUDA acceleration when a compatible FFmpeg build and NVIDIA driver are available
- Web UI plus a native Edge WebView2 desktop window with no background command prompt
- Local processing: uploaded videos and extracted frames stay on your computer

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

While the original video plays, ReelScope highlights the matching transcript cue. Click a cue timestamp to seek the video, edit any cue directly in the workspace, and choose **Save edits** to regenerate the job's SRT file.

The RTX 3090 path uses CUDA float16. If CUDA model loading is unavailable, ReelScope automatically retries with CPU int8. Transcript text and SRT files remain in the owning user's local job directory.

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

## Privacy, data, and network use

ReelScope has no analytics, cloud upload, or telemetry. Browser mode binds to all local interfaces by default so registered users on the LAN can reach it. The built-in server is intended for a trusted local network; before exposing it to the public internet, place it behind an HTTPS reverse proxy and set `REELSCOPE_SECURE_COOKIES=1`.

## License

ReelScope is released under the [MIT License](LICENSE). Bundled font and icon licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
