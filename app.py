"""
app.py – SEO Analyzer Web Arayüzü
"""
import os
import sys
import csv
import io
import json
import uuid
import threading
import queue
import webbrowser
from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from urllib.parse import urlparse

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fetcher import fetch_page, fetch_text_url
from checks import PageAnalyzer, PageReport, SiteReport, check_site_wide, Sev
from reporter import save_html, save_markdown, save_json
import inspector

if getattr(sys, "frozen", False):
    _BASE    = os.path.dirname(sys.executable)
    _MEIPASS = getattr(sys, "_MEIPASS", _BASE)
    app = Flask(__name__, template_folder=os.path.join(_MEIPASS, "templates"))
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__)

jobs: dict[str, queue.Queue] = {}
OUT_DIR = os.path.join(_BASE, "rapor")


def run_analysis(job_id: str, cfg: dict):
    q = jobs[job_id]

    def emit(obj):
        q.put(obj)

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        settings = cfg.get("settings", {})
        base_url = cfg["base_url"].rstrip("/")
        report = SiteReport(site_name=cfg["site_name"], base_url=base_url)

        emit({"type": "status", "msg": "robots.txt ve sitemap.xml kontrol ediliyor..."})
        site_issues = check_site_wide(
            base_url,
            lambda u: fetch_text_url(u, settings.get("timeout", 15)),
        )
        report.site_issues = site_issues
        for i in site_issues:
            emit({"type": "site_issue", "severity": i.severity.value,
                  "name": i.name, "message": i.message})

        pages = cfg.get("pages", [])
        for idx, page_cfg in enumerate(pages):
            url = base_url + page_cfg["url"]
            label = page_cfg.get("label", page_cfg["url"])
            page_type = page_cfg.get("type", "default")

            emit({"type": "status", "msg": f"[{idx+1}/{len(pages)}] {label} analiz ediliyor..."})

            fetched = fetch_page(url, settings)
            pr = PageReport(
                url=fetched.get("url", url),
                label=label,
                page_type=page_type,
                status_code=fetched.get("status_code", 0),
                load_time=fetched.get("load_time", 0),
                render_method=fetched.get("method", "?"),
            )

            if fetched.get("error") or not fetched.get("soup"):
                pr.add("Bağlantı", "Sayfa Yüklenemedi", Sev.ERROR,
                       fetched.get("error", "Bilinmeyen hata"),
                       fix="URL'nin doğruluğunu kontrol edin")
            else:
                PageAnalyzer(
                    soup=fetched["soup"], url=fetched["url"],
                    page_type=page_type, config=cfg,
                ).analyze(pr)

            report.pages.append(pr)
            emit({
                "type": "page_done",
                "label": label,
                "url": pr.url,
                "score": pr.score,
                "status_code": pr.status_code,
                "load_time": pr.load_time,
                "render_method": pr.render_method,
                "errors": len(pr.errors),
                "warnings": len(pr.warnings),
                "issues": [
                    {"category": i.category, "severity": i.severity.value,
                     "name": i.name, "message": i.message, "fix": i.fix}
                    for i in pr.issues
                ],
            })

        emit({"type": "status", "msg": "Raporlar kaydediliyor..."})
        save_html(report, OUT_DIR)
        save_markdown(report, OUT_DIR)
        save_json(report, OUT_DIR)

        emit({
            "type": "done",
            "avg_score": report.avg_score,
            "total_errors": report.total_errors,
            "total_warnings": report.total_warnings,
            "pages_count": len(report.pages),
        })

    except Exception as e:
        emit({"type": "error", "msg": str(e)})
    finally:
        q.put(None)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = queue.Queue()
    threading.Thread(target=run_analysis, args=(job_id, data), daemon=True).start()
    return {"job_id": job_id}


