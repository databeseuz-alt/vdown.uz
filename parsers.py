"""
VDown.uz — Maxsus sayt parserlari
uzmovi.net/tv va shunga o'xshash o'zbek kino saytlaridan
video stream (m3u8) havolalarini ajratib oladi.
"""
import re
import logging
from urllib.parse import urljoin
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Umumiy HTTP headerlari
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ─── Qo'llab-quvvatlanadigan saytlar ro'yxati ─────────
SUPPORTED_SITES = {}


def register_site(pattern):
    """Sayt extractorini ro'yxatga qo'shish uchun decorator"""
    def decorator(func):
        SUPPORTED_SITES[pattern] = func
        return func
    return decorator


def is_supported_site(url: str) -> bool:
    """URL maxsus parser bilan qo'llab-quvvatlanadimi?"""
    for pattern in SUPPORTED_SITES:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def extract_stream_url(url: str) -> dict | None:
    """
    Sayt havolasidan video stream URL ni ajratib olish.

    Returns:
        dict: {"stream_url": "...", "title": "...", "referer": "..."} yoki None
    """
    for pattern, extractor in SUPPORTED_SITES.items():
        if re.search(pattern, url, re.IGNORECASE):
            try:
                return extractor(url)
            except Exception as e:
                logger.error(f"Extractor xatosi ({pattern}): {e}")
                return None
    return None


def _fetch_url(url: str, referer: str = None) -> str:
    """URL dan HTML yuklab olish (urllib bilan, requests kerak emas)"""
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    resp = urlopen(req, timeout=15)
    return resp.read().decode("utf-8", errors="ignore")


# ═══════════════════════════════════════════════════════
# UZMOVI Parser (uzmovi.net, uzmovi.tv)
# ═══════════════════════════════════════════════════════

