"""
checks.py – Tüm SEO kontrolleri
Kategoriler:
  1. Title & Meta
  2. OG / Sosyal Medya
  3. Heading Yapısı
  4. Teknik SEO (canonical, https, viewport, lang)
  5. Görseller
  6. Linkler
  7. Schema / Yapısal Veri
  8. Analytics / Takip
  9. Form Kontrolü
 10. İçerik Kalitesi
 11. Robots.txt & Sitemap  (site geneli, ayrı fonksiyon)
"""

import re
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup


# ──────────────────────────────────────────────────────────────
#  Veri Yapıları
# ──────────────────────────────────────────────────────────────

class Sev(str, Enum):
    ERROR   = "error"
    WARNING = "warning"
    OK      = "ok"
    INFO    = "info"


@dataclass
class Issue:
    category: str
    name:     str
    severity: Sev
    message:  str
    detail:   str = ""
    fix:      str = ""


@dataclass
class PageReport:
    url:           str
    label:         str
    page_type:     str
    status_code:   int
    load_time:     float
    render_method: str
    issues: List[Issue] = field(default_factory=list)

    def add(self, cat, name, sev, msg, detail="", fix=""):
        self.issues.append(Issue(cat, name, sev, msg, detail, fix))

    @property
    def errors(self):   return [i for i in self.issues if i.severity == Sev.ERROR]
    @property
    def warnings(self): return [i for i in self.issues if i.severity == Sev.WARNING]
    @property
    def oks(self):      return [i for i in self.issues if i.severity == Sev.OK]
    @property
    def infos(self):    return [i for i in self.issues if i.severity == Sev.INFO]

    @property
    def score(self) -> int:
        if not self.issues:
            return 100
        penalty = len(self.errors) * 10 + len(self.warnings) * 3
        return max(0, 100 - penalty)

    def by_category(self):
        cats = {}
        for i in self.issues:
            cats.setdefault(i.category, []).append(i)
        return cats


@dataclass
class SiteReport:
    site_name:   str
    base_url:    str
    pages:       List[PageReport] = field(default_factory=list)
    site_issues: List[Issue]      = field(default_factory=list)

    @property
    def total_errors(self):   return sum(len(p.errors)   for p in self.pages) + len([i for i in self.site_issues if i.severity == Sev.ERROR])
    @property
    def total_warnings(self): return sum(len(p.warnings) for p in self.pages) + len([i for i in self.site_issues if i.severity == Sev.WARNING])
    @property
    def avg_score(self) -> int:
        if not self.pages: return 0
        return round(sum(p.score for p in self.pages) / len(self.pages))


# ──────────────────────────────────────────────────────────────
#  Sayfa Analizi
# ──────────────────────────────────────────────────────────────

