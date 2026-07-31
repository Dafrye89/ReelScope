from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _quiet_windowed_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def _candidate_ffmpeg_pairs() -> list[tuple[Path, Path]]:
    configured_ffmpeg = os.environ.get("VIDEO_FRAMES_FFMPEG")
    configured_ffprobe = os.environ.get("VIDEO_FRAMES_FFPROBE")
    pairs: list[tuple[Path, Path]] = []
    if configured_ffmpeg and configured_ffprobe:
        pairs.append((Path(configured_ffmpeg), Path(configured_ffprobe)))

    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    pairs.extend(
        [
            (
                user_profile / "anaconda3" / "Library" / "bin" / "ffmpeg.exe",
                user_profile / "anaconda3" / "Library" / "bin" / "ffprobe.exe",
            ),
            (program_data / "chocolatey" / "bin" / "ffmpeg.exe", program_data / "chocolatey" / "bin" / "ffprobe.exe"),
        ]
    )
    return pairs


def _configure_engine() -> str:
    for ffmpeg, ffprobe in _candidate_ffmpeg_pairs():
        if not ffmpeg.is_file() or not ffprobe.is_file():
            continue
        try:
            completed = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-hwaccels"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0 and "cuda" in completed.stdout.lower():
            os.environ["VIDEO_FRAMES_FFMPEG"] = str(ffmpeg)
            os.environ["VIDEO_FRAMES_FFPROBE"] = str(ffprobe)
            os.environ["VIDEO_FRAMES_ENGINE"] = "CUDA"
            return "CUDA"

    os.environ["VIDEO_FRAMES_ENGINE"] = "CPU"
    return "CPU"


def _configure_data_dir() -> Path:
    source_dir = Path(__file__).resolve().parent
    source_history = source_dir / "web_data_cuda"
    if not getattr(sys, "frozen", False) and source_history.is_dir():
        data_dir = source_history
    else:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data_dir = local_app_data / "ReelScope" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("VIDEO_FRAMES_DATA_DIR", str(data_dir))
    return data_dir


def _show_startup_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "ReelScope could not start", 0x10)
    except Exception:
        pass


def main() -> None:
    _quiet_windowed_streams()
    _configure_data_dir()
    engine = _configure_engine()

    try:
        if engine == "CUDA":
            import web_app_cuda  # noqa: F401

        import webview
        from web_app import JOBS_DIR, app

        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        storage_path = Path(os.environ["VIDEO_FRAMES_DATA_DIR"]).parent / "webview"
        storage_path.mkdir(parents=True, exist_ok=True)
        webview.create_window(
            "ReelScope",
            app,
            width=1440,
            height=920,
            min_size=(980, 680),
            background_color="#07111f",
            confirm_close=False,
        )
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(storage_path),
        )
    except Exception as exc:  # noqa: BLE001
        _show_startup_error(str(exc))
        raise


if __name__ == "__main__":
    main()
