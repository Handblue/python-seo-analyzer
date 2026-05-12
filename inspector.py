"""
inspector.py – Tekli sayfa derin analiz fonksiyonları
Her fonksiyon bağımsız çalışır; app.py route'larından çağrılır.
"""
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def fetch_url(url: str, timeout: int = 30) -> dict:
    try:
        t0 = time.time()
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"},
                         timeout=timeout, allow_redirects=True)
        return {"ok": True, "text": r.text, "status": r.status_code,
                "url": r.url, "elapsed": round(time.time() - t0, 2)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fetch_text(url: str, timeout: int = 15) -> tuple[int, str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


# ── 1. Heading Map ────────────────────────────────────────────
def get_headings(soup: BeautifulSoup) -> dict:
    nodes = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    headings = [{"level": int(n.name[1]), "text": n.get_text(strip=True)[:150]}
                for n in nodes]

    h1s = [h for h in headings if h["level"] == 1]
    issues = []
    if not h1s:
        issues.append({"cls": "bad", "t": "H1 eksik!"})
    elif len(h1s) > 1:
        issues.append({"cls": "warn", "t": f"{len(h1s)} tane H1 var"})
    else:
        issues.append({"cls": "ok", "t": "H1 doğru ✓"})

    prev, seen = 0, {}
    for h in headings:
        if prev > 0 and h["level"] > prev + 1:
            k = f"H{prev}→H{h['level']}"
            if k not in seen:
                issues.append({"cls": "warn", "t": f"{k} atlama"})
                seen[k] = True
        prev = h["level"]

    return {"headings": headings, "issues": issues, "total": len(headings)}


# ── 2. Meta & Canonical ───────────────────────────────────────
def get_meta(soup: BeautifulSoup, url: str) -> dict:
    def g(sel, attr=None):
        el = soup.select_one(sel)
        if not el:
            return None
        return el.get(attr) if attr else el.get_text()

    html_tag = soup.find("html")
    body = soup.find("body")
    wc = len(body.get_text(separator=" ").split()) if body else 0

    return {
        "title": g("title"),
        "desc": g('meta[name="description"]', "content"),
        "canonical": g('link[rel="canonical"]', "href"),
        "robots": g('meta[name="robots"]', "content"),
        "lang": html_tag.get("lang") if html_tag else None,
        "viewport": g('meta[name="viewport"]', "content"),
        "h1_count": len(soup.find_all("h1")),
        "word_count": wc,
    }


# ── 3. OG / Social ───────────────────────────────────────────
def get_og(soup: BeautifulSoup) -> dict:
    def gm(name):
        el = (soup.find("meta", property=name) or
              soup.find("meta", attrs={"name": name}))
        return el.get("content") if el else None

    return {
        "ogTitle":   gm("og:title"),    "ogDesc": gm("og:description"),
        "ogImage":   gm("og:image"),    "ogUrl":  gm("og:url"),
        "ogType":    gm("og:type"),     "ogSite": gm("og:site_name"),
        "twCard":    gm("twitter:card"),"twTitle":gm("twitter:title"),
        "twDesc":    gm("twitter:description"),
        "twImage":   gm("twitter:image"),
        "twSite":    gm("twitter:site"),
        "twCreator": gm("twitter:creator"),
    }


# ── 4. Images ────────────────────────────────────────────────
def get_images(soup: BeautifulSoup, base_url: str) -> list:
    imgs = []
    for el in soup.find_all("img"):
        src = el.get("src") or el.get("data-src") or ""
        if src and not src.startswith("data:"):
            src = urljoin(base_url, src)
        imgs.append({
            "src":     src[:200],
            "alt":     el.get("alt"),       # None = attribute missing
            "loading": el.get("loading"),
        })
    return imgs


# ── 5. Schema / Structured Data ──────────────────────────────
def get_schema(soup: BeautifulSoup) -> list:
    results = []
    for el in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(el.string or "{}")
            types = []
            if "@graph" in data:
                for item in data["@graph"]:
                    t = item.get("@type", "")
                    types.append(t if isinstance(t, str) else ",".join(t))
            elif "@type" in data:
                t = data["@type"]
                types.append(t if isinstance(t, str) else ",".join(t))
            raw = json.dumps(data, ensure_ascii=False, indent=2)[:2000]
            results.append({"source": "JSON-LD", "types": ", ".join(types) or "Unknown", "raw": raw})
        except Exception:
            results.append({"source": "JSON-LD", "types": "(Parse Hatası)",
                            "raw": (el.string or "")[:500]})

    micros = soup.find_all(attrs={"itemscope": True})
    if micros:
        types2 = [el.get("itemtype", "").split("/")[-1]
                  for el in micros if el.get("itemtype")]
        results.append({"source": "Microdata",
                         "types": ", ".join(types2),
                         "raw": f"[Microdata — {len(micros)} blok]"})
    return results


# ── 6. Core Web Vitals (Playwright) ──────────────────────────
def get_cwv(url: str, timeout: int = 30) -> dict:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

            metrics = page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0];
                const paint = performance.getEntriesByName('first-contentful-paint')[0];
                const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
                const clsEntries = performance.getEntriesByType('layout-shift');
                const fidEntries = performance.getEntriesByType('first-input');
                let cls = null;
                if (clsEntries.length) {
                    cls = clsEntries.reduce((s,e) => s + (e.hadRecentInput ? 0 : e.value), 0);
                    cls = Math.round(cls * 1000) / 1000;
                }
                return {
                    ttfb:    nav  ? Math.round(nav.responseStart - nav.requestStart) : null,
                    domLoad: nav  ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : null,
                    load:    nav  ? Math.round(nav.loadEventEnd - nav.startTime) : null,
                    fcp:     paint ? Math.round(paint.startTime) : null,
                    lcp:     lcpEntries.length ? Math.round(lcpEntries[lcpEntries.length-1].startTime) : null,
                    cls:     cls,
                    fid:     fidEntries.length ? Math.round(fidEntries[0].processingStart - fidEntries[0].startTime) : null,
                };
            }""")
            browser.close()
            return metrics
    except Exception as e:
        return {"error": str(e)}


# ── 7. PageSpeed Insights ────────────────────────────────────
def get_pagespeed(url: str, strategy: str, api_key: str) -> dict:
    endpoint = (
        f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={requests.utils.quote(url, safe='')}&strategy={strategy}&key={api_key}"
    )
    try:
        r = requests.get(endpoint, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── 8. Broken Links ──────────────────────────────────────────
def check_broken_links(soup: BeautifulSoup, base_url: str, timeout: int = 8) -> list:
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full = urljoin(base_url, href)
        if full in seen:
            continue
        seen.add(full)
        links.append({"url": full, "text": a.get_text(strip=True)[:60]})
        if len(links) >= 60:
            break

    results = []
    for link in links:
        try:
            r = requests.head(link["url"], headers={"User-Agent": UA},
                              timeout=timeout, allow_redirects=True)
            status = r.status_code
        except Exception:
            status = 0
        results.append({**link, "status": status})
    return results


# ── 9. Sitemap ───────────────────────────────────────────────
def get_sitemap(base_url: str) -> dict:
    from xml.etree import ElementTree as ET

    # Find sitemap URL from robots.txt
    _, robots = fetch_text(base_url.rstrip("/") + "/robots.txt")
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    if robots:
        m = re.search(r"Sitemap:\s*(\S+)", robots, re.I)
        if m:
            sitemap_url = m.group(1).strip()

    status, text = fetch_text(sitemap_url)
    if status != 200:
        return {"error": f"Sitemap yüklenemedi (HTTP {status})", "url": sitemap_url}

    try:
        root = ET.fromstring(text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        def find(el, tag):
            return el.find(f"sm:{tag}", ns) or el.find(tag)

        def val(el, tag):
            f = find(el, tag)
            return f.text.strip() if f is not None and f.text else ""

        sitemaps = root.findall("sm:sitemap", ns) or root.findall("sitemap")
        if sitemaps:
            entries = [{"loc": val(s, "loc"), "lm": val(s, "lastmod")} for s in sitemaps]
            return {"type": "index", "entries": entries, "url": sitemap_url}

        url_els = root.findall("sm:url", ns) or root.findall("url")
        entries = [{"loc": val(u, "loc"), "lm": val(u, "lastmod"),
                    "pri": val(u, "priority"), "chf": val(u, "changefreq")}
                   for u in url_els]
        return {"type": "sitemap", "entries": entries, "url": sitemap_url}
    except Exception as e:
        return {"error": f"Parse hatası: {e}", "raw": text[:500]}


# ── 10. WHOIS / RDAP ─────────────────────────────────────────
def get_whois(domain: str) -> dict:
    try:
        r = requests.get(f"https://rdap.org/domain/{domain}",
                         headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            return {"error": f"RDAP yanıt vermedi (HTTP {r.status_code})"}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── 11. Readability ──────────────────────────────────────────
def get_readability(soup: BeautifulSoup) -> dict:
    body = soup.find("main") or soup.find("article") or soup.find("body")
    if not body:
        return {"error": "İçerik bulunamadı."}
    for tag in body.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    text = re.sub(r"\s+", " ", body.get_text(separator=" ", strip=True))
    words = text.split()
    wc = len(words)
    if wc < 10:
        return {"error": "Yeterli metin bulunamadı."}

    sents = [s.strip() for s in re.split(r"[.!?…]+", text) if len(s.strip()) > 3]
    if not sents:
        sents = [text]
    sc = len(sents)

    VOWELS = "aeıioöuüAEIİOÖUÜaeiouAEIOU"
    syl_count = sum(max(1, sum(1 for c in w if c in VOWELS)) for w in words)

    fk = max(0, min(100, 206.835 - 1.015 * (wc / sc) - 84.6 * (syl_count / wc)))
    top_sents = sorted(sents, key=lambda s: len(s.split()), reverse=True)[:5]

    return {
        "wc": wc, "sc": sc, "avg_len": round(wc / sc, 1),
        "read_min": max(1, round(wc / 200)),
        "fk": round(fk),
        "sentences": [s[:200] for s in top_sents],
    }


# ── 12. Keyword Density ───────────────────────────────────────
STOP_WORDS = {
    "ve","ile","de","da","den","dan","bir","bu","o","şu","için","olan","ki",
    "ama","fakat","ancak","ya","veya","hem","ne","mi","mu","mı","mü","ben",
    "sen","biz","siz","onlar","çok","daha","en","her","ise","bunlar",
    "the","a","an","and","or","in","on","at","to","of","is","are","was",
    "were","has","have","be","it","that","this","with","for","as","by",
    "from","but","not","so","do","did","will","can","if","then","than",
    "all","any","out","up","been","their","there","they","what","who",
    "how","when","where","which","your","our","its",
}


def get_keywords(soup: BeautifulSoup, mode: int = 1) -> list:
    body = soup.find("main") or soup.find("article") or soup.find("body")
    if not body:
        return []
    text = body.get_text(separator=" ", strip=True).lower()
    text = re.sub(r"[0-9]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    words = [w for w in text.split() if len(w) > 2 and w not in STOP_WORDS]

    if mode == 2:
        tokens = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    else:
        tokens = words
    if not tokens:
        return []

    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    total = len(tokens)

    return [{"word": w, "count": c, "pct": round(c / total * 100, 1)}
            for w, c in sorted(freq.items(), key=lambda x: -x[1])[:30]]


# ── 13. robots.txt ───────────────────────────────────────────
def get_robots(base_url: str) -> dict:
    url = base_url.rstrip("/") + "/robots.txt"
    status, text = fetch_text(url)
    return {"status": status, "text": text[:5000] if text else "", "url": url}


# ── 14. Performance (Playwright) ─────────────────────────────
def get_performance(url: str, timeout: int = 30) -> dict:
    try:
        from playwright.sync_api import sync_playwright
        resources = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)

            def on_response(resp):
                resources.append({
                    "name": resp.url.split("/")[-1].split("?")[0][:50] or resp.url[:50],
                    "fullUrl": resp.url[:200],
                    "type": resp.request.resource_type,
                    "status": resp.status,
                })

            page.on("response", on_response)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

            timing = page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0];
                const res = performance.getEntriesByType('resource');
                const byType = {};
                let totalSize = 0;
                res.forEach(r => {
                    const t = r.initiatorType || 'other';
                    if (!byType[t]) byType[t] = {count:0,size:0};
                    byType[t].count++;
                    byType[t].size += r.decodedBodySize || 0;
                    totalSize += r.transferSize || 0;
                });
                return {
                    ttfb:     nav ? Math.round(nav.responseStart - nav.requestStart) : null,
                    domReady: nav ? Math.round(nav.domContentLoadedEventEnd - nav.startTime) : null,
                    loadTime: nav ? Math.round(nav.loadEventEnd - nav.startTime) : null,
                    transferSize: nav ? (nav.transferSize || 0) : 0,
                    totalTransfer: totalSize,
                    byType: byType,
                    topResources: Array.from(res)
                        .sort((a,b) => (b.decodedBodySize||0)-(a.decodedBodySize||0))
                        .slice(0,20)
                        .map(r => ({
                            name: r.name.split('/').pop().split('?')[0] || r.name.substring(0,50),
                            fullUrl: r.name.substring(0,200),
                            type: r.initiatorType||'other',
                            size: r.decodedBodySize||0,
                            duration: Math.round(r.duration),
                        })),
                };
            }""")
            browser.close()
            return timing
    except Exception as e:
        return {"error": str(e)}
