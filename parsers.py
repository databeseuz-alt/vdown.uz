"""
VDown.uz — Maxsus sayt parserlari
uzmovi.net va shunga o'xshash o'zbek kino saytlaridan
video stream (m3u8) havolalarini ajratib oladi.
"""
import re
import logging
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# Umumiy HTTP headerlari
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
}

# ─── Qo'llab-quvvatlanadigan saytlar ro'yxati ─────────
# Har bir sayt uchun: (domain_pattern, extractor_function)
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


# ═══════════════════════════════════════════════════════
# UZMOVI.NET Parser
# ═══════════════════════════════════════════════════════

@register_site(r"uzmovi\.net")
def _extract_uzmovi(url: str) -> dict | None:
    """
    uzmovi.net dan video stream URL ni olish.
    Jarayon:
      1. Sahifa HTML dan iframe src ni topish (uzdown.*/embed/...)
      2. iframe sahifasidan PlayerJS konfiguratsiyasidan m3u8 URL olish
    """
    logger.info(f"UzMovi parser: {url}")

    # 1-qadam: Asosiy sahifani yuklab olish
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # Sahifa sarlavhasini olish
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Video"
    # Ortiqcha matnlarni tozalash
    title = re.sub(r"\s*[\-–|].*$", "", title).strip()

    # 2-qadam: iframe src ni topish (uzdown domenlari)
    iframe_patterns = [
        r'<iframe[^>]+src=["\']([^"\']*uzdown\.[^"\']+)["\']',
        r'<iframe[^>]+src=["\']([^"\']*embed[^"\']+)["\']',
        r'src=["\']([^"\']*uzdown\.[^"\']+)["\']',
        # PlayerJS to'g'ridan-to'g'ri sahifada bo'lishi mumkin
        r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    ]

    iframe_url = None
    direct_m3u8 = None

    for pattern in iframe_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            found_url = match.group(1)
            if ".m3u8" in found_url:
                direct_m3u8 = found_url
                break
            else:
                iframe_url = found_url
                break

    # Agar m3u8 to'g'ridan-to'g'ri topilsa
    if direct_m3u8:
        logger.info(f"M3U8 to'g'ridan-to'g'ri topildi: {direct_m3u8}")
        return {
            "stream_url": direct_m3u8,
            "title": title,
            "referer": url,
        }

    if not iframe_url:
        logger.error("iframe topilmadi")
        # Sahifadagi barcha iframe'larni ko'rsatish (debug)
        all_iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        logger.debug(f"Barcha iframe'lar: {all_iframes}")
        return None

    # URL ni to'liq qilish
    if iframe_url.startswith("//"):
        iframe_url = "https:" + iframe_url
    elif not iframe_url.startswith("http"):
        iframe_url = urljoin(url, iframe_url)

    logger.info(f"iframe topildi: {iframe_url}")

    # 3-qadam: iframe sahifasini yuklab olish
    resp2 = session.get(
        iframe_url,
        timeout=15,
        headers={**HEADERS, "Referer": url},
    )
    resp2.raise_for_status()
    iframe_html = resp2.text

    # 4-qadam: m3u8 URL ni topish
    m3u8_patterns = [
        r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'["\']([^"\']+\.m3u8[^"\']*)["\']',
        # Ba'zan video fayllar to'g'ridan-to'g'ri
        r'file:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
    ]

    for pattern in m3u8_patterns:
        match = re.search(pattern, iframe_html, re.IGNORECASE)
        if match:
            stream_url = match.group(1)
            logger.info(f"Stream URL topildi: {stream_url}")
            return {
                "stream_url": stream_url,
                "title": title,
                "referer": iframe_url,
            }

    logger.error("m3u8/video URL topilmadi iframe ichida")
    logger.debug(f"iframe HTML (birinchi 500 belgi): {iframe_html[:500]}")
    return None


# ═══════════════════════════════════════════════════════
# ASILMEDIA Parser (shunga o'xshash saytlar)
# ═══════════════════════════════════════════════════════

@register_site(r"asilmedia\.(net|org)")
def _extract_asilmedia(url: str) -> dict | None:
    """asilmedia.net/org dan video stream URL ni olish."""
    logger.info(f"AsilMedia parser: {url}")
    # AsilMedia ham xuddi shunday iframe + PlayerJS tuzilishiga ega
    return _generic_iframe_extractor(url)


@register_site(r"uzdown\.(live|net|com|org|pw)")
def _extract_uzdown_direct(url: str) -> dict | None:
    """uzdown embed sahifasidan to'g'ridan-to'g'ri m3u8 olish."""
    logger.info(f"UzDown direct parser: {url}")

    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    html = resp.text

    m3u8_patterns = [
        r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
    ]

    for pattern in m3u8_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            stream_url = match.group(1)
            return {
                "stream_url": stream_url,
                "title": "Video",
                "referer": url,
            }

    return None


# ═══════════════════════════════════════════════════════
# Umumiy iframe extractor (ko'p saytlar uchun ishlaydi)
# ═══════════════════════════════════════════════════════

def _generic_iframe_extractor(url: str) -> dict | None:
    """
    Ko'pchilik o'zbek kino saytlari uchun umumiy extractor.
    Iframe → PlayerJS → m3u8 zanjirini kuzatadi.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # Sarlavha
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Video"
    title = re.sub(r"\s*[\-–|].*$", "", title).strip()

    # To'g'ridan-to'g'ri m3u8
    m3u8_match = re.search(r'["\']([^"\']+\.m3u8[^"\']*)["\']', html)
    if m3u8_match:
        return {
            "stream_url": m3u8_match.group(1),
            "title": title,
            "referer": url,
        }

    # iframe topish
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
    resp2 = session.get(
        iframe_url,
        timeout=15,
        headers={**HEADERS, "Referer": url},
    )
    resp2.raise_for_status()
    iframe_html = resp2.text

    # m3u8 topish
    for pattern in [
        r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file:\s*["\']([^"\']+\.mp4[^"\']*)["\']',
    ]:
        match = re.search(pattern, iframe_html, re.IGNORECASE)
        if match:
            return {
                "stream_url": match.group(1),
                "title": title,
                "referer": iframe_url,
            }

    return None
