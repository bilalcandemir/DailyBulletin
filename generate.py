#!/usr/bin/env python3
"""
The Bilal's Times — Morning Bulletin
Run: python3 generate.py
Requirements: pip3 install pyyaml jinja2 requests playwright
              python3 -m playwright install chromium
"""

import yaml
import datetime
import random
import os
import subprocess
import sys
import asyncio

try:
    import requests
    from jinja2 import Environment, FileSystemLoader
    from playwright.async_api import async_playwright
except ImportError:
    print("Missing packages. Run:")
    print("  pip3 install pyyaml jinja2 requests playwright")
    print("  python3 -m playwright install chromium")
    sys.exit(1)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE   = os.path.join(BASE_DIR, "config.yaml")
TASKS_FILE    = os.path.join(BASE_DIR, "tasks.yaml")
SCHEDULE_FILE = os.path.join(BASE_DIR, "weekly_schedule.yaml")
QUOTES_FILE   = os.path.join(BASE_DIR, "quotes.txt")
NOTES_FILE    = os.path.join(BASE_DIR, "notes.txt")
NOTES_ARCHIVE = os.path.join(BASE_DIR, "notes_archive")
TEMPLATE_DIR  = os.path.join(BASE_DIR, "templates")

# ── loaders ───────────────────────────────────────

def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_schedule(weekday):
    data = load_yaml(SCHEDULE_FILE)
    keys = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    ordered = []
    for i in range(7):
        k = keys[(weekday + i) % 7]
        entry = dict(data["schedule"].get(k, {}))
        entry["is_today"] = (i == 0)
        ordered.append(entry)
    return ordered

