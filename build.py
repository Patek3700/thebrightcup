#!/usr/bin/env python3
"""The Bright Cup — good-news aggregator.

Pulls curated positive-news RSS feeds and builds a calm LANDING page
(index.html: hero + daily meditation + big topic bubbles) plus one page per
topic (science.html, planet.html, … gems.html). Clicking a bubble opens that
topic's stories. Run hourly; the Daily Meditation + Little Gems rotate daily.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
FEEDS = json.loads((HERE / "feeds.json").read_text())["feeds"]
MAX_PER_FEED = 12
MAX_TOTAL = 60
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TheBrightCup/1.0"

STRIP_TAGS = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")

SECTIONS = [
    ("science", "🔬 Science & Discovery",
     ["scien", "research", "study", "physic", "space", "astronom", "nasa",
      "telescope", "quantum", "fossil", "archaeolog", "tomb", "ancient",
      "tech", "ai ", "robot", "engineer", "invent", "breakthrough"]),
    ("planet", "🌱 Planet & Nature",
     ["climate", "ocean", "reef", "forest", "wildlife", "animal", "species",
      "conservation", "biodivers", "solar", "renewab", "whale", "bird",
      "crow", "national park", "endangered", "rewild", "marine",
      "tree", "river", "clean energy", "emission"]),
    ("kindness", "❤️ People & Kindness",
     ["rescue", "donat", "volunteer", "hero", "kind", "generos", "gift",
      "stranger", "community", "neighbor", "raised", "fundrais", "helps",
      "helped", "saved", "adopt", "reunit"]),
    ("health", "🏥 Health & Hope",
     ["health", "medic", "cure", "cancer", "patient", "hospital", "vaccine",
      "therapy", "mental", "disease", "treatment", "wellness", "diagnos"]),
    ("culture", "✨ Culture, Sport & Joy",
     ["art", "music", "film", "festiv", "record", "athlet", "sport", "team",
      "champion", "cycle", "marathon", "museum", "danc", "book", "award"]),
]
CATCH_ALL = ("world", "🌍 World & Community")
COLORS = {
    "science":  ("#2563eb", "#eaf1ff"),
    "planet":   ("#059669", "#e6f8f0"),
    "kindness": ("#e11d48", "#fde9ee"),
    "health":   ("#0891b2", "#e3f5f9"),
    "culture":  ("#7c3aed", "#f1eafe"),
    "world":    ("#ea580c", "#fdeede"),
}
GEM_ACCENT, GEM_TINT = "#a16207", "#fbf1d2"  # treasure gold

# topic icons (feather-style line art, scale to currentColor)
ICONS = {
    "science": '<path d="M9 2h6"/><path d="M10 2v6.3L4.6 18A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-3L14 8.3V2"/><path d="M7.5 14h9"/>',
    "planet": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10Z"/><path d="M2 21c0-3 1.9-5.4 5.1-6"/>',
    "kindness": '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
    "health": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "culture": '<path d="M12 3l2.6 5.7 6.2.7-4.6 4.2 1.2 6.1L12 16.9 6.6 19.7l1.2-6.1L3.2 9.4l6.2-.7z"/>',
    "world": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.5 4 6 4 9s-1.5 6.5-4 9c-2.5-2.5-4-6-4-9s1.5-6.5 4-9z"/>',
    "gems": '<path d="M6 3h12l3.5 5.5L12 21 2.5 8.5z"/><path d="M2.5 8.5h19M9 3l-2.5 5.5L12 21l5.5-12.5L15 3"/>',
    "suggest": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
}

CONTACT_EMAIL = "jlsilverman1@gmail.com"  # FormSubmit delivers notes here


def svg_icon(slug, cls):
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS.get(slug, "")}</svg>')


# ----------------------------------------------------------------- helpers ---
def clean(text, limit=240):
    if not text:
        return ""
    text = html.unescape(STRIP_TAGS.sub(" ", text))
    text = WS.sub(" ", text).strip()
    return (text[:limit].rstrip() + "…") if len(text) > limit else text


def text_label(label):
    return re.sub(r"^[^\w]+\s*", "", label)


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def classify(article):
    hay = (article["title"] + " " + article["summary"]).lower()
    for slug, label, keys in SECTIONS:
        if any(k in hay for k in keys):
            return slug, label
    return CATCH_ALL


def first_image(item):
    for tag in ("{http://search.yahoo.com/mrss/}content",
                "{http://search.yahoo.com/mrss/}thumbnail"):
        el = item.find(tag)
        if el is not None and el.get("url"):
            return el.get("url")
    enc = item.find("enclosure")
    if enc is not None and enc.get("type", "").startswith("image") and enc.get("url"):
        return enc.get("url")
    for tag in ("{http://purl.org/rss/1.0/modules/content/}encoded", "description"):
        el = item.find(tag)
        if el is not None and el.text:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', el.text)
            if m:
                return m.group(1)
    return ""


def fetch(feed):
    out = []
    try:
        req = urllib.request.Request(feed["url"], headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=20).read()
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"  ! {feed['name']}: {e}", file=sys.stderr)
        return out
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry")
    for item in items[:MAX_PER_FEED]:
        def g(tag):
            el = item.find(tag)
            return el.text if el is not None and el.text else ""
        title = g("title") or g("{http://www.w3.org/2005/Atom}title")
        link = g("link")
        if not link:
            le = item.find("{http://www.w3.org/2005/Atom}link")
            link = le.get("href") if le is not None else ""
        desc = (g("description") or g("{http://www.w3.org/2005/Atom}summary")
                or g("{http://purl.org/rss/1.0/modules/content/}encoded"))
        pub = (g("pubDate") or g("{http://www.w3.org/2005/Atom}updated")
               or g("{http://purl.org/dc/elements/1.1/}date"))
        if not title or not link:
            continue
        d = parse_date(pub)
        out.append({
            "title": clean(title, 160), "link": link.strip(),
            "summary": clean(desc, 220), "source": feed["name"],
            "image": first_image(item),
            "published": d.isoformat() if d else "", "ts": d.timestamp() if d else 0,
        })
    print(f"  ✓ {feed['name']}: {len(out)}")
    return out


def daily_meditation():
    try:
        quotes = json.loads((HERE / "quotes.json").read_text())
    except Exception:
        return ("We are what we think.", "The Buddha · Dhammapada")
    q = quotes[datetime.now().timetuple().tm_yday % len(quotes)]
    return (q["text"], q["who"] + (" · " + q["source"] if q.get("source") else ""))


def daily_gems(n=3):
    try:
        gems = json.loads((HERE / "gems.json").read_text())
    except Exception:
        return []
    start = (datetime.now().timetuple().tm_yday * n) % len(gems)
    return [gems[(start + i) % len(gems)] for i in range(min(n, len(gems)))]


# ------------------------------------------------------------- rendering ---
def card_html(a, accent, tint):
    when = ""
    if a["published"]:
        try:
            when = datetime.fromisoformat(a["published"]).strftime("%b %-d")
        except Exception:
            when = ""
    meta = html.escape(a["source"]) + ((" · " + when) if when else "")
    top = (f'<div class="thumb" style="background-image:url(\'{html.escape(a["image"])}\')"></div>'
           if a["image"] else "")
    cls = "card" if a["image"] else "card noimg"
    return (f'    <a class="{cls}" href="{html.escape(a["link"])}" target="_blank" rel="noopener" '
            f'style="--a:{accent};--t:{tint}">\n      {top}\n'
            f'      <div class="body"><div class="src">{meta}</div>\n'
            f'      <h3>{html.escape(a["title"])}</h3>\n'
            f'      <p>{html.escape(a["summary"])}</p></div>\n    </a>')


def gem_card_html(g):
    tag = html.escape(g.get("tag", "Gem"))
    return (f'    <div class="card noimg gem" style="--a:{GEM_ACCENT};--t:{GEM_TINT}">\n'
            f'      <div class="body"><div class="src">{tag}</div>\n'
            f'      <h3>{html.escape(g["fact"])}</h3></div>\n    </div>')


def nav_bar(pages, active):
    out = ['<nav>']
    for slug, label, accent, tint, _ in pages:
        cls = ' class="active"' if slug == active else ""
        out.append(f'<a{cls} href="{slug}.html" style="--a:{accent};--t:{tint}">'
                   f'{html.escape(text_label(label))}</a>')
    out.append("</nav>")
    return "".join(out)


def section_block(slug, label, accent, tint, items, gems):
    if slug == "gems":
        head = ('Little Gems <span class="count">odd, delightful &amp; true</span>')
        cards = "\n".join(gem_card_html(g) for g in gems)
    else:
        n = len(items)
        head = (f'{html.escape(text_label(label))} '
                f'<span class="count">{n} {"story" if n == 1 else "stories"}</span>')
        cards = "\n".join(card_html(a, accent, tint) for a in items)
    return (f'  <section style="--a:{accent};--t:{tint}">\n'
            f'    <h2 class="sec">{head}</h2>\n'
            f'    <div class="grid">\n{cards}\n    </div>\n  </section>')


def page(title, hero, nav, body, countdown=False):
    cd = COUNTDOWN_JS if countdown else ""
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{title}</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap" rel="stylesheet">'
        '<script data-goatcounter="https://brightcup.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
        f'<style>{STYLE}</style></head><body>'
        f'{hero}{nav}<main>{body}</main>{FOOTER}{cd}'
        '</body></html>'
    )


def render(articles):
    now = datetime.now()
    built = now.strftime("%A, %B %-d, %Y")
    nxt = now.replace(minute=15, second=0, microsecond=0)
    if now.minute >= 15:
        nxt += timedelta(hours=1)
    next_ms = int(nxt.timestamp() * 1000)
    med_text, med_attr = daily_meditation()

    # group articles
    order = [s[0] for s in SECTIONS] + [CATCH_ALL[0]]
    labels = {s[0]: s[1] for s in SECTIONS}
    labels[CATCH_ALL[0]] = CATCH_ALL[1]
    grouped = {slug: [] for slug in order}
    for a in articles:
        grouped[classify(a)[0]].append(a)

    # ordered page list — news topics first, Little Gems LAST
    pages = []
    for slug in order:
        if grouped[slug]:
            acc, tnt = COLORS[slug]
            pages.append((slug, labels[slug], acc, tnt, grouped[slug]))
    gems = daily_gems()
    pages.append(("gems", "Little Gems", GEM_ACCENT, GEM_TINT, gems))

    # ---- landing page (index.html): hero + meditation + big bubbles ----
    hero = (
        '<header class="hero full">'
        '<h1 class="logo">The Bright <span class="cup">Cup</span></h1>'
        '<p class="tag">Good news. Daily.</p>'
        f'<span class="built">Fresh Brewed Daily: {built}</span>'
        f'<div class="refresh" data-next="{next_ms}"><span class="rdot"></span>'
        'Next fresh pour in <b id="cd">…</b></div>'
        '</header>')
    creed = (
        '<section class="creed"><p class="eyebrow">The Daily Meditation</p>'
        f'<p class="quote">&ldquo;{html.escape(med_text)}&rdquo;</p>'
        f'<p class="attr">{html.escape(med_attr)}</p>'
        '<p class="words">You can&rsquo;t control the world &mdash; but you can choose where you look. '
        'And what you look at becomes how you feel. So we pour the good stuff fresh every morning. '
        'Fill your cup with what lifts you up.</p></section>')
    bubbles = []
    for slug, label, acc, tnt, items in pages:
        if slug == "gems":
            sub = f"{len(items)} today"
        else:
            n = len(items)
            sub = f'{n} {"story" if n == 1 else "stories"}'
        bubbles.append(
            f'<a href="{slug}.html" style="--a:{acc};--t:{tnt}">'
            f'{svg_icon(slug, "bgicon")}'
            f'<span class="lbl">{html.escape(text_label(label))}</span>'
            f'<span class="c">{sub}</span></a>')
    menu = ('<div class="menuwrap"><p class="menuhead">Choose your pour</p>'
            '<div class="menu">' + "".join(bubbles) + '</div>'
            '<div class="cta"><a href="suggest.html">'
            'Have good news to share, or a suggestion? Leave us a note &rarr;</a></div></div>')
    (HERE / "index.html").write_text(
        page("The Bright Cup — good news, daily", hero, "", creed + menu, countdown=True))

    # ---- suggestions / leave-a-note page + thank-you ----
    note_hero = (
        '<header class="topbanner" style="--a:#0f766e">'
        f'{svg_icon("suggest", "bgicon")}'
        '<a class="logo" href="index.html">The Bright <span class="cup">Cup</span></a>'
        '<div class="ttl">Leave a Note</div>'
        '<a class="backhome" href="index.html">&larr; all topics</a></header>')
    note_body = (
        '<section class="formwrap">'
        '<p class="formsub">Got good news to share, an idea to make this better, '
        'or just want to say hello? We&rsquo;d love to hear from you.</p>'
        f'<form action="https://formsubmit.co/{CONTACT_EMAIL}" method="POST">'
        '<input type="hidden" name="_subject" value="A new note from The Bright Cup">'
        '<input type="hidden" name="_captcha" value="true">'
        '<input type="hidden" name="_template" value="box">'
        '<input type="hidden" name="_next" value="https://thebrightcup.com/thanks.html">'
        '<input class="fld" type="text" name="name" placeholder="Your name (optional)">'
        '<input class="fld" type="email" name="email" placeholder="Your email (optional, if you\'d like a reply)">'
        '<textarea class="fld" name="message" rows="6" placeholder="Your message, suggestion, or good news…" required></textarea>'
        '<button class="send" type="submit">Send it &#9749;</button>'
        '</form></section>')
    (HERE / "suggest.html").write_text(
        page("Leave a Note — The Bright Cup", note_hero, nav_bar(pages, None), note_body))

    thanks_body = (
        '<section class="formwrap thanks">'
        '<h2 class="formtitle">Thank you &#9749;</h2>'
        '<p class="formsub">Your note just landed in our cup. We read every one.</p>'
        '<a class="send" href="index.html">Back to the good news</a></section>')
    (HERE / "thanks.html").write_text(
        page("Thanks — The Bright Cup", note_hero, "", thanks_body))

    # ---- one page per topic (banner = the topic's icon, big, on its color) ----
    for slug, label, acc, tnt, items in pages:
        cat_hero = (
            f'<header class="topbanner" style="--a:{acc}">'
            f'{svg_icon(slug, "bgicon")}'
            '<a class="logo" href="index.html">The Bright <span class="cup">Cup</span></a>'
            f'<div class="ttl">{html.escape(text_label(label))}</div>'
            '<a class="backhome" href="index.html">&larr; all topics</a>'
            '</header>')
        body = section_block(slug, label, acc, tnt, items, gems)
        (HERE / f"{slug}.html").write_text(
            page(f"{html.escape(text_label(label))} — The Bright Cup",
                 cat_hero, nav_bar(pages, slug), body))

    print(f"built landing + {len(pages)} topic pages")


def main():
    print(f"The Bright Cup build @ {datetime.now():%Y-%m-%d %H:%M}")
    articles = []
    for feed in FEEDS:
        articles.extend(fetch(feed))
    seen, deduped = set(), []
    for a in sorted(articles, key=lambda x: x["ts"], reverse=True):
        key = a["link"].split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    deduped = deduped[:MAX_TOTAL]
    (HERE / "articles.json").write_text(json.dumps(deduped, indent=1))
    render(deduped)
    print(f"aggregated {len(deduped)} stories")


STYLE = """
:root{ --ink:#0f172a; --soft:#64748b; --line:#eef1f5; --bg:#fff; }
*{ box-sizing:border-box; }
body{ margin:0; background:var(--bg); color:var(--ink);
  font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased; }

.hero{ position:relative; display:flex; flex-direction:column; align-items:center;
  justify-content:center; text-align:center; color:#fff;
  background:url('img/hero.jpg') center 40%/cover no-repeat; }
.hero.full{ min-height:66vh; padding:80px 22px 64px; }
.hero.strip{ min-height:210px; padding:34px 22px; }
.hero::after{ content:""; position:absolute; inset:0;
  background:linear-gradient(180deg,rgba(8,20,38,.5),rgba(8,20,38,.25) 45%,rgba(8,20,38,.6)); }
.hero>*{ position:relative; z-index:1; }
.logo{ font-size:clamp(40px,7.5vw,82px); font-weight:900; letter-spacing:-.035em;
  line-height:.98; margin:0; text-shadow:0 2px 30px rgba(0,0,0,.35); text-decoration:none; color:#fff; }
.hero.strip .logo{ font-size:clamp(28px,5vw,44px); }
.logo .cup{ background:linear-gradient(90deg,#ffd76b,#ff9e3d);
  -webkit-background-clip:text; background-clip:text; color:transparent; }
.tag{ margin:18px 0 0; font-size:clamp(17px,2.4vw,22px); font-weight:500;
  text-shadow:0 1px 14px rgba(0,0,0,.4); }
.built{ margin-top:22px; font-size:13px; font-weight:600; letter-spacing:.08em;
  text-transform:uppercase; opacity:.92; border:1px solid rgba(255,255,255,.5);
  border-radius:30px; padding:7px 16px; display:inline-block; backdrop-filter:blur(3px); }
.refresh{ margin-top:14px; font-size:13.5px; font-weight:600; opacity:.95;
  display:inline-flex; align-items:center; gap:8px; }
.refresh b{ font-weight:800; }
.rdot{ width:8px; height:8px; border-radius:50%; background:#7CFC9B; animation:pulse 2s infinite; }
@keyframes pulse{ 0%{ box-shadow:0 0 0 0 rgba(124,252,155,.6) }
  70%{ box-shadow:0 0 0 9px rgba(124,252,155,0) } 100%{ box-shadow:0 0 0 0 rgba(124,252,155,0) } }
.backhome{ display:inline-block; margin-top:14px; font-size:14px; font-weight:600;
  color:#fff; text-decoration:none; opacity:.92; }

.creed{ max-width:780px; margin:0 auto; padding:62px 26px 30px; text-align:center; }
.creed .eyebrow{ font-size:12.5px; font-weight:800; letter-spacing:.22em;
  text-transform:uppercase; color:#d9822b; margin:0; }
.creed .eyebrow::after{ content:""; display:block; width:36px; height:3px; border-radius:3px;
  margin:16px auto 22px; background:linear-gradient(90deg,#ffd76b,#ff9e3d); }
.creed .quote{ font-family:Georgia,"Times New Roman",serif; font-style:italic;
  font-size:clamp(21px,3.1vw,29px); line-height:1.42; color:var(--ink); margin:0; }
.creed .attr{ margin:16px 0 28px; font-size:12.5px; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--soft); }
.creed .words{ font-size:clamp(15.5px,2vw,17.5px); line-height:1.72; color:#475569;
  max-width:640px; margin:0 auto; }

.menuwrap{ text-align:center; padding:8px 20px 16px; }
.menuhead{ font-size:13px; font-weight:800; letter-spacing:.2em; text-transform:uppercase;
  color:var(--soft); margin:0 0 24px; }
.menu{ display:flex; flex-wrap:wrap; justify-content:center; gap:16px;
  max-width:860px; margin:0 auto 76px; }
.menu a{ position:relative; overflow:hidden; width:212px; min-height:108px;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  padding:22px; border-radius:22px; background:var(--t); border:2px solid var(--a);
  color:var(--a); text-decoration:none; font-weight:800; font-size:18.5px; letter-spacing:-.01em;
  transition:transform .15s,box-shadow .15s,background .15s,color .15s; }
.menu a .bgicon{ position:absolute; left:50%; top:50%; width:92px; height:92px;
  transform:translate(-50%,-50%); opacity:.12; z-index:0; }
.menu a .lbl, .menu a .c{ position:relative; z-index:1; text-align:center; }
.menu a .c{ font-size:13px; font-weight:600; opacity:.85; margin-top:8px; }
.menu a:hover{ background:var(--a); color:#fff; transform:translateY(-4px);
  box-shadow:0 14px 30px color-mix(in srgb,var(--a) 34%,transparent); }
.menu a:hover .bgicon{ opacity:.2; }

.topbanner{ position:relative; overflow:hidden; text-align:center; color:#fff;
  padding:46px 22px 40px;
  background:linear-gradient(135deg,var(--a),color-mix(in srgb,var(--a) 62%,#0b1220)); }
.topbanner .bgicon{ position:absolute; right:-30px; top:50%; width:240px; height:240px;
  transform:translateY(-50%); opacity:.17; color:#fff; }
.topbanner .logo{ position:relative; font-size:clamp(26px,4.5vw,42px); }
.topbanner .cup{ -webkit-text-fill-color:#fff; background:none; color:#fff; }
.topbanner .ttl{ position:relative; margin:10px 0 0; font-size:clamp(20px,3vw,27px);
  font-weight:800; letter-spacing:-.01em; }
.topbanner .backhome{ position:relative; }

nav{ position:sticky; top:0; z-index:5; background:rgba(255,255,255,.9);
  backdrop-filter:saturate(1.6) blur(12px); border-bottom:1px solid var(--line);
  padding:13px 10px; white-space:nowrap; overflow-x:auto;
  -webkit-overflow-scrolling:touch; text-align:center; }
nav::-webkit-scrollbar{ display:none; }
nav a{ display:inline-flex; align-items:center; gap:8px; margin:0 5px; padding:9px 17px;
  border-radius:40px; font-size:14px; font-weight:700; text-decoration:none;
  color:var(--a); background:var(--t); border:1.6px solid var(--a); transition:all .18s; }
nav a::before{ content:""; width:8px; height:8px; border-radius:50%; background:var(--a); }
nav a:hover{ background:var(--a); color:#fff; transform:translateY(-1px); }
nav a:hover::before{ background:#fff; }
nav a.active{ background:var(--a); color:#fff; }
nav a.active::before{ background:#fff; }

main{ max-width:1140px; margin:0 auto; padding:8px 18px 70px; }
section{ padding-top:36px; }
h2.sec{ font-size:clamp(22px,3.4vw,30px); font-weight:900; letter-spacing:-.02em;
  margin:0 0 22px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
h2.sec::before{ content:""; width:14px; height:14px; border-radius:5px; background:var(--a); }
h2.sec .count{ font-size:13px; font-weight:700; color:var(--a); background:var(--t);
  border-radius:20px; padding:4px 12px; text-transform:none; letter-spacing:0; }
.grid{ display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr));
  gap:22px; align-items:start; }
.card{ display:flex; flex-direction:column; background:#fff; border:1px solid var(--line);
  border-radius:18px; overflow:hidden; text-decoration:none; color:inherit;
  transition:transform .14s,box-shadow .14s; }
.card:hover{ transform:translateY(-4px); box-shadow:0 14px 34px rgba(15,23,42,.12); }
.thumb{ height:172px; background-size:cover; background-position:center; }
.body{ padding:18px 19px 22px; }
.src{ font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.07em;
  color:var(--a); margin-bottom:9px; }
.card h3{ font-size:19px; font-weight:800; line-height:1.28; letter-spacing:-.01em; margin:0 0 9px; }
.card p{ margin:0; font-size:14.5px; line-height:1.5; color:var(--soft); }
.card.noimg{ background:var(--t); border-color:transparent; }
.card.gem h3{ font-family:Georgia,"Times New Roman",serif; font-size:19px; line-height:1.4; }
footer{ text-align:center; padding:40px 22px 60px; color:var(--soft);
  font-size:13.5px; line-height:1.7; border-top:1px solid var(--line); }
footer strong{ color:var(--ink); }
.flinks{ margin-top:10px; }
.flinks a{ color:var(--soft); text-decoration:none; font-weight:600; }
.flinks a:hover{ color:var(--ink); }

.cta{ margin:2px auto 78px; }
.cta a{ display:inline-block; font-size:15px; font-weight:700; color:#d9822b;
  text-decoration:none; border-bottom:2px solid #ffd76b; padding-bottom:2px; }
.cta a:hover{ color:#b45309; }
.formwrap{ max-width:620px; margin:0 auto; padding:34px 22px 50px; text-align:center; }
.formtitle{ font-size:28px; font-weight:900; letter-spacing:-.02em; margin:0 0 10px; }
.formsub{ font-size:16px; line-height:1.6; color:var(--soft); margin:0 auto 28px; max-width:520px; }
.formwrap form{ display:flex; flex-direction:column; gap:14px; text-align:left; }
.fld{ font:inherit; font-size:16px; padding:14px 16px; border:1.5px solid var(--line);
  border-radius:14px; background:#fff; color:var(--ink); width:100%;
  transition:border-color .15s,box-shadow .15s; }
.fld:focus{ outline:none; border-color:#f0a23d; box-shadow:0 0 0 4px rgba(240,162,61,.18); }
textarea.fld{ resize:vertical; }
.send{ align-self:center; margin-top:8px; font:inherit; font-size:16px; font-weight:800;
  color:#fff; background:linear-gradient(135deg,#f0a23d,#e07b1f); border:0; border-radius:40px;
  padding:14px 34px; cursor:pointer; text-decoration:none; display:inline-block;
  transition:transform .15s,box-shadow .15s; }
.send:hover{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(224,123,31,.35); }
.thanks{ padding-top:54px; }
.byline{ margin-top:18px; font-size:12px; font-weight:700; letter-spacing:.16em;
  text-transform:uppercase; color:#c0a86f; }
.byline::before{ content:""; display:block; width:26px; height:2px; border-radius:2px;
  margin:0 auto 14px; background:linear-gradient(90deg,#ffd76b,#ff9e3d); }
"""

FOOTER = ('<footer><strong>The Bright Cup</strong> &mdash; good news, gathered from '
          'Good News Network, Positive News, Reasons to be Cheerful, The Optimist Daily '
          '&amp; Squirrel News.<br>Every story links to its original publisher.'
          '<div class="flinks"><a href="index.html">Home</a> &nbsp;·&nbsp; '
          '<a href="suggest.html">Leave a note</a></div>'
          '<div class="byline">A JDog Production</div></footer>')

COUNTDOWN_JS = """<script>
(function(){
  var out=document.getElementById('cd'); if(!out) return;
  // compute the next brew (once a day, just after midnight at 00:15) live in
  // the browser, so the clock is always correct no matter when the page loaded
  function nextBrew(){
    var n=new Date(), t=new Date(n);
    t.setHours(0,15,0,0);
    if(n.getHours()>0 || (n.getHours()===0 && n.getMinutes()>=15)) t.setDate(t.getDate()+1);
    return t.getTime();
  }
  var target=nextBrew();
  function tick(){
    var s=Math.floor((target-Date.now())/1000);
    if(s<=0){ target=nextBrew(); setTimeout(function(){location.reload();},4000); out.textContent='brewing…'; return; }
    var h=Math.floor(s/3600), m=Math.floor((s%3600)/60), ss=s%60;
    out.textContent = h>0 ? (h+'h '+m+'m') : (m+'m '+String(ss).padStart(2,'0')+'s');
    setTimeout(tick,1000);
  }
  tick();
})();
</script>"""

if __name__ == "__main__":
    main()