@app.route("/stream/<job_id>")
def stream(job_id):
    q = jobs.get(job_id)
    if not q:
        return "Job bulunamadı", 404

    def generate():
        while True:
            item = q.get()
            if item is None:
                jobs.pop(job_id, None)
                yield "data: {\"type\":\"end\"}\n\n"
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/report")
def report():
    path = os.path.join(OUT_DIR, "seo_raporu.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "Rapor henüz oluşturulmadı.", 404


@app.route("/api/inspect", methods=["POST"])
def api_inspect():
    data   = request.get_json()
    url    = (data.get("url") or "").strip()
    tab    = data.get("tab", "")
    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    parsed   = urlparse(url if "://" in url else "https://" + url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Tabs that need the full page HTML
    if tab in ("h", "m", "og", "i", "sc", "bl", "o", "k", "hl"):
        res = inspector.fetch_url(url)
        if not res["ok"]:
            return jsonify({"error": res["error"]}), 400
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res["text"], "lxml")
        final_url = res.get("url", url)

    if tab == "h":
        return jsonify(inspector.get_headings(soup))
    elif tab == "m":
        return jsonify(inspector.get_meta(soup, final_url))
    elif tab == "og":
        return jsonify(inspector.get_og(soup))
    elif tab == "i":
        return jsonify({"images": inspector.get_images(soup, final_url)})
    elif tab == "sc":
        return jsonify({"schemas": inspector.get_schema(soup)})
    elif tab == "bl":
        return jsonify({"links": inspector.check_broken_links(soup, final_url)})
    elif tab == "o":
        return jsonify(inspector.get_readability(soup))
    elif tab == "k":
        mode = int(data.get("mode", 1))
        return jsonify({"keywords": inspector.get_keywords(soup, mode)})
    elif tab == "hl":
        return jsonify(inspector.get_hreflang(soup, final_url))
    elif tab == "sm":
        return jsonify(inspector.get_sitemap(base_url))
    elif tab == "w":
        domain = parsed.netloc.replace("www.", "")
        return jsonify(inspector.get_whois(domain))
    elif tab == "r":
        return jsonify(inspector.get_robots(base_url))
    elif tab == "cv":
        return jsonify(inspector.get_cwv(url))
    elif tab == "f":
        return jsonify(inspector.get_performance(url))
    elif tab == "ps":
        api_key  = data.get("apiKey", "")
        strategy = data.get("strategy", "mobile")
        if not api_key:
            return jsonify({"error": "PageSpeed API key gerekli. Ayarlar ikonuna tıklayın."})
        return jsonify(inspector.get_pagespeed(url, strategy, api_key))
    else:
        return jsonify({"error": "Bilinmeyen sekme"}), 400


@app.route("/api/sitemap-pages", methods=["POST"])
def api_sitemap_pages():
    data        = request.get_json()
    base_url    = (data.get("base_url") or "").strip().rstrip("/")
    sitemap_url = (data.get("sitemap_url") or "").strip()

    if not sitemap_url and not base_url:
        return jsonify({"error": "sitemap_url veya base_url gerekli"}), 400

    # Derive base_url from sitemap_url when not provided
    if sitemap_url and not base_url:
        p = urlparse(sitemap_url)
        base_url = f"{p.scheme}://{p.netloc}"

    result  = inspector.get_sitemap(base_url, sitemap_url)
    entries = result.get("entries", [])

    # If sitemap index, fetch first child sitemap for real page URLs
    if result.get("type") == "index" and entries:
        first_loc = (entries[0].get("loc") or "").strip()
        if first_loc:
            child = inspector.get_sitemap("", first_loc)
            if child.get("entries"):
                entries = child["entries"]

    if not entries:
        return jsonify({"error": result.get("error", "Sitemap boş veya bulunamadı")}), 400

    pages = []
    for e in entries:
        loc = (e.get("loc") or "").strip()
        if not loc:
            continue
        path = loc[len(base_url):] if loc.startswith(base_url) else loc
        path = path or "/"
        pages.append({"url": path, "label": path, "type": "default"})

    return jsonify({"pages": pages[:60], "total": len(entries)})


@app.route("/download/csv")
def download_csv():
    path = os.path.join(OUT_DIR, "seo_raporu.json")
    if not os.path.exists(path):
        return "Henüz analiz yapılmadı.", 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["Sayfa", "URL", "Skor", "HTTP", "Yük(s)", "Hata", "Uyarı",
                "Kategori", "Önem", "Sorun", "Mesaj", "Çözüm"])

    for page in data.get("pages", []):
        issues = page.get("issues", [])
        if not issues:
            w.writerow([page["label"], page["url"], page["score"],
                        page["status_code"], page["load_time"],
                        page["errors"], page["warnings"], "", "", "", "", ""])
        for issue in issues:
            w.writerow([page["label"], page["url"], page["score"],
                        page["status_code"], page["load_time"],
                        page["errors"], page["warnings"],
                        issue["category"], issue["severity"],
                        issue["name"], issue["message"], issue.get("fix", "")])

    out.seek(0)
    return Response(
        "﻿" + out.getvalue(),   # BOM for Excel UTF-8
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=seo_raporu.csv"},
    )


if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
