#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created by omegai.me
COMBO LEECHER - Multi-Engine Edition
Engines: Bing, DuckDuckGo, Yahoo, Baidu, Sogou, Yandex, Brave, Ask, AOL, Startpage
APIs:    psbdmp.ws, scrapbin.com, pastebin archive
"""

import re
import os
import sys
import time
import random
import threading
import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── optional deps ─────────────────────────────────────────────
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
CFG = {
    "max_threads":        8,
    "timeout":            15,
    "delay_min":          0.3,
    "delay_max":          1.2,
    "output_file":        "combos_leeched.txt",
    "log_file":           "leecher_log.txt",
    "max_pages_per_engine": 3,
    "deduplicate":        True,
    "min_combo_length":   6,
    "save_interval":      25,
    "debug_paste":        False,   # True = show first 150 chars of each paste
    "queries_per_engine": 15,
}

# ── Paste domains to harvest from ────────────────────────────
PASTE_DOMAINS = [
    "pastebin.com", "hastebin.com", "ghostbin.com",
    "paste.ee", "controlc.com", "paste2.org",
    "ideone.com", "justpaste.it", "dpaste.com",
    "pastecode.io", "rentry.co", "paste.fo",
    "txt.fyi", "termbin.com", "0paste.com",
    "paste.rs", "bpa.st", "sprunge.us", "ix.io",
]

# ── Search dork templates ─────────────────────────────────────
DORK_TEMPLATES = [
    'site:{domain} "{keyword}"',
    'site:pastebin.com "{keyword}" email password',
    'site:pastebin.com "{keyword}" "@gmail.com"',
    'site:pastebin.com "{keyword}" "@hotmail.com"',
    'site:hastebin.com "{keyword}" combo',
    'site:controlc.com "{keyword}" email pass',
    '"@gmail.com:" "{keyword}"',
    '"@hotmail.com:" "{keyword}"',
    '"@yahoo.com:" "{keyword}"',
    '"{keyword}" combo email:pass 2024',
    '"{keyword}" combo email:pass 2025',
    '"{keyword}" leaked combo list',
    '"{keyword}" "@gmail.com" ":" paste',
    'pastebin "{keyword}" combo hits',
    '"{keyword}" "email" "password" pastebin',
    'filetype:txt "{keyword}" email password',
]

KEYWORDS = [
    "combo", "email:pass", "user:pass", "mail:pass",
    "account", "credentials", "leaked", "database",
    "checker", "hits", "valid", "cracked",
]

# ── User-Agent pool ───────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
]

# ═══════════════════════════════════════════════════════════════
#  COLOURS
# ═══════════════════════════════════════════════════════════════
if sys.platform == "win32":
    os.system("color")

R   = "\033[91m"
G   = "\033[92m"
Y   = "\033[93m"
B   = "\033[94m"
M   = "\033[95m"
C   = "\033[96m"
W   = "\033[97m"
DIM = "\033[2m"
RST = "\033[0m"

# ═══════════════════════════════════════════════════════════════
#  LOGGER
# ═══════════════════════════════════════════════════════════════
_log_lock = threading.Lock()

def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    col = {"INFO": C, "OK": G, "WARN": Y, "ERR": R, "COMBO": M, "ENGINE": B}.get(level, W)
    pfx = {"INFO": "[*]", "OK": "[+]", "WARN": "[!]", "ERR": "[-]",
           "COMBO": "[C]", "ENGINE": "[E]"}.get(level, "[?]")
    line = f"{DIM}{ts}{RST} {col}{pfx}{RST} {msg}"
    with _log_lock:
        print(line)
        try:
            with open(CFG["log_file"], "a", encoding="utf-8") as f:
                f.write(f"{ts} {pfx} {msg}\n")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
#  HTTP
# ═══════════════════════════════════════════════════════════════
def make_session():
    if not REQUESTS_OK:
        return None
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

def random_ua():
    return random.choice(USER_AGENTS)

def safe_get(session, url, timeout=None, extra_headers=None):
    timeout = timeout or CFG["timeout"]
    headers = {
        "User-Agent":      random_ua(),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,zh-CN;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Connection":      "keep-alive",
        "DNT":             "1",
    }
    if extra_headers:
        headers.update(extra_headers)
    try:
        if session and REQUESTS_OK:
            r = session.get(url, headers=headers, timeout=timeout,
                            allow_redirects=True, verify=False)
            return r.text, r.status_code
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore"), resp.status
    except Exception:
        return "", 0

# ═══════════════════════════════════════════════════════════════
#  COMBO VALIDATOR  – strict email:pass only, no CSS garbage
# ═══════════════════════════════════════════════════════════════

# CSS property names - if the "password" is one of these, reject
_CSS_PROPS = {
    "display","height","width","max-width","min-width","max-height","min-height",
    "background","background-color","background-image","background-position",
    "background-repeat","background-size","border","border-radius","border-bottom",
    "border-top","border-left","border-right","box-shadow","box-sizing","color",
    "content","cursor","direction","fill","flex","flex-direction","flex-shrink",
    "flex-wrap","font","font-family","font-size","font-stretch","font-weight",
    "gap","grid-column","grid-column-gap","grid-column-start","grid-row-start",
    "grid-template-columns","grid-template-rows","justify-content","justify-self",
    "left","margin","margin-bottom","margin-left","margin-right","margin-top",
    "object-fit","object-position","opacity","outline","outline-color","outline-offset",
    "overflow","padding","padding-bottom","padding-left","padding-right","padding-top",
    "pointer-events","position","right","text-align","text-shadow","top","transition",
    "vertical-align","visibility","white-space","z-index","align-items","align-self",
    "column-gap","filter","grid-row","overflow-anchor","text-decoration","transform",
    "word-break","word-wrap","animation","appearance","aspect-ratio","clip-path",
    "float","inset","isolation","letter-spacing","line-height","list-style",
    "mix-blend-mode","order","overflow-x","overflow-y","resize","rotate","scale",
    "stroke","stroke-width","translate","unicode-bidi","user-select","will-change",
    # JS / HTML tokens (only clear non-password HTML/JS keywords)
    "href","src","xmlns","mailto",
}

# CSS value patterns - if password matches these, reject
_CSS_VALUE_RE = re.compile(
    r'^(?:'
    r'\d+(?:px|em|rem|vh|vw|%|pt|pc|cm|mm|in|ex|ch|fr|deg|rad|turn)(?:\s|$)'
    r'|#[0-9a-fA-F]{3,8}$'
    r'|rgba?[(]|hsla?[(]|var[(]--|linear-gradient[(]|radial-gradient[(]'
    r'|calc[(]|url[(]|format[(]|local[(]|env[(]|min[(]|max[(]|clamp[(]'
    r'|!important$'
    r')',
    re.IGNORECASE
)

# Strict email regex
_EMAIL_RE  = re.compile(r'^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,10}$')
_FAKE_TLDS = re.compile(r'\.(px|em|rem|vw|vh|pt|cm|gif|jpg|png|svg|js|css|woff|ttf)$', re.I)

# Only capture email:pass (email MUST have @domain.tld)
_COMBO_RE = re.compile(
    r'(?<![\\w.])'
    r'([a-zA-Z0-9][a-zA-Z0-9_.+\-]{1,62}'
    r'@[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}\.[a-zA-Z]{2,10})'
    r':'
    r'([^\s:,;|<>"`\x00-\x1f]{4,72})',
    re.UNICODE
)

def extract_combos(text):
    found = set()
    for m in _COMBO_RE.finditer(text):
        email = m.group(1).strip()
        pw    = m.group(2).strip()
        if _valid_combo(email, pw):
            found.add(f"{email}:{pw}")
    return found

def _valid_combo(email, pw):
    if len(email) < 6 or len(pw) < 4:
        return False
    if not _EMAIL_RE.match(email):
        return False
    if _FAKE_TLDS.search(email):
        return False
    if _CSS_VALUE_RE.match(pw):
        return False
    pw_key = pw.lower().split("(")[0].strip("-").strip()
    if pw_key in _CSS_PROPS:
        return False
    if pw.startswith("--") or pw.startswith("var("):
        return False
    if not re.search(r'[a-zA-Z0-9]', pw):
        return False
    if re.fullmatch(r'\d+[a-zA-Z%]+', pw):
        return False
    bad = ("http", "www", "ftp", "//", "\\", "{", "}", "<", ">", "#")
    if any(pw.lower().startswith(b) for b in bad):
        return False
    domain = email.split("@", 1)[1]
    if "." not in domain or len(domain.split(".")[-1]) < 2:
        return False
    return True

# ═══════════════════════════════════════════════════════════════
#  RAW-TEXT FETCHER
# ═══════════════════════════════════════════════════════════════
_RAW_MAP = {
    "pastebin.com": lambda u: re.sub(r'pastebin\.com/(?!raw/)', 'pastebin.com/raw/', u),
    "hastebin.com": lambda u: re.sub(r'hastebin\.com/(?!raw/)', 'hastebin.com/raw/', u),
    "paste.ee":     lambda u: u.replace("paste.ee/p/", "paste.ee/r/"),
    "dpaste.com":   lambda u: u.rstrip("/") + ".txt",
}

def to_raw_url(url):
    for domain, fn in _RAW_MAP.items():
        if domain in url:
            return fn(url)
    return url

def fetch_paste(session, url):
    raw = to_raw_url(url)
    text, code = safe_get(session, raw)
    if code == 200 and text:
        return text
    text, code = safe_get(session, url)
    return text if code == 200 else ""

# ═══════════════════════════════════════════════════════════════
#  LINK EXTRACTION FROM SEARCH RESULTS
# ═══════════════════════════════════════════════════════════════
def _is_valid_paste_url(url):
    """True only if the URL's actual host is a paste site (not a search engine
    redirect that merely contains a paste domain name inside a query param)."""
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False
        host = p.netloc.lower()
        if host.startswith('www.'):
            host = host[4:]
        for d in PASTE_DOMAINS:
            if host == d or host.endswith('.' + d):
                return True
    except Exception:
        pass
    return False

def parse_links(html):
    if BS4_OK:
        soup  = BeautifulSoup(html, "html.parser")
        raw   = [a["href"] for a in soup.find_all("a", href=True)
                 if a["href"].startswith("http")]
    else:
        raw = re.findall(r'href=["\']?(https?://[^\s"\'<>]+)', html)

    good = []
    seen = set()

    def _add(u):
        u = u.strip('.,;)')
        if u not in seen and _is_valid_paste_url(u):
            good.append(u)
            seen.add(u)

    for link in raw:
        # 1. Direct paste URL
        _add(link)

        # 2. Paste URL hidden inside a redirect parameter
        # (Yahoo: RU=, Bing: u=, generic: url= / redirect= / dest=)
        try:
            for match in re.finditer(
                    r'(?:^|[?&])(?:RU|url|u|redirect|dest)=([A-Za-z0-9%._~:@!$&\'()*+,;=\-/]{10,})',
                    link, re.IGNORECASE):
                decoded = urllib.parse.unquote(match.group(1))
                if decoded.startswith('http'):
                    _add(decoded)
        except Exception:
            pass

    return good

# ═══════════════════════════════════════════════════════════════
#  SEARCH ENGINES
# ═══════════════════════════════════════════════════════════════
def search_bing(session, query, page=0):
    url = (f"https://www.bing.com/search?"
           f"q={urllib.parse.quote(query)}&first={page*10}&count=10")
    html, _ = safe_get(session, url, extra_headers={"Accept-Language": "en-US,en;q=0.9"})
    return parse_links(html)

def search_ddg(session, query, page=0):
    params = {"q": query, "kl": "us-en", "s": str(page*30), "dc": str(page*30+1)}
    url    = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(params)
    html, _ = safe_get(session, url)
    raw  = re.findall(r'uddg=(https?[^&"\']+)', html)
    good = []
    for l in raw:
        try:
            l = urllib.parse.unquote(l)
        except Exception:
            pass
        for d in PASTE_DOMAINS:
            if d in l:
                good.append(l)
                break
    return good

def search_yahoo(session, query, page=0):
    url = (f"https://search.yahoo.com/search?"
           f"p={urllib.parse.quote(query)}&b={page*10+1}&pz=10")
    html, _ = safe_get(session, url)
    return parse_links(html)

def search_baidu(session, query, page=0):
    url = (f"https://www.baidu.com/s?"
           f"wd={urllib.parse.quote(query)}&pn={page*10}&rn=10")
    html, _ = safe_get(session, url, extra_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    return parse_links(html)

def search_sogou(session, query, page=1):
    url = (f"https://www.sogou.com/web?"
           f"query={urllib.parse.quote(query)}&page={page}")
    html, _ = safe_get(session, url, extra_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    return parse_links(html)

def search_yandex(session, query, page=0):
    url = (f"https://yandex.com/search/?"
           f"text={urllib.parse.quote(query)}&p={page}")
    html, _ = safe_get(session, url)
    return parse_links(html)

def search_brave(session, query, page=0):
    url = (f"https://search.brave.com/search?"
           f"q={urllib.parse.quote(query)}&offset={page*10}")
    html, _ = safe_get(session, url)
    return parse_links(html)

def search_ask(session, query, page=1):
    url = (f"https://www.ask.com/web?"
           f"q={urllib.parse.quote(query)}&qo=pagination&page={page}")
    html, _ = safe_get(session, url)
    return parse_links(html)

def search_aol(session, query, page=1):
    url = (f"https://search.aol.com/aol/search?"
           f"q={urllib.parse.quote(query)}&page={page}")
    html, _ = safe_get(session, url)
    return parse_links(html)

def search_startpage(session, query, page=0):
    url = (f"https://www.startpage.com/search?"
           f"query={urllib.parse.quote(query)}&page={page+1}")
    html, _ = safe_get(session, url)
    return parse_links(html)

ENGINES = {
    "bing":       search_bing,
    "duckduckgo": search_ddg,
    "yahoo":      search_yahoo,
    "baidu":      search_baidu,
    "sogou":      search_sogou,
    "yandex":     search_yandex,
    "brave":      search_brave,
    "ask":        search_ask,
    "aol":        search_aol,
    "startpage":  search_startpage,
}

# ═══════════════════════════════════════════════════════════════
#  PASTE AGGREGATOR APIs  (most reliable source)
# ═══════════════════════════════════════════════════════════════
def fetch_psbdmp(session, keyword, page=0):
    """psbdmp.ws - public API indexing pastebin dumps."""
    urls = []
    try:
        api = f"https://psbdmp.ws/api/search/v3/{urllib.parse.quote(keyword)}"
        if page > 0:
            api += f"?page={page}"
        text, code = safe_get(session, api, extra_headers={"Accept": "application/json"})
        if not text or code != 200:
            return []
        try:
            data  = json.loads(text)
            items = data.get("data", data) if isinstance(data, dict) else data
            for item in (items if isinstance(items, list) else []):
                pid = item.get("id") or item.get("paste_id") or ""
                if pid:
                    urls.append(f"https://pastebin.com/raw/{pid}")
        except Exception:
            for pid in re.findall(r'pastebin\.com/([A-Za-z0-9]{6,10})', text):
                urls.append(f"https://pastebin.com/raw/{pid}")
    except Exception as e:
        log(f"psbdmp error: {e}", "WARN")
    return urls

def fetch_scrapbin(session, keyword):
    """scrapbin.com - paste aggregator search."""
    urls = []
    try:
        text, _ = safe_get(session, f"https://scrapbin.com/search/?q={urllib.parse.quote(keyword)}")
        for pid in set(re.findall(r'pastebin\.com/(?:raw/)?([A-Za-z0-9]{6,10})', text or "")):
            urls.append(f"https://pastebin.com/raw/{pid}")
        urls += parse_links(text or "")
    except Exception as e:
        log(f"scrapbin error: {e}", "WARN")
    return urls

# Pastebin navigation slugs that are NOT paste IDs
_PASTEBIN_NAV = {
    "signup", "login", "logout", "archive", "languages", "trends",
    "contact", "faq", "tools", "api", "doc", "pro", "blog", "news",
    "privacy", "cookies", "tos", "about", "u", "search", "sitemap",
    "index", "home", "register", "reset",
}

def fetch_pastebin_archive(session):
    """Scrape Pastebin public archive (~50 recent pastes)."""
    urls = []
    try:
        text, code = safe_get(session, "https://pastebin.com/archive")
        if text and code == 200:
            for pid in set(re.findall(r'href="/([A-Za-z0-9]{6,10})"', text)):
                # Must be 6-8 chars and not a nav page
                if len(pid) >= 6 and pid.lower() not in _PASTEBIN_NAV:
                    urls.append(f"https://pastebin.com/raw/{pid}")
            log(f"  pastebin archive raw IDs found: {len(urls)}", "INFO")
    except Exception as e:
        log(f"pastebin archive error: {e}", "WARN")
    return urls

def fetch_via_api_all(session, keywords):
    """Collect paste URLs from all API sources."""
    all_urls = set()
    kws = keywords[:8]

    log("Stage 0: Querying paste aggregator APIs...", "INFO")

    # psbdmp
    pre = len(all_urls)
    for kw in kws:
        for pg in range(3):
            urls = fetch_psbdmp(session, kw, pg)
            for u in urls:
                all_urls.add(u)
            if not urls:
                break
            time.sleep(0.4)
    log(f"  psbdmp: {len(all_urls)-pre} URLs", "OK")

    # scrapbin
    pre = len(all_urls)
    for kw in kws:
        for u in fetch_scrapbin(session, kw):
            all_urls.add(u)
        time.sleep(0.3)
    log(f"  scrapbin: {len(all_urls)-pre} URLs", "OK")

    # pastebin archive
    pre = len(all_urls)
    for u in fetch_pastebin_archive(session):
        all_urls.add(u)
    log(f"  pastebin archive: {len(all_urls)-pre} URLs", "OK")

    log(f"Stage 0 done. API total: {len(all_urls)} URLs", "OK")
    return list(all_urls)

# ═══════════════════════════════════════════════════════════════
#  CORE LEECHER
# ═══════════════════════════════════════════════════════════════
class ComboLeecher:
    def __init__(self, keywords=None, engines=None, pages=None):
        self.keywords = keywords or KEYWORDS
        self.engines  = engines  or list(ENGINES.keys())
        self.pages    = pages    or CFG["max_pages_per_engine"]
        self.session  = make_session()
        self._seen_combos = set()
        self._seen_urls   = set()
        self._new_combos  = []
        self._lock        = threading.Lock()
        self._stats       = {
            "urls_searched": 0,
            "pastes_fetched": 0,
            "combos_found": 0,
            "engines_used": set(),
        }
        try:
            import urllib3
            urllib3.disable_warnings()
        except Exception:
            pass
        self._load_existing()

    def _load_existing(self):
        if os.path.exists(CFG["output_file"]):
            try:
                with open(CFG["output_file"], "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._seen_combos.add(line.lower())
                log(f"Loaded {len(self._seen_combos)} existing combos for dedup", "INFO")
            except Exception:
                pass

    def _save_combos(self, combos):
        if not combos:
            return
        with open(CFG["output_file"], "a", encoding="utf-8") as f:
            for c in combos:
                f.write(c + "\n")

    def _add_combo(self, combo):
        key = combo.lower()
        with self._lock:
            if key in self._seen_combos:
                return False
            self._seen_combos.add(key)
            self._new_combos.append(combo)
            self._stats["combos_found"] += 1
            if len(self._new_combos) >= CFG["save_interval"]:
                self._flush()
            return True

    def _flush(self):
        if self._new_combos:
            self._save_combos(self._new_combos)
            self._new_combos.clear()

    def _process_url(self, url):
        with self._lock:
            if url in self._seen_urls:
                return 0
            self._seen_urls.add(url)

        time.sleep(random.uniform(CFG["delay_min"], CFG["delay_max"]))
        text = fetch_paste(self.session, url)
        if not text:
            log(f"Empty/failed: {url[-40:]}", "WARN")
            return 0

        with self._lock:
            self._stats["pastes_fetched"] += 1

        if CFG.get("debug_paste"):
            preview = text[:150].replace("\n", " ").replace("\r", "")
            log(f"PREVIEW [{url[-25:]}]: {preview}", "INFO")

        combos = extract_combos(text)
        added  = 0
        for c in combos:
            if self._add_combo(c):
                log(f"{G}{c}{RST}", "COMBO")
                added += 1

        if added == 0 and len(text) > 50:
            sample = re.search(r'[\w.]+@[\w.]+', text)
            if sample:
                log(f"No valid combo in {url[-30:]} "
                    f"(email-like found: {sample.group()[:30]})", "WARN")
        return added

    def _search_engine(self, engine_name, query, page):
        fn = ENGINES.get(engine_name)
        if not fn:
            return []
        time.sleep(random.uniform(CFG["delay_min"], CFG["delay_max"]))
        try:
            urls = fn(self.session, query, page)
            with self._lock:
                self._stats["urls_searched"] += len(urls)
                self._stats["engines_used"].add(engine_name)
            return urls
        except Exception as e:
            log(f"Engine {engine_name} error: {e}", "WARN")
            return []

    def _build_queries(self, extra_keywords=None):
        kws     = self.keywords + (extra_keywords or [])
        queries = set()
        for kw in kws:
            for tmpl in DORK_TEMPLATES:
                for domain in random.sample(PASTE_DOMAINS, min(3, len(PASTE_DOMAINS))):
                    try:
                        queries.add(tmpl.format(keyword=kw, domain=domain))
                    except KeyError:
                        pass
                try:
                    queries.add(tmpl.format(keyword=kw, domain="pastebin.com"))
                except KeyError:
                    pass
        return list(queries)

    def run(self, extra_keywords=None):
        self._print_banner()
        all_kws = self.keywords + (extra_keywords or [])
        queries = self._build_queries(extra_keywords)
        log(f"Built {len(queries)} queries | {len(self.engines)} engines", "INFO")

        paste_urls = set()

        # Stage 0: API Aggregators (fastest & most reliable)
        for u in fetch_via_api_all(self.session, all_kws):
            paste_urls.add(u)

        # Stage 1: Search Engines
        log("Stage 1: Searching engines...", "INFO")
        qpe = CFG.get("queries_per_engine", 15)
        tasks = []
        for engine in self.engines:
            q_sample = random.sample(queries, min(qpe, len(queries)))
            for q in q_sample:
                for pg in range(self.pages):
                    tasks.append((engine, q, pg))
        random.shuffle(tasks)
        log(f"Total search tasks: {len(tasks)}", "INFO")

        with ThreadPoolExecutor(max_workers=CFG["max_threads"]) as ex:
            futs = {ex.submit(self._search_engine, e, q, p): (e, q, p)
                    for e, q, p in tasks}
            done = 0
            for fut in as_completed(futs):
                try:
                    for u in fut.result():
                        paste_urls.add(u)
                except Exception as err:
                    log(f"Search error: {err}", "ERR")
                done += 1
                if done % 10 == 0:
                    log(f"Search {done}/{len(tasks)} | URLs: {len(paste_urls)}", "ENGINE")

        log(f"Stage 1 done. Total paste URLs: {len(paste_urls)}", "OK")

        # Stage 2: Fetch & Extract
        log(f"Stage 2: Fetching {len(paste_urls)} pastes...", "INFO")
        url_list = list(paste_urls)

        with ThreadPoolExecutor(max_workers=CFG["max_threads"]) as ex:
            futs = {ex.submit(self._process_url, u): u for u in url_list}
            done = 0
            for fut in as_completed(futs):
                try:
                    n = fut.result()
                    if n > 0:
                        log(f"Got {n} combos from {list(futs.keys()).index(fut) if False else '...'}", "OK")
                except Exception as err:
                    log(f"Fetch error: {err}", "ERR")
                done += 1
                if done % 20 == 0:
                    log(f"Fetch {done}/{len(url_list)} | "
                        f"Combos: {self._stats['combos_found']}", "INFO")

        with self._lock:
            self._flush()
        self._print_summary()

    def _print_banner(self):
        eng = ", ".join(self.engines[:5])
        pad = " " * max(0, 35 - len(eng))
        lines = [
            "",
            f"{B}+----------------------------------------------------------+",
            f"|{M}     COMBO LEECHER  -  Multi-Engine Edition               {B}|",
            f"|{C}  Engines : {eng}...{pad}{B}|",
            f"|{C}  Keywords: {len(self.keywords):<4} Pages/Engine: {self.pages:<3} Threads: {CFG['max_threads']:<3}{B}|",
            f"|{Y}                  Created by omegai.me                   {B}|",
            f"+----------------------------------------------------------+{RST}",
            "",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()

    def _print_summary(self):
        s   = self._stats
        eng = ", ".join(sorted(s["engines_used"])) or "none"
        lines = [
            "",
            f"{G}+----------------------------------------------------------+",
            f"|                    FINAL SUMMARY                        |",
            f"|  URLs searched  : {s['urls_searched']:<38}|",
            f"|  Pastes fetched : {s['pastes_fetched']:<38}|",
            f"|  Combos found   : {s['combos_found']:<38}|",
            f"|  Output file    : {CFG['output_file']:<38}|",
            f"+----------------------------------------------------------+{RST}",
            "",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        log(f"Combos saved to {CFG['output_file']}", "OK")

# ═══════════════════════════════════════════════════════════════
#  DIRECT LEECHER  (URLs from file or single URL)
# ═══════════════════════════════════════════════════════════════
class DirectLeecher:
    def __init__(self):
        self.session = make_session()
        self._seen   = set()
        try:
            import urllib3; urllib3.disable_warnings()
        except Exception:
            pass

    def leech_urls(self, url_list, output="direct_combos.txt"):
        log(f"Direct leeching {len(url_list)} URLs...", "INFO")
        all_combos = []
        with ThreadPoolExecutor(max_workers=CFG["max_threads"]) as ex:
            futs = {ex.submit(self._fetch_extract, u): u for u in url_list}
            for fut in as_completed(futs):
                for c in fut.result():
                    if c.lower() not in self._seen:
                        self._seen.add(c.lower())
                        all_combos.append(c)
                        log(c, "COMBO")
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(all_combos))
        log(f"Saved {len(all_combos)} combos to {output}", "OK")
        return all_combos

    def _fetch_extract(self, url):
        text = fetch_paste(self.session, url)
        return extract_combos(text) if text else set()

    def leech_file(self, filepath, output="direct_combos.txt"):
        if not os.path.exists(filepath):
            log(f"File not found: {filepath}", "ERR")
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            urls = [l.strip() for l in f if l.strip().startswith("http")]
        log(f"Loaded {len(urls)} URLs from {filepath}", "INFO")
        return self.leech_urls(urls, output)

# ═══════════════════════════════════════════════════════════════
#  INTERACTIVE MENU
# ═══════════════════════════════════════════════════════════════
def interactive_menu():
    print(f"""
{M}{'='*56}
  COMBO LEECHER  -  Choose Mode
{'='*56}{RST}
  {G}[1]{RST} Full Auto-Leech  (APIs + search engines + harvest)
  {G}[2]{RST} Direct URL Leech (provide URL list file)
  {G}[3]{RST} Single URL Leech
  {G}[4]{RST} Custom Keywords + Engine Selection
  {G}[5]{RST} Exit
{M}{'='*56}{RST}
""")
    return input(f"  {C}Select [{W}1-5{C}]{RST}: ").strip()


def run_interactive():
    while True:
        choice = interactive_menu()

        if choice == "1":
            pages   = input(f"  {C}Pages per engine [{W}default=3{C}]{RST}: ").strip()
            pages   = int(pages) if pages.isdigit() else 3
            threads = input(f"  {C}Threads [{W}default=8{C}]{RST}: ").strip()
            threads = int(threads) if threads.isdigit() else 8
            CFG["max_pages_per_engine"] = pages
            CFG["max_threads"] = threads
            eng_in  = input(
                f"  {C}Engines (comma-sep, or ENTER for all):\n"
                f"  {DIM}{', '.join(ENGINES.keys())}{RST}\n  > "
            ).strip()
            chosen  = ([e.strip().lower() for e in eng_in.split(",")
                        if e.strip().lower() in ENGINES]
                       if eng_in else list(ENGINES.keys()))
            ComboLeecher(engines=chosen, pages=pages).run()

        elif choice == "2":
            fp  = input(f"  {C}Path to URL file{RST}: ").strip()
            out = input(f"  {C}Output file [{W}direct_combos.txt{C}]{RST}: ").strip() or "direct_combos.txt"
            DirectLeecher().leech_file(fp, out)

        elif choice == "3":
            url = input(f"  {C}Paste URL{RST}: ").strip()
            if not url.startswith("http"):
                log("Invalid URL", "ERR")
                continue
            combos = DirectLeecher().leech_urls([url], "single_combo.txt")
            log(f"Extracted {len(combos)} combos", "OK")

        elif choice == "4":
            kw_raw  = input(f"  {C}Keywords (comma-sep){RST}: ").strip()
            kws     = [k.strip() for k in kw_raw.split(",") if k.strip()] or KEYWORDS
            eng_in  = input(f"  {C}Engines (comma-sep, or ENTER for all){RST}: ").strip()
            chosen  = ([e.strip().lower() for e in eng_in.split(",")
                        if e.strip().lower() in ENGINES]
                       if eng_in else list(ENGINES.keys()))
            pages   = input(f"  {C}Pages [{W}default=3{C}]{RST}: ").strip()
            pages   = int(pages) if pages.isdigit() else 3
            ComboLeecher(keywords=kws, engines=chosen, pages=pages).run()

        elif choice == "5":
            log("Bye!", "INFO")
            break
        else:
            log("Invalid choice", "WARN")

# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════
def parse_args():
    import argparse
    p = argparse.ArgumentParser(
        description="Combo Leecher - Multi-Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dddd.py                              # interactive menu
  python dddd.py --auto                       # full auto
  python dddd.py --auto --engines bing,baidu --pages 5
  python dddd.py --url https://pastebin.com/xxxxx
  python dddd.py --file urls.txt
  python dddd.py --keywords netflix,spotify
  python dddd.py --auto --debug              # show paste previews
        """
    )
    p.add_argument("--auto",     action="store_true")
    p.add_argument("--url",      type=str)
    p.add_argument("--file",     type=str)
    p.add_argument("--keywords", type=str)
    p.add_argument("--engines",  type=str)
    p.add_argument("--pages",    type=int, default=3)
    p.add_argument("--threads",  type=int, default=8)
    p.add_argument("--output",   type=str)
    p.add_argument("--debug",    action="store_true", help="Show paste content previews")
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════
def main():
    # Always-shown startup banner
    banner = [
        "",
        f"{B}+----------------------------------------------------------+",
        f"|{M}     COMBO LEECHER  -  Multi-Engine Edition               {B}|",
        f"|{C}  Bing | DDG | Yahoo | Baidu | Sogou | Yandex | Brave    {B}|",
        f"|{Y}               Created by omegai.me                      {B}|",
        f"+----------------------------------------------------------+{RST}",
        "",
    ]
    sys.stdout.write("\n".join(banner) + "\n")
    sys.stdout.flush()

    args = parse_args()

    if args.output:  CFG["output_file"]          = args.output
    if args.threads: CFG["max_threads"]           = args.threads
    if args.pages:   CFG["max_pages_per_engine"]  = args.pages
    if args.debug:   CFG["debug_paste"]           = True

    chosen  = ([e.strip().lower() for e in args.engines.split(",")
                if e.strip().lower() in ENGINES]
               if args.engines else list(ENGINES.keys()))
    keywords = ([k.strip() for k in args.keywords.split(",") if k.strip()]
                if args.keywords else KEYWORDS)

    if args.url:
        combos = DirectLeecher().leech_urls([args.url], CFG["output_file"])
        log(f"Done. {len(combos)} combos -> {CFG['output_file']}", "OK")
        return

    if args.file:
        DirectLeecher().leech_file(args.file, CFG["output_file"])
        return

    if args.auto:
        ComboLeecher(keywords=keywords, engines=chosen, pages=args.pages).run()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
