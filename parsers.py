"""
VDown.uz — Maxsus sayt parserlari
uzmovi.net/tv va shunga o'xshash o'zbek kino saytlaridan
video stream (m3u8) havolalarini ajratib oladi.
"""
import re
import logging
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

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
# UZMOVI Parser (uzmovi.net, uzmovi.tv) - Playwright bilan
# ═══════════════════════════════════════════════════════

@register_site(r"uzmovi\.(?:net|tv|com)")
def _extract_uzmovi(url: str) -> dict | None:
    """uzmovi.net uchun maxsus parser (Playwright yordamida)"""
    logger.info(f"UzMovi Playwright parser ishga tushdi: {url}")
    
    # Agar bu to'g'ridan-to'g'ri mp4/m3u8 fayl bo'lsa (masalan story.uzmovi.net)
    if url.lower().endswith('.mp4') or url.lower().endswith('.m3u8'):
        logger.info(f"To'g'ridan-to'g'ri fayl aniqlandi: {url}")
        return {
            "stream_url": url,
            "title": "Uzmovi Video",
            "referer": "https://uzmovi.net/"
        }
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            intercepted_url = None
            intercepted_headers = {}
            
            def handle_request(route, request):
                nonlocal intercepted_url, intercepted_headers
                if (".mpd" in request.url or ".m3u8" in request.url) and intercepted_url is None:
                    intercepted_url = request.url
                    intercepted_headers = request.headers
                    logger.info(f"Stream URL va headerlar ushlandi: {intercepted_url}")
                route.continue_()
                
            page.route("**/*", handle_request)
            
            logger.info("Sahifa yuklanmoqda...")
            page.goto(url, wait_until="load", timeout=30000)
            
            # Sarlavhani olish
            title = "Uzmovi Video"
            h1 = page.query_selector("h1")
            if h1:
                title = h1.inner_text().strip()
                
            # ONLAYN KO'RISH tabini bosish
            tabs = page.query_selector_all('[data-toggle="tab"]')
            for tab in tabs:
                if "ONLAYN" in tab.inner_text().upper():
                    logger.info("ONLAYN KO'RISH tugmasi topildi, bosilmoqda...")
                    tab.click()
                    break
            
            # JavaScript ishlashini va player yuklanishini kutish
            page.wait_for_timeout(3000)
            
            # Player play tugmasini bosish (tarmoq so'rovlarini chaqirish uchun)
            play_btn = page.query_selector('.vjs-big-play-button')
            if play_btn:
                logger.info("Play tugmasi bosilmoqda...")
                play_btn.click()
                page.wait_for_timeout(3000)
            
            stream_url = intercepted_url
            headers = intercepted_headers
            
            # Agar networkdan tushmasa, <source> tegidan qidirish
            if not stream_url:
                source = page.query_selector("source")
                if source:
                    stream_url = source.get_attribute("src")
                    logger.info(f"<source> tegidan video topildi: {stream_url}")
                    
            # Agar <source> bo'lmasa, iframe larni tekshirish (YouTube, VK va boshqalar uchun)
            if not stream_url:
                iframes = page.query_selector_all("iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                            
                        if any(d in src.lower() for d in ['youtube.com', 'youtu.be', 'ok.ru', 'rutube.ru', 'vk.com']):
                            stream_url = src
                            logger.info(f"Mashhur platforma iframe topildi: {stream_url}")
                            break
                        elif "uzdown" in src or "embed" in src:
                            stream_url = src
                            logger.info(f"Uzdown/embed iframe topildi: {stream_url}")
                            break

            browser.close()
            
            if stream_url:
                # Keraksiz headerlarni tozalash
                clean_headers = {}
                for k, v in headers.items():
                    if k.lower() not in ["host", "accept-encoding"]:
                        clean_headers[k] = v
                        
                return {
                    "stream_url": stream_url,
                    "title": title,
                    "referer": url,
                    "headers": clean_headers
                }
            else:
                logger.error("Playwright yordamida hech qanday video havola topilmadi.")
                return None
                
    except Exception as e:
        logger.error(f"Playwright orqali xatolik yuz berdi: {e}")
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

    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).split("-")[0].strip() if title_match else "Video"
    title = re.sub(r'[\\/*?:"<>|]', "", title).strip()

    m3u8_match = re.search(r"file:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html)
    if m3u8_match:
        return {
            "stream_url": m3u8_match.group(1),
            "title": title,
            "referer": url,
        }

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

    if any(domain in iframe_url.lower() for domain in ['youtube.com', 'youtu.be', 'ok.ru', 'rutube.ru', 'vk.com', 'myvideo.uz', 'mover.uz']):
        return {
            "stream_url": iframe_url,
            "title": title,
            "referer": url,
        }

    iframe_html = _fetch_url(iframe_url, referer=url)

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
