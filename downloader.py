"""
VDown.uz Bot — Video yuklab olish moduli
yt-dlp + ffmpeg orqali HLS segmentlarni yuklab olib, MKV ga birlashtiradi.
"""
import os
import asyncio
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from config import DOWNLOAD_DIR, YTDLP_OPTIONS, QUALITY_OPTIONS, MAX_FILE_SIZE
from parsers import is_supported_site, extract_stream_url

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Video yuklab olishda xatolik"""
    pass


class VideoInfo:
    """Video haqida ma'lumot"""

    def __init__(self, data: dict):
        self.title: str = data.get("title", "video")
        self.duration: int = data.get("duration", 0)
        self.url: str = data.get("webpage_url", data.get("url", ""))
        self.thumbnail: str = data.get("thumbnail", "")
        self.filesize_approx: int = data.get("filesize_approx", 0)
        self.formats: list = data.get("formats", [])
        self.ext: str = data.get("ext", "mkv")
        self._raw = data

    @property
    def duration_str(self) -> str:
        """Davomiylikni HH:MM:SS formatda qaytaradi"""
        if not self.duration:
            return "noma'lum"
        h, r = divmod(self.duration, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def available_qualities(self) -> list[str]:
        """Mavjud sifat variantlarini qaytaradi"""
        heights = set()
        for fmt in self.formats:
            h = fmt.get("height")
            if h and h > 0:
                heights.add(h)

        available = []
        for label, _ in QUALITY_OPTIONS.items():
            if label == "best":
                available.append(label)
                continue
            target_h = int(label.replace("p", ""))
            if any(h >= target_h for h in heights):
                available.append(label)

        return available if available else ["best"]


async def get_video_info(url: str) -> VideoInfo:
    """
    Video haqida ma'lumot olish (yuklab olmasdan).
    Avval yt-dlp, keyin maxsus parserlarni sinab ko'radi.

    Args:
        url: Video havolasi

    Returns:
        VideoInfo obyekti

    Raises:
        DownloadError: Video topilmasa
    """
    loop = asyncio.get_running_loop()

    # 1-usul: Avval maxsus parser bilan sinash (o'zbek saytlari uchun)
    if is_supported_site(url):
        def _extract_custom():
            result = extract_stream_url(url)
            if result:
                return result
            return None

        custom_result = await loop.run_in_executor(None, _extract_custom)
        if custom_result:
            stream_url = custom_result["stream_url"]
            title = custom_result.get("title", "Video")
            logger.info(f"Maxsus parser orqali topildi: {title} -> {stream_url}")

            # m3u8 stream uchun yt-dlp bilan info olish
            opts = {
                **YTDLP_OPTIONS,
                "extract_flat": False,
                "skip_download": True,
            }
            if custom_result.get("referer"):
                opts["http_headers"] = {
                    **opts.get("http_headers", {}),
                    "Referer": custom_result["referer"],
                }
            if custom_result.get("headers"):
                opts["http_headers"] = {
                    **opts.get("http_headers", {}),
                    **custom_result["headers"],
                }

            def _extract_stream_info():
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(stream_url, download=False)
                        if info:
                            info["title"] = title  # Asl sarlavha
                            return info
                except Exception as e:
                    logger.warning(f"yt-dlp stream info xatosi: {e}")
                # Fallback: oddiy info
                return {
                    "title": title,
                    "url": stream_url,
                    "duration": 0,
                    "formats": [],
                    "ext": "mkv",
                }

            info = await loop.run_in_executor(None, _extract_stream_info)
            return VideoInfo(info)

    # 2-usul: yt-dlp bilan to'g'ridan-to'g'ri sinash
    opts = {
        **YTDLP_OPTIONS,
        "extract_flat": False,
        "skip_download": True,
    }

    def _extract():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise DownloadError("Video topilmadi")

                # Playlist bo'lsa, birinchi videoni olish
                if "entries" in info:
                    entries = list(info["entries"])
                    if not entries:
                        raise DownloadError("Playlistda video topilmadi")
                    info = entries[0]

                return info
        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Video topilmadi: {e}")
        except Exception as e:
            raise DownloadError(f"Ma'lumot olishda xato: {e}")

    info = await loop.run_in_executor(None, _extract)
    return VideoInfo(info)


async def download_video(
    url: str,
    quality: str = "best",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """
    Videoni yuklab olish va MKV formatga birlashtirish.
    Avval maxsus parser, keyin yt-dlp to'g'ridan-to'g'ri sinab ko'radi.

    Args:
        url: Video havolasi
        quality: Sifat (360p, 480p, 720p, 1080p, best)
        progress_callback: Progress funksiyasi (foiz, holat)

    Returns:
        Yuklab olingan MKV fayl yo'li

    Raises:
        DownloadError: Yuklab olishda xatolik
    """
    loop = asyncio.get_running_loop()

    # Maxsus parser orqali stream URL ni olish
    actual_url = url
    extra_headers = {}

    if is_supported_site(url):
        def _get_stream():
            return extract_stream_url(url)

        stream_info = await loop.run_in_executor(None, _get_stream)
        if stream_info and stream_info.get("stream_url"):
            actual_url = stream_info["stream_url"]
            if stream_info.get("referer"):
                extra_headers["Referer"] = stream_info["referer"]
            if stream_info.get("headers"):
                extra_headers.update(stream_info["headers"])
            logger.info(f"Stream URL: {actual_url}")

    # Unique ID bilan fayl nomi
    download_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOAD_DIR / f"{download_id}_%(title).50s.%(ext)s")

    # Sifat formati
    format_str = QUALITY_OPTIONS.get(quality, QUALITY_OPTIONS["best"])

    opts = {
        **YTDLP_OPTIONS,
        "format": format_str,
        "outtmpl": output_template,
    }

    # Maxsus parser header'larini qo'shish
    if extra_headers:
        opts["http_headers"] = {
            **opts.get("http_headers", {}),
            **extra_headers,
        }

    # Progress hook
    last_percent = [-1]  # mutable for closure

    def _progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percent = int(downloaded / total * 100)
                if percent != last_percent[0] and percent % 5 == 0:
                    last_percent[0] = percent
                    if progress_callback:
                        try:
                            # Async callback ni sync kontekstdan chaqirish
                            loop = asyncio.get_running_loop()
                            if loop.is_running():
                                asyncio.ensure_future(
                                    _async_callback(progress_callback, percent, "downloading")
                                )
                        except Exception:
                            pass

        elif d["status"] == "finished":
            if progress_callback:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        asyncio.ensure_future(
                            _async_callback(progress_callback, 100, "merging")
                        )
                except Exception:
                    pass

    opts["progress_hooks"] = [_progress_hook]

    def _download():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(actual_url, download=True)
                if info is None:
                    raise DownloadError("Video yuklab olinmadi")

                # Playlist bo'lsa
                if "entries" in info:
                    entries = list(info["entries"])
                    if not entries:
                        raise DownloadError("Playlistda video topilmadi")
                    info = entries[0]

                # Yakuniy fayl yo'li
                filepath = ydl.prepare_filename(info)

                # yt-dlp merge qilganda ext o'zgarishi mumkin
                mkv_path = Path(filepath).with_suffix(".mkv")

                # Fayl mavjudligini tekshirish
                if mkv_path.exists():
                    return mkv_path

                # Boshqa kengaytma bilan bo'lishi mumkin
                base = Path(filepath).stem
                for f in DOWNLOAD_DIR.iterdir():
                    if f.stem == base and f.suffix in (".mkv", ".mp4", ".webm", ".ts"):
                        # MKV ga konvert qilish kerak bo'lsa
                        if f.suffix != ".mkv":
                            return _convert_to_mkv(f)
                        return f

                # download_id bilan boshlanadigan eng yangi faylni topish
                candidates = sorted(
                    [f for f in DOWNLOAD_DIR.iterdir() if f.name.startswith(download_id)],
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                if candidates:
                    f = candidates[0]
                    if f.suffix != ".mkv":
                        return _convert_to_mkv(f)
                    return f

                # Asl fayl
                orig = Path(filepath)
                if orig.exists():
                    if orig.suffix != ".mkv":
                        return _convert_to_mkv(orig)
                    return orig

                raise DownloadError("Yuklab olingan fayl topilmadi")

        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Yuklab olishda xato: {e}")
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"Kutilmagan xato: {e}")

    result_path = await loop.run_in_executor(None, _download)
    return result_path


def _convert_to_mkv(input_path: Path) -> Path:
    """
    Faylni ffmpeg orqali MKV formatga konvert qilish.

    Args:
        input_path: Kirish fayli

    Returns:
        MKV fayl yo'li
    """
    output_path = input_path.with_suffix(".mkv")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(input_path),
                "-c", "copy",  # codec o'zgartirmasdan, faqat konteyner
                "-y",  # overwrite
                str(output_path),
            ],
            capture_output=True,
            check=True,
            timeout=300,
        )
        # Asl faylni o'chirish
        input_path.unlink(missing_ok=True)
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg xatosi: {e.stderr.decode()}")
        # Konvert bo'lmasa, asl faylni qaytarish
        return input_path
    except FileNotFoundError:
        logger.error("ffmpeg topilmadi! O'rnating: https://ffmpeg.org/download.html")
        return input_path