class PageAnalyzer:

    def __init__(self, soup: BeautifulSoup, url: str, page_type: str, config: dict):
        self.soup      = soup
        self.url       = url
        self.page_type = page_type
        self.config    = config
        parsed         = urlparse(url)
        self.base      = f"{parsed.scheme}://{parsed.netloc}"
        self.netloc    = parsed.netloc

    # ── Giriş noktası ───────────────────────────────────────────
    def analyze(self, report: PageReport):
        self._title(report)
        self._meta_desc(report)
        self._og_tags(report)
        self._twitter_tags(report)
        self._headings(report)
        self._canonical(report)
        self._images(report)
        self._links(report)
        self._schema(report)
        self._analytics(report)
        self._forms(report)
        self._technical(report)
        self._content(report)

    # ── 1. Title ────────────────────────────────────────────────
    def _title(self, r: PageReport):
        CAT = "Title & Meta"
        tag = self.soup.find("title")
        if not tag or not tag.text.strip():
            r.add(CAT, "Title Etiketi", Sev.ERROR,
                  "Title etiketi eksik veya boş",
                  fix="Her sayfaya benzersiz, 50-60 karakterlik title ekleyin")
            return

        title  = tag.text.strip()
        length = len(title)
        detail = f'"{title}"'

        if length < 30:
            r.add(CAT, "Title Uzunluğu", Sev.WARNING,
                  f"Title çok kısa ({length} karakter, ideal 50-60)",
                  detail=detail,
                  fix="Keyword + şehir + marka adı kombinasyonu deneyin")
        elif length > 60:
            r.add(CAT, "Title Uzunluğu", Sev.WARNING,
                  f"Title çok uzun ({length} karakter), Google SERP'te kesilebilir",
                  detail=detail,
                  fix="60 karakterin altına indirin")
        else:
            r.add(CAT, "Title Uzunluğu", Sev.OK,
                  f"Title uzunluğu ideal ({length} karakter)",
                  detail=detail)

    # ── 2. Meta Description ──────────────────────────────────────
    def _meta_desc(self, r: PageReport):
        CAT  = "Title & Meta"
        meta = self.soup.find("meta", attrs={"name": "description"})
        if not meta or not meta.get("content", "").strip():
            r.add(CAT, "Meta Description", Sev.ERROR,
                  "Meta description eksik",
                  fix="150-160 karakter, CTA içeren özgün meta description yazın")
            return

        desc   = meta["content"].strip()
        length = len(desc)

        if length < 80:
            r.add(CAT, "Meta Description", Sev.WARNING,
                  f"Meta description çok kısa ({length} karakter)",
                  detail=f'"{desc}"',
                  fix="150-160 karakter olmalı, anahtar kelimeler doğal geçmeli")
        elif length > 160:
            r.add(CAT, "Meta Description", Sev.WARNING,
                  f"Meta description çok uzun ({length} karakter, Google 160'ta kesiyor)",
                  detail=f'"{desc[:80]}..."',
                  fix="160 karakterin altına düşürün")
        else:
            r.add(CAT, "Meta Description", Sev.OK,
                  f"Meta description ideal ({length} karakter)")

    # ── 3. Open Graph ────────────────────────────────────────────
    def _og_tags(self, r: PageReport):
        CAT      = "OG / Sosyal Medya"
        required = ["og:title", "og:description", "og:image", "og:url", "og:type"]
        missing  = [p for p in required
                    if not self.soup.find("meta", property=p)
                    or not self.soup.find("meta", property=p).get("content", "").strip()]

        if missing:
            r.add(CAT, "Open Graph Etiketleri", Sev.ERROR,
                  f"Eksik OG etiketleri: {', '.join(missing)}",
                  detail="WhatsApp/Instagram/Facebook paylaşımında önizleme görünmez",
                  fix="Tüm OG etiketlerini ekleyin. og:image minimum 1200×630 px olmalı")
        else:
            r.add(CAT, "Open Graph Etiketleri", Sev.OK, "Tüm OG etiketleri mevcut ✓")

            # og:image varlığını ayrıca kontrol et (URL geçerli mi bilinmez ama boş mu?)
            img_tag = self.soup.find("meta", property="og:image")
            if img_tag and img_tag.get("content", "").startswith("http"):
                r.add(CAT, "og:image URL", Sev.OK, f"og:image tanımlı: {img_tag['content'][:60]}")

    # ── 4. Twitter / X Card ──────────────────────────────────────
    def _twitter_tags(self, r: PageReport):
        CAT   = "OG / Sosyal Medya"
        card  = self.soup.find("meta", attrs={"name": "twitter:card"})
        title = self.soup.find("meta", attrs={"name": "twitter:title"})
        desc  = self.soup.find("meta", attrs={"name": "twitter:description"})

        missing = []
        if not card:  missing.append("twitter:card")
        if not title: missing.append("twitter:title")
        if not desc:  missing.append("twitter:description")

        if missing:
            r.add(CAT, "Twitter/X Card", Sev.WARNING,
                  f"Eksik Twitter meta etiketleri: {', '.join(missing)}",
                  fix='<meta name="twitter:card" content="summary_large_image"> ile başlayın')
        else:
            r.add(CAT, "Twitter/X Card", Sev.OK, "Twitter Card etiketleri mevcut ✓")

    # ── 5. Heading Yapısı ────────────────────────────────────────
    def _headings(self, r: PageReport):
        CAT  = "Heading Yapısı"
        h1s  = self.soup.find_all("h1")

        # H1 sayısı
        if not h1s:
            r.add(CAT, "H1 Etiketi", Sev.ERROR,
                  "H1 etiketi bulunamadı",
                  fix="Her sayfada tam olarak 1 adet H1 olmalı, ana keyword'ü içermeli")
        elif len(h1s) > 1:
            texts = [h.get_text(strip=True)[:50] for h in h1s]
            r.add(CAT, "H1 Etiketi", Sev.ERROR,
                  f"{len(h1s)} adet H1 var (sadece 1 olmalı)",
                  detail=f"H1 metinleri: {texts}",
                  fix="Responsive tasarımda aynı component'in CSS ile gizlenip"
                      " gösterilip gösterilmediğini kontrol edin; fazla H1'i kaldırın")
        else:
            txt = h1s[0].get_text(strip=True)
            if len(txt) < 8:
                r.add(CAT, "H1 Etiketi", Sev.WARNING,
                      f"H1 çok kısa: '{txt}'",
                      fix="H1 ana keyword'ü net biçimde içermeli")
            else:
                r.add(CAT, "H1 Etiketi", Sev.OK, f"H1 doğru: '{txt[:60]}'")

        # Hiyerarşi / seviye atlama
        all_h = [(int(t.name[1]), t.get_text(strip=True)[:50])
                 for t in self.soup.find_all(["h1","h2","h3","h4","h5","h6"])]

        skips = []
        for i in range(1, len(all_h)):
            prev, curr = all_h[i-1][0], all_h[i][0]
            if curr > prev + 1:
                skips.append(f"H{prev}→H{curr}")

        if skips:
            r.add(CAT, "Heading Hiyerarşisi", Sev.WARNING,
                  f"Seviye atlaması tespit edildi: {', '.join(skips[:4])}",
                  fix="H1→H2→H3 sırasıyla kullanın, seviye atlamayın")
        elif len(all_h) > 1:
            r.add(CAT, "Heading Hiyerarşisi", Sev.OK, "Heading hiyerarşisi doğru")

        # Tekrar eden heading metinleri
        texts_lower = [h[1].lower() for h in all_h if len(h[1]) > 5]
        dupes = set(t for t in texts_lower if texts_lower.count(t) > 1)
        if dupes:
            r.add(CAT, "Tekrar Eden Başlıklar", Sev.WARNING,
                  f"{len(dupes)} başlık birden fazla kez tekrar ediyor: {list(dupes)[:3]}",
                  detail="Genellikle responsive breakpoint'lerde aynı component'in çift render olmasından kaynaklanır",
                  fix="CSS display:none yerine conditional rendering / visibility hidden kullanın")

    # ── 6. Canonical ────────────────────────────────────────────
    def _canonical(self, r: PageReport):
        CAT  = "Teknik SEO"
        link = self.soup.find("link", rel="canonical")

        if not link or not link.get("href", "").strip():
            r.add(CAT, "Canonical Tag", Sev.WARNING,
                  "Canonical etiketi eksik",
                  fix="<link rel='canonical' href='tam-url'> her sayfaya ekleyin")
            return

        canon      = link["href"].strip()
        cp         = urlparse(canon)
        pp         = urlparse(self.url)
        canon_www  = "www." in cp.netloc
        page_www   = "www." in pp.netloc

        if canon_www != page_www:
            r.add(CAT, "Canonical / WWW Tutarsızlığı", Sev.ERROR,
                  f"Canonical {'www\'lu' if canon_www else 'www\'suz'} "
                  f"ama sayfa URL\'si {'www\'lu' if page_www else 'www\'suz'}",
                  detail=f"Canonical: {canon}\nSayfa: {self.url}",
                  fix="Tüm iç linkler + sitemap URL'leri canonical ile aynı formatta olmalı")
        else:
            r.add(CAT, "Canonical Tag", Sev.OK, f"Canonical doğru: {canon[:70]}")

        # HTTPS kontrolü canonical üzerinden
        if canon.startswith("http://"):
            r.add(CAT, "Canonical HTTPS", Sev.ERROR,
                  "Canonical HTTP kullanıyor",
                  fix="Canonical URL'yi https:// ile başlatın")

    # ── 7. Görseller ────────────────────────────────────────────
    def _images(self, r: PageReport):
        CAT    = "Görseller"
        images = self.soup.find_all("img")
        total  = len(images)

        if total == 0:
            r.add(CAT, "Görseller", Sev.INFO, "Sayfada <img> etiketi bulunamadı")
            return

        # alt eksik (alt attribute hiç yok)
        no_alt_attr = [img for img in images if img.get("alt") is None]
        # alt var ama boş ve dekoratif olmayabilir (src değerine bakıyoruz)
        empty_alt   = [img for img in images
                       if img.get("alt") == ""
                       and img.get("src", "")
                       and not any(kw in img.get("src","").lower()
                                   for kw in ["logo","icon","shape","bg","background","divider"])]

        if no_alt_attr:
            srcs = [img.get("src","?")[:60] for img in no_alt_attr[:5]]
            r.add(CAT, "Alt Etiketi Eksik", Sev.ERROR,
                  f"{len(no_alt_attr)}/{total} görselde alt attribute YOK",
                  detail=f"Örnekler: {srcs}",
                  fix="İçerik görsellerine açıklayıcı alt text ekleyin. Dekoratif için alt='' kullanın")
        elif empty_alt:
            r.add(CAT, "Boş Alt Etiketi", Sev.WARNING,
                  f"{len(empty_alt)} içerik görseli boş alt text içeriyor",
                  fix="Görseli tarif eden anahtar kelimeli alt text yazın")
        else:
            r.add(CAT, "Alt Etiketleri", Sev.OK,
                  f"Tüm {total} görsel alt etiketi içeriyor ✓")

        # Lazy loading
        lazy_count = sum(1 for img in images if img.get("loading") == "lazy")
        if total > 3 and lazy_count < total * 0.5:
            r.add(CAT, "Lazy Loading", Sev.WARNING,
                  f"Görsellerin çoğunda lazy loading yok ({lazy_count}/{total})",
                  fix='Fold altındaki tüm görsellere loading="lazy" ekleyin')

        # WebP / next-gen format
        srcs    = [img.get("src","") for img in images]
        old_fmt = [s for s in srcs
                   if s and not s.endswith(".webp") and not s.endswith(".svg")
                   and not s.startswith("data:") and not s.startswith("//")
                   and ("." in s.split("/")[-1])]
        if old_fmt and len(old_fmt) > len(images) * 0.4:
            r.add(CAT, "Görsel Formatı", Sev.INFO,
                  f"{len(old_fmt)} görsel WebP formatında değil",
                  fix="Görselleri WebP/AVIF'e dönüştürün; PageSpeed puanı yükselir")

    # ── 8. Linkler ──────────────────────────────────────────────
    def _links(self, r: PageReport):
        CAT   = "Linkler"
        links = self.soup.find_all("a", href=True)

        # Tel: format
        tel_bad = [a["href"] for a in links
                   if a["href"].startswith("tel:")
                   and (" " in a["href"] or not a["href"].startswith("tel:+"))]
        if tel_bad:
            r.add(CAT, "Telefon Link Formatı", Sev.WARNING,
                  f"Hatalı tel: link formatı: {tel_bad[:3]}",
                  fix="Doğru format: tel:+905XXXXXXXXX (boşluk yok, +90 ile başlar)")

        # target=_blank güvenliği
        blank_ext = [a for a in links
                     if a.get("target") == "_blank"
                     and a["href"].startswith("http")
                     and self.netloc.replace("www.","") not in a["href"]]
        no_noopener = [a for a in blank_ext
                       if "noopener" not in " ".join(a.get("rel") or [])]
        if no_noopener:
            r.add(CAT, "Dış Link Güvenliği", Sev.WARNING,
                  f"{len(no_noopener)} dış linkte rel='noopener noreferrer' eksik",
                  fix='target="_blank" olan tüm dış linklere rel="noopener noreferrer" ekleyin')

        # target=blank yazım hatası
        typos = [a for a in links if a.get("target") in ("blank","_Blank","Blank","_BLANK")]
        if typos:
            r.add(CAT, "target=_blank Yazım Hatası", Sev.ERROR,
                  f"{len(typos)} linkte target='blank' (alt çizgi eksik!)",
                  detail=[a.get("href","?")[:60] for a in typos[:5]],
                  fix='Doğru: target="_blank"')

        # WWW tutarsızlığı iç linklerde
        page_www    = "www." in self.netloc
        domain_base = self.netloc.replace("www.","")
        int_links   = [a["href"] for a in links
                       if a["href"].startswith("http")
                       and domain_base in a["href"]]
        if page_www:
            inconsistent = [l for l in int_links if "www." not in urlparse(l).netloc]
        else:
            inconsistent = [l for l in int_links if "www." in urlparse(l).netloc]

        if inconsistent:
            r.add(CAT, "İç Link WWW Tutarsızlığı", Sev.WARNING,
                  f"{len(inconsistent)} iç link canonical formatından farklı",
                  detail=inconsistent[:3],
                  fix="Tüm iç linkler canonical URL formatıyla (www'lu/www'suz) tutarlı olmalı")

        # Boş href veya javascript: linkler
        empty = [a for a in links
                 if not a["href"].strip() or a["href"].strip() in ("#", "javascript:void(0)","javascript:;")]
        if len(empty) > 3:
            r.add(CAT, "Boş / Sahte Linkler", Sev.INFO,
                  f"{len(empty)} adet href='#' veya javascript: link var",
                  fix="Gereksiz boş linkler kaldırılabilir; butona dönüştürün")

    # ── 9. Schema ────────────────────────────────────────────────
    def _schema(self, r: PageReport):
        CAT  = "Schema / Yapısal Veri"
        tags = self.soup.find_all("script", type="application/ld+json")

        if not tags:
            rec = self._recommended_schemas()
            r.add(CAT, "JSON-LD Schema Yok", Sev.ERROR,
                  "Hiç JSON-LD schema bulunamadı",
                  fix=f"Bu sayfa türü için önerilen: {', '.join(rec)}")
            return

        found_types = []
        for tag in tags:
            try:
                data = json.loads(tag.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    t = item.get("@type","?")
                    found_types.append(t if isinstance(t, str) else str(t))
            except json.JSONDecodeError:
                r.add(CAT, "JSON-LD Syntax Hatası", Sev.ERROR,
                      "JSON-LD parse edilemedi (geçersiz JSON)",
                      fix="https://validator.schema.org ile doğrulayın")

        r.add(CAT, "JSON-LD Bulundu", Sev.OK,
              f"Schema türleri: {', '.join(found_types)}")

        # Önerilen schema eksik mi?
        rec     = self._recommended_schemas()
        missing = [s for s in rec if s not in found_types]
        if missing:
            r.add(CAT, "Önerilen Schema Eksik", Sev.WARNING,
                  f"Bu sayfa için önerilen schema eksik: {', '.join(missing)}",
                  fix=f"Ekleyin: {', '.join(missing)}")

    def _recommended_schemas(self):
        mapping = {
            "home":           ["LocalBusiness", "WebSite"],
            "blog_list":      ["Blog"],
            "blog_detail":    ["Article", "BreadcrumbList"],
            "service_list":   ["ItemList"],
            "service_detail": ["Service", "BreadcrumbList"],
            "contact":        ["ContactPage"],
            "about":          ["AboutPage"],
        }
        return mapping.get(self.page_type, ["WebPage"])

    # ── 10. Analytics ────────────────────────────────────────────
    def _analytics(self, r: PageReport):
        CAT  = "Analytics / Takip"
        html = str(self.soup)

        has_gtm  = "googletagmanager.com/gtm.js" in html or re.search(r"GTM-[A-Z0-9]+", html)
        has_ga4  = re.search(r"G-[A-Z0-9]{6,}", html) or "gtag('config'" in html
        has_ua   = re.search(r"UA-\d+-\d+", html)
        has_px   = "fbq(" in html or "connect.facebook.net" in html
        has_hj   = "static.hotjar.com" in html or "hj(" in html
        has_cls  = "clarity.ms" in html

        if not has_gtm and not has_ga4:
            r.add(CAT, "Google Analytics / GTM", Sev.ERROR,
                  "GA4 veya GTM bulunamadı — ziyaretçi takibi YOK",
                  fix="GA4 ölçüm ID'si veya GTM container tag ekleyin")
        elif has_gtm:
            r.add(CAT, "Google Tag Manager", Sev.OK, "GTM aktif ✓")
        else:
            r.add(CAT, "Google Analytics 4", Sev.OK, "GA4 aktif ✓")

        if has_ua and not has_ga4:
            r.add(CAT, "Universal Analytics (Eski)", Sev.WARNING,
                  "UA kodu var ama GA4 yok — UA 2023'te kapatıldı",
                  fix="GA4 geçişini tamamlayın")

        if not has_px:
            r.add(CAT, "Meta Pixel", Sev.INFO,
                  "Meta Pixel bulunamadı",
                  fix="Facebook/Instagram kampanyaları için Meta Pixel ekleyin")
        else:
            r.add(CAT, "Meta Pixel", Sev.OK, "Meta Pixel aktif ✓")

        if has_hj:
            r.add(CAT, "Hotjar", Sev.OK, "Hotjar aktif ✓")
        if has_cls:
            r.add(CAT, "Microsoft Clarity", Sev.OK, "Microsoft Clarity aktif ✓")

    # ── 11. Formlar ──────────────────────────────────────────────
    def _forms(self, r: PageReport):
        CAT   = "Form Kontrolü"
        forms = self.soup.find_all("form")

        for i, form in enumerate(forms, 1):
            method = (form.get("method") or "get").lower()
            action = form.get("action", "")

            if method == "get":
                r.add(CAT, f"Form #{i} Method", Sev.WARNING,
                      f"Form #{i} method=GET kullanıyor (veriler URL'de görünür)",
                      fix='method="post" kullanın')

            # Honeypot / CSRF yoksa bilgi ver
            has_csrf = bool(form.find("input", attrs={"name": re.compile("csrf|token|_token", re.I)}))
            if not has_csrf and method == "post":
                r.add(CAT, f"Form #{i} CSRF Koruması", Sev.INFO,
                      f"Form #{i} CSRF token içermiyor (framework'e göre değişir)",
                      fix="Server-side CSRF koruması kullanıldığını doğrulayın")

        # Google Maps iframe title
        maps = self.soup.find_all("iframe",
                                   src=lambda s: s and "google.com/maps" in s)
        for iframe in maps:
            if not iframe.get("title"):
                r.add(CAT, "Google Maps iframe title", Sev.WARNING,
                      "Google Maps iframe'inde title attribute eksik",
                      detail="Erişilebilirlik ve SEO için önemli",
                      fix='title="Konum Haritası" attribute ekleyin')

    # ── 12. Teknik SEO ───────────────────────────────────────────
    def _technical(self, r: PageReport):
        CAT = "Teknik SEO"

        # HTTPS
        if self.url.startswith("http://"):
            r.add(CAT, "HTTPS", Sev.ERROR,
                  "Sayfa HTTP üzerinden yükleniyor",
                  fix="SSL ekleyin + HTTP → HTTPS yönlendirmesi kurun")
        else:
            r.add(CAT, "HTTPS", Sev.OK, "HTTPS aktif ✓")

        # Viewport
        vp = self.soup.find("meta", attrs={"name": "viewport"})
        if not vp:
            r.add(CAT, "Viewport Meta", Sev.ERROR,
                  "Viewport meta eksik — mobil uyum bozulur",
                  fix='<meta name="viewport" content="width=device-width, initial-scale=1">')
        else:
            r.add(CAT, "Viewport Meta", Sev.OK, "Viewport meta var ✓")

        # Charset
        charset = self.soup.find("meta", attrs={"charset": True}) or \
                  self.soup.find("meta", attrs={"http-equiv": re.compile("content-type", re.I)})
        if not charset:
            r.add(CAT, "Charset", Sev.WARNING,
                  "Charset meta eksik",
                  fix='<meta charset="UTF-8"> ekleyin')

        # HTML lang
        html_tag = self.soup.find("html")
        if html_tag and not html_tag.get("lang"):
            r.add(CAT, "HTML lang Attribute", Sev.WARNING,
                  "HTML etiketinde lang attribute yok",
                  fix='<html lang="tr"> şeklinde dil belirtin')
        elif html_tag and html_tag.get("lang"):
            r.add(CAT, "HTML lang Attribute", Sev.OK,
                  f'lang="{html_tag["lang"]}" tanımlı ✓')

        # robots meta noindex
        robots_meta = self.soup.find("meta", attrs={"name": re.compile("robots", re.I)})
        if robots_meta:
            content = robots_meta.get("content", "").lower()
            if "noindex" in content:
                r.add(CAT, "Robots Meta – noindex", Sev.ERROR,
                      f"Sayfa arama motorlarından gizleniyor: {content}",
                      fix="Kasıtlı değilse noindex'i kaldırın")
            elif "nofollow" in content:
                r.add(CAT, "Robots Meta – nofollow", Sev.WARNING,
                      "Sayfadaki linkler takip edilmiyor (nofollow)",
                      fix="Kasıtlı değilse nofollow'u kaldırın")

        # Load time uyarısı
        # report'ta load_time var; buraya parametre geçilmiyor ama
        # ana döngüde koyabiliriz; şimdilik pass

    # ── 13. İçerik Kalitesi ──────────────────────────────────────
    def _content(self, r: PageReport):
        CAT    = "İçerik Kalitesi"
        body   = self.soup.find("main") or self.soup.find("article") or self.soup.find("body")
        if not body:
            return

        text  = re.sub(r'\s+', ' ', body.get_text(separator=" ", strip=True))
        words = len(text.split())
        min_w = (self.config.get("min_word_count") or {}).get(
                    self.page_type,
                    (self.config.get("min_word_count") or {}).get("default", 300))

        if words < min_w:
            r.add(CAT, "Kelime Sayısı", Sev.WARNING,
                  f"İçerik az: {words} kelime (min önerilen: {min_w})",
                  fix=f"Daha açıklayıcı içerik ekleyin; hedef ≥{min_w} kelime")
        else:
            r.add(CAT, "Kelime Sayısı", Sev.OK,
                  f"İçerik yeterli: {words} kelime ✓")

        # Breadcrumb (detay sayfaları)
        if self.page_type in ("blog_detail", "service_detail", "product_detail"):
            bc = (self.soup.find(attrs={"aria-label": re.compile("breadcrumb", re.I)}) or
                  self.soup.find(class_=re.compile("breadcrumb", re.I)))
            if not bc:
                r.add(CAT, "Breadcrumb Navigasyonu", Sev.INFO,
                      "Görünür breadcrumb navigasyonu bulunamadı",
                      fix="Kullanıcı deneyimi + BreadcrumbList schema için breadcrumb ekleyin")

        # Yazar bilgisi (blog)
        if self.page_type == "blog_detail":
            author = (self.soup.find(attrs={"rel": "author"}) or
                      self.soup.find(class_=re.compile(r"\bauthor\b", re.I)) or
                      self.soup.find(attrs={"itemprop": "author"}))
            if not author:
                r.add(CAT, "Yazar Bilgisi", Sev.WARNING,
                      "Yazar bilgisi bulunamadı",
                      fix="E-E-A-T sinyalleri için yazar adı ve kısa bio ekleyin")

            # Yayın tarihi
            date = (self.soup.find("time") or
                    self.soup.find(attrs={"itemprop": re.compile("date", re.I)}) or
                    self.soup.find(class_=re.compile(r"date|tarih|time", re.I)))
            if not date:
                r.add(CAT, "Yayın Tarihi", Sev.WARNING,
                      "Yayın tarihi bulunamadı",
                      fix="datePublished + dateModified hem schema'ya hem görünüme ekleyin")

            # Okuma süresi
            reading = self.soup.find(class_=re.compile(r"reading.?time|okuma", re.I))
            if not reading:
                r.add(CAT, "Okuma Süresi", Sev.INFO,
                      "Tahmini okuma süresi gösterilmiyor",
                      fix=f"~{max(1, words // 200)} dakika okuma süresi ekleyebilirsiniz")

        # Hizmet detayı için CTA kontrolü
        if self.page_type == "service_detail":
            cta = (self.soup.find(class_=re.compile(r"cta|teklif|contact|iletisim", re.I)) or
                   self.soup.find("a", string=re.compile(r"teklif|iletişim|ara|fiyat", re.I)))
            if not cta:
                r.add(CAT, "Servis Sayfası CTA", Sev.INFO,
                      "Açık bir CTA (Call-to-Action) butonu/bölümü bulunamadı",
                      fix="'Teklif Al' / 'Bizimle İletişime Geç' gibi net CTA ekleyin")


# ──────────────────────────────────────────────────────────────
#  Site Geneli Kontroller (robots.txt, sitemap)
# ──────────────────────────────────────────────────────────────

def check_site_wide(base_url: str, fetch_text) -> List[Issue]:
    issues = []

    def add(cat, name, sev, msg, detail="", fix=""):
        issues.append(Issue(cat, name, sev, msg, detail, fix))

    # robots.txt
    robots_url = base_url.rstrip("/") + "/robots.txt"
    status, robots_text = fetch_text(robots_url)

    if status != 200:
        add("Robots.txt & Sitemap", "robots.txt", Sev.ERROR,
            f"robots.txt bulunamadı (HTTP {status})",
            fix="Kök dizine robots.txt ekleyin")
    else:
        add("Robots.txt & Sitemap", "robots.txt", Sev.OK,
            f"robots.txt mevcut ({len(robots_text)} karakter)")

        # Sitemap referansı var mı
        if "sitemap" not in robots_text.lower():
            add("Robots.txt & Sitemap", "Sitemap Direktifi", Sev.WARNING,
                "robots.txt içinde Sitemap direktifi yok",
                fix="robots.txt'e 'Sitemap: https://domain.com/sitemap.xml' ekleyin")

    # sitemap.xml
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    status, sitemap_text = fetch_text(sitemap_url)

    if status != 200:
        add("Robots.txt & Sitemap", "sitemap.xml", Sev.ERROR,
            f"sitemap.xml bulunamadı (HTTP {status})",
            fix="XML sitemap oluşturun ve Google Search Console'a gönderin")
    else:
        url_count = sitemap_text.count("<loc>")
        add("Robots.txt & Sitemap", "sitemap.xml", Sev.OK,
            f"sitemap.xml mevcut ({url_count} URL)")

        # WWW tutarsızlığı
        parsed_base = urlparse(base_url)
        base_www    = "www." in parsed_base.netloc

        sitemap_urls = re.findall(r"<loc>(.*?)</loc>", sitemap_text)
        if base_www:
            bad = [u for u in sitemap_urls if "www." not in urlparse(u).netloc]
        else:
            bad = [u for u in sitemap_urls if "www." in urlparse(u).netloc]

        if bad:
            add("Robots.txt & Sitemap", "Sitemap WWW Tutarsızlığı", Sev.ERROR,
                f"Sitemap'te {len(bad)} URL canonical format ile uyumsuz",
                detail=bad[:3],
                fix="Tüm sitemap URL'lerini canonical domain formatına uyarlayın")

        # HTTP URL'ler varsa
        http_urls = [u for u in sitemap_urls if u.startswith("http://")]
        if http_urls:
            add("Robots.txt & Sitemap", "Sitemap HTTP URL", Sev.WARNING,
                f"Sitemap'te {len(http_urls)} adet HTTP (non-HTTPS) URL var",
                fix="Tüm sitemap URL'lerini https:// ile başlatın")

    return issues
