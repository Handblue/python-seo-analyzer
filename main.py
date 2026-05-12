"""
main.py – SEO Analyzer giriş noktası

Kullanım:
  python main.py                    → config.yaml'ı kullanır
  python main.py --config baska.yaml
"""

import os
import sys
import argparse

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import yaml
from colorama import init, Fore, Style
from urllib.parse import urljoin

from fetcher import fetch_page, fetch_text_url
from checks import PageAnalyzer, PageReport, SiteReport, check_site_wide, Sev
from reporter import save_html, save_markdown, save_json

init(autoreset=True)


# ──────────────────────────────────────────────────────────────
def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_banner():
    sep = "-" * 55
    print(f"\n{Fore.CYAN}{sep}")
    print(f"  SEO Analyzer")
    print(f"{sep}{Style.RESET_ALL}\n")


def print_page_result(page: PageReport):
    score = page.score
    color = Fore.GREEN if score >= 80 else (Fore.YELLOW if score >= 60 else Fore.RED)
    print(f"\n  {color}[{score:3d}/100]{Style.RESET_ALL}  {page.label}")
    print(f"           {Fore.WHITE}{page.url}{Style.RESET_ALL}")
    print(f"           HTTP {page.status_code}  |  {page.load_time}s  |  {page.render_method}")

    if page.errors:
        for e in page.errors:
            print(f"           {Fore.RED}✗ {e.name}: {e.message}{Style.RESET_ALL}")
    if page.warnings:
        for w in page.warnings[:5]:  # terminalde ilk 5 uyarı
            print(f"           {Fore.YELLOW}⚠ {w.name}: {w.message}{Style.RESET_ALL}")
        if len(page.warnings) > 5:
            print(f"           {Fore.YELLOW}  ... ve {len(page.warnings)-5} uyarı daha (HTML raporu inceleyin){Style.RESET_ALL}")


# ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SEO Analyzer")
    parser.add_argument("--config", default="config.yaml", help="Config dosyası yolu")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"{Fore.RED}Config dosyası bulunamadı: {args.config}{Style.RESET_ALL}")
        sys.exit(1)

    cfg      = load_config(args.config)
    settings = cfg.get("settings", {})
    base_url = cfg["base_url"].rstrip("/")

    out_dir  = settings.get("output_dir", "./rapor")
    os.makedirs(out_dir, exist_ok=True)

    print_banner()
    print(f"  Site  : {Fore.CYAN}{cfg['site_name']}{Style.RESET_ALL}")
    print(f"  URL   : {base_url}")
    print(f"  Sayfa : {len(cfg['pages'])}")
    print(f"  Çıktı : {out_dir}\n")

    report = SiteReport(site_name=cfg["site_name"], base_url=base_url)

    # ── Site geneli kontroller ─────────────────────────────────
    print(f"{Fore.CYAN}  ▸ robots.txt ve sitemap.xml kontrol ediliyor...{Style.RESET_ALL}")
    site_issues = check_site_wide(base_url, lambda u: fetch_text_url(u, settings.get("timeout", 15)))
    report.site_issues = site_issues
    for i in site_issues:
        color = Fore.RED if i.severity.value == "error" else \
                (Fore.YELLOW if i.severity.value == "warning" else Fore.GREEN)
        print(f"    {color}{i.severity.value.upper():7s}{Style.RESET_ALL}  {i.name}: {i.message}")

    # ── Sayfa analizleri ───────────────────────────────────────
    print(f"\n{Fore.CYAN}  ▸ Sayfalar analiz ediliyor...{Style.RESET_ALL}")

    for page_cfg in cfg["pages"]:
        url       = base_url + page_cfg["url"]
        label     = page_cfg.get("label", page_cfg["url"])
        page_type = page_cfg.get("type", "default")

        print(f"\n  → {label}  ({url})")

        fetched = fetch_page(url, settings)

        page_report = PageReport(
            url           = fetched.get("url", url),
            label         = label,
            page_type     = page_type,
            status_code   = fetched.get("status_code", 0),
            load_time     = fetched.get("load_time", 0),
            render_method = fetched.get("method", "?"),
        )

        if fetched.get("error") or not fetched.get("soup"):
            page_report.add(
                "Bağlantı", "Sayfa Yüklenemedi",
                Sev.ERROR,
                fetched.get("error", "Bilinmeyen hata"),
                fix="URL'nin doğruluğunu ve sitenin erişilebilirliğini kontrol edin"
            )
        else:
            analyzer = PageAnalyzer(
                soup      = fetched["soup"],
                url       = fetched["url"],
                page_type = page_type,
                config    = cfg,
            )
            analyzer.analyze(page_report)

        report.pages.append(page_report)
        print_page_result(page_report)

        # Load time uyarısı
        if page_report.load_time > 3:
            print(f"           {Fore.YELLOW}⚠ Sayfa yavaş yüklendi: {page_report.load_time}s (>3s){Style.RESET_ALL}")

    # ── Raporları kaydet ───────────────────────────────────────
    print(f"\n{Fore.CYAN}  ▸ Raporlar kaydediliyor...{Style.RESET_ALL}")

    html_path = save_html(report, out_dir)
    md_path   = save_markdown(report, out_dir)
    json_path = save_json(report, out_dir)

    print(f"    {Fore.GREEN}✓{Style.RESET_ALL} HTML     : {html_path}")
    print(f"    {Fore.GREEN}✓{Style.RESET_ALL} Markdown : {md_path}")
    print(f"    {Fore.GREEN}✓{Style.RESET_ALL} JSON     : {json_path}")

    # ── Özet ──────────────────────────────────────────────────
    avg   = report.avg_score
    color = Fore.GREEN if avg >= 80 else (Fore.YELLOW if avg >= 60 else Fore.RED)
    print(f"\n  {'─'*45}")
    print(f"  Ortalama Skor  : {color}{avg}/100{Style.RESET_ALL}")
    print(f"  Toplam Hata    : {Fore.RED}{report.total_errors}{Style.RESET_ALL}")
    print(f"  Toplam Uyarı   : {Fore.YELLOW}{report.total_warnings}{Style.RESET_ALL}")
    print(f"  {'─'*45}\n")


if __name__ == "__main__":
    main()