async def compress_video(input_path: Path, target_size_mb: int = 49) -> Path:
    """
    Videoni siqib kichiklashtirish (50 MB dan kichik qilish uchun).

    Args:
        input_path: Kirish fayli
        target_size_mb: Maqsad hajm (MB)

    Returns:
        Siqilgan fayl yo'li
    """
    output_path = input_path.with_name(f"compressed_{input_path.name}")

    # Video davomiyligini aniqlash
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]

    loop = asyncio.get_running_loop()

    def _compress():
        try:
            result = subprocess.run(
                probe_cmd, capture_output=True, text=True, timeout=30
            )
            duration = float(result.stdout.strip())
        except Exception:
            duration = 600  # Fallback: 10 daqiqa

        # Bitrate hisoblash (kbit/s)
        target_bitrate = int((target_size_mb * 8192) / duration)
        # Audio uchun 128k ajratish
        video_bitrate = max(target_bitrate - 128, 200)

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-c:v", "libx264",
                    "-b:v", f"{video_bitrate}k",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-preset", "fast",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                check=True,
                timeout=1800,  # 30 daqiqa timeout
            )
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Siqishda xato: {e.stderr.decode()}")
            raise DownloadError("Videoni siqishda xato yuz berdi")

    return await loop.run_in_executor(None, _compress)


def get_file_size_mb(path: Path) -> float:
    """Fayl hajmini MB da qaytarish"""
    return path.stat().st_size / (1024 * 1024)


def cleanup_file(path: Path) -> None:
    """Vaqtinchalik faylni o'chirish"""
    try:
        if path and path.exists():
            path.unlink()
            logger.info(f"Tozalandi: {path}")
    except Exception as e:
        logger.warning(f"Tozalashda xato: {e}")


async def _async_callback(callback, percent, status):
    """Async callback wrapper"""
    if asyncio.iscoroutinefunction(callback):
        await callback(percent, status)
    else:
        callback(percent, status)
