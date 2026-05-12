"""
reporter.py – HTML / Markdown / JSON rapor üreticisi
"""

import json
import os
from datetime import datetime
from checks import SiteReport, PageReport, Issue, Sev


# ──────────────────────────────────────────────────────────────
#  JSON
# ──────────────────────────────────────────────────────────────

def save_json(report: SiteReport, out_dir: str) -> str:
    data = {
        "site_name":      report.site_name,
        "base_url":       report.base_url,
        "analyzed_at":    datetime.now().isoformat(),
        "summary": {
            "avg_score":      report.avg_score,
            "total_errors":   report.total_errors,
            "total_warnings": report.total_warnings,
            "pages_analyzed": len(report.pages),
        },
        "site_issues": [_issue_dict(i) for i in report.site_issues],
        "pages": [_page_dict(p) for p in report.pages],
    }
    path = os.path.join(out_dir, "seo_raporu.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _issue_dict(i: Issue) -> dict:
    return {
        "category": i.category,
        "name":     i.name,
        "severity": i.severity.value,
        "message":  i.message,
        "detail":   i.detail,
        "fix":      i.fix,
    }


def _page_dict(p: PageReport) -> dict:
    return {
        "url":           p.url,
        "label":         p.label,
        "page_type":     p.page_type,
        "status_code":   p.status_code,
        "load_time":     p.load_time,
        "render_method": p.render_method,
        "score":         p.score,
        "errors":        len(p.errors),
        "warnings":      len(p.warnings),
        "issues":        [_issue_dict(i) for i in p.issues],
    }


# ──────────────────────────────────────────────────────────────
#  Markdown
# ──────────────────────────────────────────────────────────────

SEV_EMOJI = {
    Sev.ERROR:   "❌",
    Sev.WARNING: "⚠️",
    Sev.OK:      "✅",
    Sev.INFO:    "ℹ️",
}


def save_markdown(report: SiteReport, out_dir: str) -> str:
    lines = []
    now   = datetime.now().strftime("%d.%m.%Y %H:%M")

    lines += [
        f"# SEO Analiz Raporu – {report.site_name}",
        f"**Analiz Tarihi:** {now}  |  **URL:** {report.base_url}",
        "",
        "---",
        "",
        "## 📊 Özet",
        "",
        f"| Metrik | Değer |",
        f"|--------|-------|",
        f"| Ortalama Skor | **{report.avg_score}/100** |",
        f"| Toplam Hata | {report.total_errors} |",
        f"| Toplam Uyarı | {report.total_warnings} |",
        f"| Analiz Edilen Sayfa | {len(report.pages)} |",
        "",
    ]

    # Site geneli kontroller
    if report.site_issues:
        lines += ["## 🌐 Site Geneli Kontroller (robots.txt / sitemap)", ""]
        for i in report.site_issues:
            emoji = SEV_EMOJI[i.severity]
            lines.append(f"- {emoji} **{i.name}**: {i.message}")
            if i.detail:
                lines.append(f"  - *Detay:* {i.detail}")
            if i.fix:
                lines.append(f"  - 💡 *Çözüm:* {i.fix}")
        lines.append("")

    # Sayfa raporları
    for page in report.pages:
        score_label = _score_label(page.score)
        lines += [
            f"---",
            f"## 📄 {page.label}",
            f"`{page.url}` | Skor: **{page.score}/100** {score_label} | "
            f"Yük: {page.load_time}s | HTTP {page.status_code} | {page.render_method}",
            "",
        ]

        if not page.issues:
            lines.append("_Bu sayfa için sorun bulunamadı._\n")
            continue

        for cat, issues in page.by_category().items():
            lines += [f"### {cat}", ""]
            for i in issues:
                emoji = SEV_EMOJI[i.severity]
                lines.append(f"- {emoji} **{i.name}**: {i.message}")
                if i.detail:
                    detail_str = i.detail if isinstance(i.detail, str) else str(i.detail)
                    lines.append(f"  - *Detay:* {detail_str[:200]}")
                if i.fix:
                    lines.append(f"  - 💡 *Çözüm:* {i.fix}")
            lines.append("")

    path = os.path.join(out_dir, "seo_raporu.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def _score_label(score: int) -> str:
    if score >= 80: return "🟢"
    if score >= 60: return "🟡"
    return "🔴"


# ──────────────────────────────────────────────────────────────
#  HTML
# ──────────────────────────────────────────────────────────────

SEV_COLOR = {
    Sev.ERROR:   ("#ff4d4d", "#2d0000"),
    Sev.WARNING: ("#ffb347", "#2d1a00"),
    Sev.OK:      ("#4ade80", "#002d10"),
    Sev.INFO:    ("#60a5fa", "#00102d"),
}

SEV_LABEL = {
    Sev.ERROR:   "HATA",
    Sev.WARNING: "UYARI",
    Sev.OK:      "TAMAM",
    Sev.INFO:    "BİLGİ",
}


def save_html(report: SiteReport, out_dir: str) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    page_cards = ""
    for page in report.pages:
        score    = page.score
        sl       = _score_label(score)
        sc_class = "score-green" if score >= 80 else ("score-yellow" if score >= 60 else "score-red")
        cats_html = ""

        for cat, issues in page.by_category().items():
            rows = ""
            for i in issues:
                color, bg = SEV_COLOR[i.severity]
                lbl       = SEV_LABEL[i.severity]
                det = ""
                if i.detail:
                    det_str = i.detail if isinstance(i.detail, str) else str(i.detail)
                    det = f'<div class="detail">📌 {_esc(det_str[:300])}</div>'
                fix = ""
                if i.fix:
                    fix = f'<div class="fix">💡 <strong>Çözüm:</strong> {_esc(i.fix)}</div>'

                rows += f"""
                <div class="issue-row" style="border-left:3px solid {color}; background:{bg}22;">
                  <span class="badge" style="background:{color};color:#000;">{lbl}</span>
                  <div class="issue-body">
                    <strong>{_esc(i.name)}</strong> — {_esc(i.message)}
                    {det}{fix}
                  </div>
                </div>"""

            cats_html += f"""
            <div class="category">
              <h4 class="cat-title">▸ {_esc(cat)}</h4>
              {rows}
            </div>"""

        page_cards += f"""
        <div class="page-card">
          <div class="page-header">
            <div>
              <span class="page-label">{_esc(page.label)}</span>
              <span class="page-url">{_esc(page.url)}</span>
            </div>
            <div class="page-meta">
              <span class="{sc_class}">{score}/100 {sl}</span>
              <span class="meta-pill">HTTP {page.status_code}</span>
              <span class="meta-pill">{page.load_time}s</span>
              <span class="meta-pill">{page.render_method}</span>
              <span class="meta-pill err">{len(page.errors)} hata</span>
              <span class="meta-pill warn">{len(page.warnings)} uyarı</span>
            </div>
          </div>
          <div class="page-body">
            {cats_html if cats_html else '<p class="no-issues">Bu sayfa için sorun bulunamadı ✅</p>'}
          </div>
        </div>"""

    # Site-wide issues
    site_html = ""
    if report.site_issues:
        rows = ""
        for i in report.site_issues:
            color, bg = SEV_COLOR[i.severity]
            lbl       = SEV_LABEL[i.severity]
            det = f'<div class="detail">📌 {_esc(str(i.detail)[:300])}</div>' if i.detail else ""
            fix = f'<div class="fix">💡 <strong>Çözüm:</strong> {_esc(i.fix)}</div>' if i.fix else ""
            rows += f"""
            <div class="issue-row" style="border-left:3px solid {color}; background:{bg}22;">
              <span class="badge" style="background:{color};color:#000;">{lbl}</span>
              <div class="issue-body">
                <strong>{_esc(i.name)}</strong> — {_esc(i.message)}
                {det}{fix}
              </div>
            </div>"""
        site_html = f"""
        <div class="page-card">
          <div class="page-header">
            <span class="page-label">🌐 Site Geneli Kontroller</span>
            <span class="page-url">robots.txt · sitemap.xml</span>
          </div>
          <div class="page-body">{rows}</div>
        </div>"""

    # Score bar
    avg    = report.avg_score
    bar_w  = avg
    bar_c  = "#4ade80" if avg >= 80 else ("#ffb347" if avg >= 60 else "#ff4d4d")

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEO Raporu – {_esc(report.site_name)}</title>
<style>
  :root {{
    --bg: #0f0f13; --surface: #1a1a23; --surface2: #22222e;
    --text: #e2e2f0; --muted: #888; --border: #333;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 24px; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; }}
  h2 {{ font-size: 1.1rem; color: var(--muted); font-weight: 400; margin-top: 4px; }}
  .header {{ margin-bottom: 32px; }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               padding: 16px 22px; min-width: 140px; }}
  .stat-num {{ font-size: 2rem; font-weight: 800; }}
  .stat-label {{ font-size: 0.8rem; color: var(--muted); margin-top: 4px; }}
  .score-bar {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               padding: 16px 22px; flex: 1; }}
  .bar-track {{ background: #333; border-radius: 99px; height: 10px; margin-top: 10px; }}
  .bar-fill {{ height: 10px; border-radius: 99px; background: {bar_c}; width: {bar_w}%; transition: width .6s; }}
  .page-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
               margin-bottom: 20px; overflow: hidden; }}
  .page-header {{ background: var(--surface2); padding: 14px 18px;
                  display: flex; justify-content: space-between; align-items: center;
                  flex-wrap: wrap; gap: 8px; }}
  .page-label {{ font-weight: 700; font-size: 1rem; }}
  .page-url {{ color: var(--muted); font-size: 0.8rem; margin-left: 8px; }}
  .page-meta {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
  .meta-pill {{ background: #333; border-radius: 99px; padding: 3px 10px; font-size: 0.75rem; }}
  .meta-pill.err {{ background: #3d0000; color: #ff8080; }}
  .meta-pill.warn {{ background: #2d1800; color: #ffb347; }}
  .score-green {{ font-weight: 800; color: #4ade80; }}
  .score-yellow {{ font-weight: 800; color: #ffb347; }}
  .score-red {{ font-weight: 800; color: #ff4d4d; }}
  .page-body {{ padding: 16px 18px; }}
  .category {{ margin-bottom: 16px; }}
  .cat-title {{ font-size: 0.85rem; color: var(--muted); text-transform: uppercase;
                letter-spacing: .05em; margin-bottom: 8px; }}
  .issue-row {{ display: flex; gap: 10px; align-items: flex-start;
               padding: 10px 12px; border-radius: 8px; margin-bottom: 6px; }}
  .badge {{ font-size: 0.65rem; font-weight: 800; padding: 3px 7px; border-radius: 5px;
            white-space: nowrap; align-self: flex-start; margin-top: 2px; }}
  .issue-body {{ font-size: 0.88rem; line-height: 1.5; flex: 1; }}
  .detail {{ color: var(--muted); font-size: 0.82rem; margin-top: 5px;
             font-family: monospace; word-break: break-all; }}
  .fix {{ font-size: 0.82rem; margin-top: 5px; color: #a0cfff; }}
  .no-issues {{ color: #4ade80; padding: 8px 0; }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 24px 0; }}
</style>
</head>
<body>
  <div class="header">
    <h1>🔍 SEO Raporu — {_esc(report.site_name)}</h1>
    <h2>{_esc(report.base_url)} &nbsp;·&nbsp; Analiz: {now}</h2>
  </div>

  <div class="summary">
    <div class="stat-card">
      <div class="stat-num" style="color:{bar_c}">{avg}</div>
      <div class="stat-label">Ortalama Skor</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" style="color:#ff4d4d">{report.total_errors}</div>
      <div class="stat-label">Toplam Hata</div>
    </div>
    <div class="stat-card">
      <div class="stat-num" style="color:#ffb347">{report.total_warnings}</div>
      <div class="stat-label">Toplam Uyarı</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{len(report.pages)}</div>
      <div class="stat-label">Analiz Edilen Sayfa</div>
    </div>
    <div class="score-bar" style="flex:1; min-width:200px">
      <div style="font-size:.85rem;color:var(--muted)">Genel SEO Sağlığı</div>
      <div class="bar-track"><div class="bar-fill"></div></div>
      <div style="font-size:.75rem;color:var(--muted);margin-top:6px">0 — 60 Kritik &nbsp; 60 — 80 Orta &nbsp; 80+ İyi</div>
    </div>
  </div>

  {site_html}
  {page_cards}

  <hr>
  <p style="color:var(--muted);font-size:.8rem;text-align:center">
    SEO Analyzer · Oluşturulma: {now}
  </p>
</body>
</html>"""

    path = os.path.join(out_dir, "seo_raporu.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))