@register_site(r"uzmovi\.(?:net|tv|com)")
def _extract_uzmovi(url: str) -> dict | None:
    """
    uzmovi.net/tv dan video stream URL ni olish.
    Jarayon:
      1. Sahifa HTML dan iframe src ni topish (uzdown.*/embed/...)
      2. iframe sahifasidan file: '...m3u8' ni ajratib olish
    """
    logger.info(f"UzMovi parser: {url}")

    # 1-qadam: Asosiy sahifani yuklab olish
    html = _fetch_url(url)

    # Sahifa sarlavhasini olish
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).split("-")[0].strip() if title_match else "Video"
    # Fayl nomi uchun tozalash
    title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    title = title.replace("(", "").replace(")", "").strip()

    # 2-qadam: iframe src ni topish (uzdown domenlari)
    iframe_match = re.search(
        r'src="(https://uzdown\.(?:live|net|com|org|pw)/embed/[^"]+)"', html
    )
    if not iframe_match:
        # Boshqa iframe formatlarni sinash
        iframe_match = re.search(
            r'<iframe[^>]+src=["\']([^"\']*(?:uzdown|embed)[^"\']*)["\']', html, re.IGNORECASE
        )

    if not iframe_match:
        logger.error("iframe topilmadi")
        # To'g'ridan-to'g'ri m3u8 qidirish
        m3u8_match = re.search(r"file:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html)
        if m3u8_match:
            return {
                "stream_url": m3u8_match.group(1),
                "title": title,
                "referer": url,
            }
        return None

    iframe_url = iframe_match.group(1)
    if iframe_url.startswith("//"):
        iframe_url = "https:" + iframe_url

    logger.info(f"iframe topildi: {iframe_url}")

    # Epizod raqamini aniqlash
    ep_match = re.search(r"episode=(\d+)", iframe_url)
    if ep_match:
        title = f"{title} - {ep_match.group(1)}-qism"

    # 3-qadam: iframe sahifasini yuklab olish
    iframe_html = _fetch_url(iframe_url, referer=url)

    # 4-qadam: m3u8 URL ni topish (single quotes — uzmovi standart formati)
    m3u8_match = re.search(r"file:\s*'([^']+)'", iframe_html)
    if not m3u8_match:
        # Double quotes bilan sinash
        m3u8_match = re.search(r'file:\s*"([^"]+)"', iframe_html)
    if not m3u8_match:
        # Umumiy m3u8 qidirish
        m3u8_match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', iframe_html)

    if m3u8_match:
        stream_url = m3u8_match.group(1)
        logger.info(f"Stream URL topildi: {stream_url}")
        return {
            "stream_url": stream_url,
            "title": title,
            "referer": iframe_url,
        }

    # mp4 to'g'ridan-to'g'ri sinash
    mp4_match = re.search(r"file:\s*['\"]([^'\"]+\.mp4[^'\"]*)['\"]", iframe_html)
    if mp4_match:
        return {
            "stream_url": mp4_match.group(1),
            "title": title,
            "referer": iframe_url,
        }

    logger.error("m3u8/video URL topilmadi iframe ichida")
    return None


# ═══════════════════════════════════════════════════════
# ASILMEDIA Parser
# ═══════════════════════════════════════════════════════

@register_site(r"asilmedia\.(net|org)")
def _extract_asilmedia(url: str) -> dict | None:
    """asilmedia.net/org dan video stream URL ni olish."""
    logger.info(f"AsilMedia parser: {url}")
    return _generic_iframe_extractor(url)


# ═══════════════════════════════════════════════════════
# UZDOWN direct embed
# ═══════════════════════════════════════════════════════

@register_site(r"uzdown\.(?:live|net|com|org|pw)")
def _extract_uzdown_direct(url: str) -> dict | None:
    """uzdown embed sahifasidan to'g'ridan-to'g'ri m3u8 olish."""
    logger.info(f"UzDown direct parser: {url}")

    html = _fetch_url(url)

    # Single quotes (uzmovi standart)
    m3u8_match = re.search(r"file:\s*'([^']+)'", html)
    if not m3u8_match:
        m3u8_match = re.search(r'file:\s*"([^"]+)"', html)
    if not m3u8_match:
        m3u8_match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', html)

    if m3u8_match:
        return {
            "stream_url": m3u8_match.group(1),
            "title": "Video",
            "referer": url,
        }

    mp4_match = re.search(r"file:\s*['\"]([^'\"]+\.mp4[^'\"]*)['\"]", html)
    if mp4_match:
        return {
            "stream_url": mp4_match.group(1),
            "title": "Video",
            "referer": url,
        }

    return None


# ═══════════════════════════════════════════════════════
# Umumiy iframe extractor (ko'p saytlar uchun)
# ═══════════════════════════════════════════════════════

def _generic_iframe_extractor(url: str) -> dict | None:
    """
    Ko'pchilik o'zbek kino saytlari uchun umumiy extractor.
    Iframe → PlayerJS → m3u8 zanjirini kuzatadi.
    """
    html = _fetch_url(url)

    # Sarlavha
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).split("-")[0].strip() if title_match else "Video"
    title = re.sub(r'[\\/*?:"<>|]', "", title).strip()

    # To'g'ridan-to'g'ri m3u8
    m3u8_match = re.search(r"file:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html)
    if m3u8_match:
        return {
            "stream_url": m3u8_match.group(1),
            "title": title,
            "referer": url,
        }

    # iframe topish (uzdown yoki boshqa embed)
    iframe_match = re.search(
        r'src="(https://uzdown\.(?:live|net|com|org|pw)/embed/[^"]+)"', html
    )
    if not iframe_match:
        iframe_match = re.search(
            r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE
        )
    if not iframe_match:
        return None

    iframe_url = iframe_match.group(1)
    if iframe_url.startswith("//"):
        iframe_url = "https:" + iframe_url
    elif not iframe_url.startswith("http"):
        iframe_url = urljoin(url, iframe_url)

    # iframe sahifasini yuklab olish
    iframe_html = _fetch_url(iframe_url, referer=url)

    # m3u8 topish
    m3u8_match = re.search(r"file:\s*'([^']+)'", iframe_html)
    if not m3u8_match:
        m3u8_match = re.search(r'file:\s*"([^"]+)"', iframe_html)
    if not m3u8_match:
        m3u8_match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', iframe_html)

    if m3u8_match:
        return {
            "stream_url": m3u8_match.group(1),
            "title": title,
            "referer": iframe_url,
        }

    mp4_match = re.search(r"file:\s*['\"]([^'\"]+\.mp4[^'\"]*)['\"]", iframe_html)
    if mp4_match:
        return {
            "stream_url": mp4_match.group(1),
            "title": title,
            "referer": iframe_url,
        }

    return None
