# SEO Analyzer

Python tabanlı, çok sayfalı SEO analiz aracı.  
Çıktı: **HTML** (tarayıcıda aç) + **Markdown** + **JSON**

---

## Kurulum

```bash
# 1. Bağımlılıkları yükle
pip install -r requirements.txt

# 2. Playwright kurulumu (JS render için)
playwright install chromium
```

---

## Kullanım

### 1. config.yaml'ı düzenle

```yaml
site_name: "Müşteri Sitesi"
base_url: "https://example.com"

pages:
  - url: "/"
    label: "Anasayfa"
    type: "home"

  - url: "/blog"
    label: "Blog"
    type: "blog_list"

  - url: "/blog/ornek-yazi"
    label: "Blog Detay"
    type: "blog_detail"

  - url: "/iletisim"
    label: "İletişim"
    type: "contact"
```

### 2. Çalıştır

```bash
python main.py
# veya farklı config:
python main.py --config musteri_abc.yaml
```

### 3. Raporu aç

```
rapor/
  seo_raporu.html   ← tarayıcıda aç
  seo_raporu.md     ← Notion/Obsidian/GitHub'a yapıştır
  seo_raporu.json   ← başka araçlarla işle
```

---

## Sayfa Türleri

| type | Açıklama |
|------|----------|
| `home` | Anasayfa |
| `blog_list` | Blog listesi |
| `blog_detail` | Tek blog yazısı |
| `service_list` | Hizmetler listesi |
| `service_detail` | Tek hizmet sayfası |
| `contact` | İletişim |
| `about` | Hakkımızda |

---

## Kontrol Listesi

| Kategori | Kontroller |
|----------|-----------|
| Title & Meta | Title varlık/uzunluk, Meta description varlık/uzunluk |
| OG / Sosyal | og:title/description/image/url/type, twitter:card |
| Heading | H1 sayısı, hiyerarşi, tekrar eden başlıklar |
| Teknik SEO | Canonical, HTTPS, viewport, charset, lang, noindex |
| Görseller | Alt text, lazy loading, WebP format |
| Linkler | tel: format, noopener, target=_blank typo, WWW tutarlılığı |
| Schema | JSON-LD varlık, tür kontrolü, önerilen schema |
| Analytics | GA4, GTM, UA eski kod uyarısı, Meta Pixel |
| Formlar | GET/POST method, CSRF bilgisi, Maps iframe title |
| İçerik | Kelime sayısı, breadcrumb, yazar/tarih (blog), CTA (hizmet) |
| Site Geneli | robots.txt, sitemap.xml, WWW+HTTPS tutarlılığı |

---

## Çoklu Site

Her site için ayrı config dosyası oluştur:

```bash
python main.py --config sites/semax.yaml
python main.py --config sites/musteri_b.yaml
```

---

## Ayarlar

```yaml
settings:
  timeout: 30             # saniye
  use_playwright: "auto"  # auto | always | never
  output_dir: "./rapor"
  check_broken_links: false

min_word_count:
  home: 400
  blog_detail: 600
  service_detail: 500
  default: 300
```
