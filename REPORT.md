# Tripadvisor restaurant scraper

## Target data (only these 4 fields)

| Field | Source on page |
|-------|----------------|
| **name** | JSON-LD, `<h1>`, `og:title` |
| **email** | `mailto:` links, JSON-LD (rare on Tripadvisor) |
| **image_url** | JSON-LD `image`, `og:image`, hero photo |
| **phone** | `tel:` links, JSON-LD `telephone`, page text |

**Note:** Tripadvisor rarely shows restaurant email on public pages. You may often get name + image + phone only.

## Which pages to open

Only URLs containing **`Restaurant_Review`**, for example:

`https://www.tripadvisor.com/Restaurant_Review-g60763-d801207-Reviews-...`

Homepage / search pages are **skipped** automatically.

---

# How it works

## Your workflow

1. Run `python main.py`
2. Click **Open browser** — real **Chrome** opens (you control it with mouse/keyboard)
3. Browse Tripadvisor normally: search, hotels, reviews, photos
4. The **tracker panel** (separate window) records each page automatically
5. Click **Capture now** to force-save the current page
6. Click **Save session** to export everything to JSON

```
┌─────────────────────┐     you click/links     ┌──────────────────────┐
│  Chrome (visible)   │ ───────────────────────►  │  Tripadvisor pages   │
│  You browse here    │                         │  (JS runs fully)     │
└─────────┬───────────┘                         └──────────────────────┘
          │ page_source on each URL change
          ▼
┌─────────────────────┐
│  Scraping engine    │  parser.py → meta, JSON-LD, links, headings, …
│  (tracker.py)       │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  Custom UI          │  Pages visited · Fields A–Z · Full JSON · Save
│  (main.py)          │
└─────────────────────┘
```

## Why browser + tracker (not HTTP-only)

Tripadvisor blocks plain `httpx` requests (HTTP 403). A real browser:

- Runs JavaScript
- Passes normal user flows
- Lets **you** navigate; the engine only **reads** what is on screen

## What gets tracked (A–Z)

On each Tripadvisor URL the engine captures:

| Category | Examples |
|----------|----------|
| **meta:** | `og:title`, `description`, … |
| **JSON-LD** | `@type`, `aggregateRating`, `address`, … |
| **headings** | h1–h4 text |
| **links** | href + label (up to 80) |
| **images** | src, alt |
| **text_blocks** | visible paragraphs |
| **data-attr** | `data-*` attributes on elements |
| **field_inventory** | flat list of every field name found |

The bottom bar shows **all unique fields** seen across the whole session.

## Files

| File | Role |
|------|------|
| `main.py` | Tracker UI |
| `tracker.py` | Selenium Chrome + URL watcher |
| `parser.py` | HTML → `PageCapture` |
| `fetcher.py` | Optional HTTP (often 403) |

## Install

```powershell
pip install -r requirements.txt
python main.py
```

Need **Google Chrome** installed.

---

## Avoiding blocks (proxy + stealth)

Tripadvisor flags:

- **Automated test software** (plain Selenium)
- **Datacenter IPs** (VPS, cloud, many VPNs)
- **Fast bot-like clicks**

This app includes:

| Setting | What it does |
|---------|----------------|
| **Stealth mode** (default on) | Uses `undetected-chromedriver` — hides most automation signals |
| **Proxy** | Routes Chrome through your proxy (new IP) |

### Proxy field examples

Copy `config.example.json` → `config.json` and edit, or type in the UI:

```
http://host:port
http://username:password@host:port
socks5://host:port
```

**Use a residential proxy** (Bright Data, Oxylabs, Smartproxy, etc.). Free/datacenter proxies are often blocked in minutes, same as your home IP when flagged.

### If you still see “Access is temporarily restricted”

1. Stop browser, set a **different residential proxy**, click **Open browser** again  
2. Browse slowly (human pace)  
3. Wait 30–60 minutes if your IP is temporarily banned  
4. Do not use “automated test software” bar — keep **Stealth mode** checked  

### Save settings

Click **Save settings** — stores proxy in `config.json` (do not commit real credentials to git).

## Rules

- Only **tripadvisor.com** URLs are captured
- Leaving Tripadvisor shows a warning in the tracker panel

## Tips

- Open a **listing page** (hotel/restaurant), not only the homepage, for richer JSON-LD
- Wait for the page to finish loading before clicking away
- Use **Capture now** after expanding “More reviews” on the same URL
- Export with **Save session** when done

## Legal

Use for learning/personal research. Respect Tripadvisor Terms of Use and rate limits.