def load_random_quote():
    with open(QUOTES_FILE, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    return random.choice(lines) if lines else ""

def load_and_archive_notes(today):
    """Read notes.txt, return as task list, then archive and clear."""
    if not os.path.exists(NOTES_FILE):
        return []
    with open(NOTES_FILE, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    if not lines:
        return []
    # Archive
    os.makedirs(NOTES_ARCHIVE, exist_ok=True)
    archive_path = os.path.join(NOTES_ARCHIVE, f"notes_{today.isoformat()}.txt")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # Clear notes.txt (keep header comment)
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        f.write("# Gün boyunca buraya not ekle — her satır yarınki bültende görev olarak çıkar.\n")
    return [{"text": line, "priority": "medium", "time": "", "source": "note"} for line in lines]

# ── weather ───────────────────────────────────────

def fetch_weather(city, api_key, units="metric"):
    if not api_key or api_key.startswith("BURAYA"):
        return {"temp": "—", "feels_like": "—", "description": "No data", "humidity": "—"}
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": units, "lang": "en"},
            timeout=5
        )
        d = r.json()
        return {
            "temp":        round(d["main"]["temp"]),
            "feels_like":  round(d["main"]["feels_like"]),
            "description": d["weather"][0]["description"].capitalize(),
            "humidity":    d["main"]["humidity"],
        }
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return {"temp": "—", "feels_like": "—", "description": "No data", "humidity": "—"}

# ── jira ──────────────────────────────────────────

def fetch_jira_tasks(cloud_id, email, max_issues=2):
    """Fetch Jira issues due within 1 day via Jira REST API (Basic Auth)."""
    if not cloud_id or not email:
        return []
    try:
        token_file = os.path.expanduser("~/.bulletin_jira_token")
        if not os.path.exists(token_file):
            print("Jira token not found — skipping Jira tasks.")
            return []
        with open(token_file) as f:
            token = f.read().strip()

        jql = (
            "assignee = currentUser() "
            "AND due <= endOfDay(\"+1\") "
            "AND statusCategory != Done "
            "ORDER BY due ASC"
        )
        r = requests.get(
            f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/search",
            auth=(email, token),
            headers={"Accept": "application/json"},
            params={"jql": jql, "maxResults": max_issues,
                    "fields": "summary,due,status,priority"},
            timeout=8,
        )
        issues = r.json().get("issues", [])
        result = []
        for issue in issues[:max_issues]:
            f = issue.get("fields", {})
            due = f.get("due", "")
            due_label = ""
            if due:
                due_dt = datetime.date.fromisoformat(due)
                diff = (due_dt - datetime.date.today()).days
                due_label = "today" if diff == 0 else "tomorrow"
            result.append({
                "text":     f.get("summary", issue["key"]),
                "key":      issue["key"],
                "due":      due_label,
                "priority": f.get("priority", {}).get("name", "Medium").lower(),
                "status":   f.get("status", {}).get("name", ""),
                "source":   "jira",
            })
        return result
    except Exception as e:
        print(f"Jira fetch failed: {e}")
        return []

# ── guardian ──────────────────────────────────────

def _strip_html(text):
    import re
    return re.sub(r"<[^>]+>", "", text or "").strip()

def fetch_guardian_news(api_key, sections, page_size=9, section_sizes=None):
    if not api_key or api_key.startswith("BURAYA"):
        return []
    try:
        all_articles = []
        default_per = max(1, page_size // len(sections))
        for section in sections:
            per_section = (section_sizes or {}).get(section, default_per)
            r = requests.get(
                "https://content.guardianapis.com/search",
                params={
                    "api-key":     api_key,
                    "section":     section,
                    "page-size":   per_section,
                    "order-by":    "newest",
                    "show-fields": "headline,trailText,standfirst,bodyText,byline,thumbnail",
                },
                timeout=8,
            )
            items = r.json().get("response", {}).get("results", [])
            for item in items:
                fields = item.get("fields", {})
                headline   = _strip_html(fields.get("headline") or item.get("webTitle", ""))
                summary    = _strip_html(fields.get("trailText", ""))
                standfirst = _strip_html(fields.get("standfirst", ""))
                body_extra = ""
                if fields.get("bodyText"):
                    import re as _re
                    raw = _strip_html(fields["bodyText"])
                    sentences = _re.split(r'(?<=[.!?])\s+', raw)
                    body_extra = " ".join(sentences[:4])
                parts  = [p for p in [standfirst, summary, body_extra] if p]
                detail = " ".join(dict.fromkeys(parts)) if parts else ""
                all_articles.append({
                    "section":   item.get("sectionName", section.title()),
                    "headline":  headline,
                    "summary":   summary,
                    "detail":    detail,
                    "byline":    _strip_html(fields.get("byline", "")),
                    "thumbnail": fields.get("thumbnail", ""),
                })
        return all_articles[:page_size]
    except Exception as e:
        print(f"Guardian fetch failed: {e}")
        return []

# ── language module ───────────────────────────────

def fetch_language_module(articles, api_key):
    """Generate writing prompt + collocations from today's news via Claude."""
    if not api_key or api_key.startswith("YOUR"):
        return None
    try:
        import anthropic, json
        client = anthropic.Anthropic(api_key=api_key)

        snippets = "\n".join(
            f"- {a['headline']}: {a.get('detail','')[:300]}"
            for a in articles[:6]
        )

        result = client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": f"""You are generating a daily English language-learning module for a printed newspaper.

Based on today's articles:
{snippets}

Return ONLY valid JSON (no markdown, no extra text):
{{
  "writing_prompt": "One open-ended question (max 25 words) tied to a specific article above.",
  "collocations": [
    {{"phrase": "verb+noun or adj+noun pair", "sentence": "Short news-style example sentence (max 12 words).", "note": "Brief meaning (3-5 words)"}},
    {{"phrase": "...", "sentence": "...", "note": "..."}},
    {{"phrase": "...", "sentence": "...", "note": "..."}},
    {{"phrase": "...", "sentence": "...", "note": "..."}},
    {{"phrase": "...", "sentence": "...", "note": "..."}},
    {{"phrase": "...", "sentence": "...", "note": "..."}}
  ]
}}"""}]
        )
        raw = next(b.text for b in result.content if hasattr(b, "text")).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"Language module failed: {e}")
        return None

# ── PDF ───────────────────────────────────────────

async def html_to_pdf(html_str: str, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page()
        await page.set_content(html_str, wait_until="networkidle", timeout=30000)
        await page.pdf(
            path             = output_path,
            format           = "A4",
            print_background = True,
            margin           = {"top": "0.6cm", "bottom": "0.6cm",
                                "left": "0.8cm", "right": "0.8cm"},
        )
        await browser.close()
    print(f"PDF generated: {output_path}")

def print_pdf(pdf_path, printer_name=""):
    cmd = ["lp"] + (["-d", printer_name] if printer_name else []) + [pdf_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("Sent to printer." if r.returncode == 0 else f"Printer error: {r.stderr}")

def cleanup_old(output_dir, keep_days):
    cutoff = datetime.date.today() - datetime.timedelta(days=keep_days)
    for f in os.listdir(output_dir):
        if not f.endswith(".pdf"): continue
        mtime = datetime.date.fromtimestamp(os.path.getmtime(os.path.join(output_dir, f)))
        if mtime < cutoff:
            os.remove(os.path.join(output_dir, f))
            print(f"Deleted: {f}")

# ── main ──────────────────────────────────────────

def main():
    today   = datetime.date.today()
    weekday = today.weekday()

    gun = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    ay  = ["","January","February","March","April","May","June",
           "July","August","September","October","November","December"]
    tarih = f"{gun[weekday]}, {today.day} {ay[today.month]} {today.year}"

    cfg      = load_yaml(CONFIG_FILE)
    tasks    = load_yaml(TASKS_FILE).get("today_tasks", [])
    notes    = load_and_archive_notes(today)
    schedule = load_schedule(weekday)
    habits   = cfg.get("habits", [])
    weather  = fetch_weather(cfg["user"]["city"],
                             cfg["weather"]["api_key"],
                             cfg["weather"].get("units", "metric"))

    j_cfg      = cfg.get("jira", {})
    jira_tasks = []
    if j_cfg.get("enabled", False):
        jira_tasks = fetch_jira_tasks(
            j_cfg.get("cloud_id", ""),
            j_cfg.get("email", ""),
            j_cfg.get("max_issues", 2),
        )

    g_cfg = cfg.get("guardian", {})
    news  = fetch_guardian_news(
                g_cfg.get("api_key", ""),
                g_cfg.get("sections", ["world"]),
                g_cfg.get("page_size", 9),
                g_cfg.get("section_sizes", None),
            )

    bw_mode = cfg.get("printer", {}).get("bw_mode", False)

    # Language module (Claude API)
    lang_module = None
    cl_cfg = cfg.get("claude", {})
    if cl_cfg.get("enabled", False) and news:
        token_file = os.path.expanduser("~/.bulletin_claude_token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                cl_key = f.read().strip()
            lang_module = fetch_language_module(news, cl_key)
        else:
            print("Claude token not found (~/.bulletin_claude_token) — skipping language module.")

    env      = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("bulletin.html")
    html_str = template.render(
        tarih=tarih, hafta_no=today.isocalendar()[1], yil=today.year,
        tasks=tasks, notes=notes, jira_tasks=jira_tasks,
        schedule=schedule, habits=habits,
        weather=weather, city=cfg["user"]["city"],
        news=news, bw_mode=bw_mode,
        lang_module=lang_module,
    )

    out = cfg["output"]["pdf_path"].replace(
        "bulletin_today.pdf", f"bulletin_{today.isoformat()}.pdf"
    )
    asyncio.run(html_to_pdf(html_str, out))
    cleanup_old(os.path.dirname(out), cfg["output"].get("keep_last_days", 7))

    printer_name = cfg["printer"].get("printer_name", "").strip()
    if cfg["printer"].get("enabled", False) and printer_name:
        print_pdf(out, printer_name)

if __name__ == "__main__":
    main()
