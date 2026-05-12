"""
fetcher.py – Sayfa çekici
  1. requests ile dener
  2. JS-heavy tespit edilirse Playwright'e düşer
  3. use_playwright=always → direkt Playwright
"""
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


JS_FRAMEWORK_SIGNALS = [
    ("div", {"id": "__next"}),       # Next.js
    ("div", {"id": "app"}),          # Vue / generic
    ("div", {"id": "root"}),         # React CRA
    ("div", {"id": "__nuxt"}),       # Nuxt
]


def _is_js_heavy(soup: BeautifulSoup) -> bool:
    """Sayfada anlamlı metin yoksa ve SPA işareti varsa True döner."""
    body_text = soup.get_text(strip=True)
    if len(body_text) > 800:
        return False
    return any(soup.find(tag, attrs) for tag, attrs in JS_FRAMEWORK_SIGNALS)


def fetch_with_requests(url: str, timeout: int, ua: str) -> dict:
    headers = {"User-Agent": ua, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
    start = time.time()
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    load_time = round(time.time() - start, 2)
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    return {
        "url": resp.url,
        "status_code": resp.status_code,
        "html": html,
        "soup": soup,
        "load_time": load_time,
        "method": "requests",
        "error": None,
    }


def fetch_with_playwright(url: str, timeout: int) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError("Playwright kurulu değil. Çalıştırın: playwright install chromium")

    start = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        html = page.content()
        final_url = page.url
        load_time = round(time.time() - start, 2)
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    return {
        "url": final_url,
        "status_code": 200,
        "html": html,
        "soup": soup,
        "load_time": load_time,
        "method": "playwright",
        "error": None,
    }


def fetch_page(url: str, config: dict) -> dict:
    """
    Ana fetch fonksiyonu.
    Hata durumunda error anahtarı dolu dict döner.
    """
    timeout = config.get("timeout", 30)
    ua = config.get("user_agent", "Mozilla/5.0")
    mode = config.get("use_playwright", "auto")

    try:
        if mode == "always":
            return fetch_with_playwright(url, timeout)

        result = fetch_with_requests(url, timeout, ua)

        if mode == "auto" and _is_js_heavy(result["soup"]):
            print(f"  ⚡ JS-heavy tespit edildi, Playwright devreye alınıyor: {url}")
            try:
                return fetch_with_playwright(url, timeout)
            except Exception as e:
                print(f"  ⚠️  Playwright başarısız, requests sonucu kullanılıyor: {e}")
                return result

        return result

    except Exception as e:
        return {
            "url": url,
            "status_code": 0,
            "html": "",
            "soup": None,
            "load_time": 0,
            "method": "error",
            "error": str(e),
        }


def fetch_text_url(url: str, timeout: int = 15) -> tuple[int, str]:
    """robots.txt / sitemap.xml gibi düz metin URL'ler için."""
    try:
        ua = "Mozilla/5.0 (compatible; SEOAnalyzer/1.0)"
        resp = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
        return resp.status_code, resp.text
    except Exception as e:
        return 0, str(e)
