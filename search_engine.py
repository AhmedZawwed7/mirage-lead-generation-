import os, re, json, time, socket, ipaddress
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

UA = "LeadsGenerationBot/1.0 (+business-contact-discovery; respect robots.txt)"
TIMEOUT = 12
MAX_PAGE_BYTES = 2097152
PHONE_RE = re.compile(r"(?<!\w)(?:\+\s?\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s().-]*)?\d[\d\s().-]{5,}\d(?!\w)")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")

def _public_host(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        return False
    try:
        addresses = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
        return bool(addresses) and all(not ipaddress.ip_address(x[4][0]).is_private and
            not ipaddress.ip_address(x[4][0]).is_loopback and
            not ipaddress.ip_address(x[4][0]).is_link_local and
            not ipaddress.ip_address(x[4][0]).is_reserved for x in addresses)
    except Exception:
        return False

def safe_fetch(url):
    current = url
    for _ in range(4):
        if not _public_host(current):
            return None
        try:
            r = requests.get(current, headers={"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"},
                             timeout=TIMEOUT, allow_redirects=False, stream=True)
            if r.is_redirect or r.is_permanent_redirect:
                target = urljoin(current, r.headers.get("Location", ""))
                current = target
                continue
            if r.status_code >= 400:
                return None
            declared = r.headers.get("Content-Length")
            if declared and int(declared) > MAX_PAGE_BYTES:
                return None
            chunks, total = [], 0
            for chunk in r.iter_content(65536):
                total += len(chunk)
                if total > MAX_PAGE_BYTES:
                    return None
                chunks.append(chunk)
            r._content = b"".join(chunks)
            return r
        except requests.RequestException:
            return None
    return None

def search_web(query, country):
    provider = os.getenv("SEARCH_PROVIDER", "serpapi").lower()
    if provider == "google_cse":
        key, cx = os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_CSE_ID")
        if not key or not cx:
            raise RuntimeError("أضف GOOGLE_API_KEY وGOOGLE_CSE_ID في إعدادات البيئة أولاً.")
        params = {"key": key, "cx": cx, "q": query, "num": 10, "hl": "ar",
                  "gl": "sa" if country == "السعودية" else "ae"}
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=TIMEOUT)
        data = response.json()
        if response.status_code >= 400:
            raise RuntimeError(data.get("error", {}).get("message", "فشل Google Custom Search"))
        return [{"title": x.get("title", ""), "link": x.get("link", ""), "snippet": x.get("snippet", "")}
                for x in data.get("items", [])]
    key = os.getenv("SERPAPI_KEY")
    if not key:
        raise RuntimeError("أضف SERPAPI_KEY في إعدادات البيئة لتفعيل البحث الآلي.")
    params = {"engine": "google", "q": query, "api_key": key, "hl": "ar",
              "gl": "sa" if country == "السعودية" else "ae", "google_domain": "google.com", "num": 20}
    response = requests.get("https://serpapi.com/search.json", params=params, timeout=TIMEOUT)
    data = response.json()
    if response.status_code >= 400 or data.get("error"):
        raise RuntimeError(data.get("error", "تعذر الاتصال بمزود البحث"))
    return [{"title": x.get("title", ""), "link": x.get("link", ""), "snippet": x.get("snippet", "")}
            for x in data.get("organic_results", [])]

def _robots_allows(url):
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    response = safe_fetch(robots_url)
    if response is None:
        return False
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(UA, url)

def _normalize_phone(raw, country):
    value = re.sub(r"[^\d+]", "", raw)
    if value.startswith("00"):
        value = "+" + value[2:]
    digits = re.sub(r"\D", "", value)
    if country == "السعودية":
        if digits.startswith("05") and len(digits) == 10: return "+966" + digits[1:]
        if digits.startswith("5") and len(digits) == 9: return "+966" + digits
        if digits.startswith("966") and 11 <= len(digits) <= 12: return "+" + digits
    if country == "الإمارات":
        if digits.startswith("05") and len(digits) == 10: return "+971" + digits[1:]
        if digits.startswith("5") and len(digits) == 9: return "+971" + digits
        if digits.startswith("971") and 11 <= len(digits) <= 12: return "+" + digits
    if value.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if 8 <= len(digits) <= 15:
        return "+" + digits
    return ""

def _extract_contact(html, base_url, country):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    phones, emails = set(), set()
    for a in soup.select('a[href^="tel:"]'):
        n = _normalize_phone(a.get("href", "")[4:], country)
        if n: phones.add(n)
    for a in soup.select('a[href^="mailto:"]'):
        e = a.get("href", "")[7:].split("?")[0].strip().lower()
        if EMAIL_RE.fullmatch(e): emails.add(e)
    text = soup.get_text(" ", strip=True)
    for raw in PHONE_RE.findall(text):
        n = _normalize_phone(raw, country)
        if n: phones.add(n)
    for e in EMAIL_RE.findall(text):
        emails.add(e.lower())
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    og = soup.find("meta", attrs={"property": "og:site_name"})
    company = (og.get("content", "").strip() if og else "") or title.split("|")[0].split("-")[0].strip()
    links = []
    for a in soup.find_all("a", href=True):
        label = (a.get_text(" ", strip=True) + " " + a["href"]).lower()
        if any(k in label for k in ("contact", "about", "اتصل", "تواصل", "من نحن", "اتصل بنا")):
            target = urljoin(base_url, a["href"].strip())
            if urlparse(target).netloc == urlparse(base_url).netloc and target not in links:
                links.append(target)
    return company[:180], sorted(phones), sorted(emails), links[:8]

def crawl_business(url, country, title="", snippet=""):
    if not _public_host(url):
        return None
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    pages = [url]
    visited, phones, emails, names = set(), set(), set(), []
    page_index = 0
    while page_index < len(pages) and len(visited) < 3:
        candidate = pages[page_index]
        page_index += 1
        if candidate in visited: continue
        visited.add(candidate)
        if not _robots_allows(candidate): continue
        response = safe_fetch(candidate)
        if response is None or "text/html" not in response.headers.get("Content-Type", "").lower():
            continue
        name, found_phones, found_emails, links = _extract_contact(response.text, response.url or candidate, country)
        if name: names.append(name)
        phones.update(found_phones); emails.update(found_emails)
        for link in links:
            if link not in visited and len(pages) < 3: pages.append(link)
        time.sleep(0.35)
    if not phones and not emails:
        return None
    return {"company": next((n for n in names if len(n) > 2), title.split("|")[0][:180]),
            "phone": ", ".join(sorted(phones)[:5]), "email": ", ".join(sorted(emails)[:5]),
            "website": url, "country": country, "city": "", "category": "",
            "source_url": url, "domain": domain, "notes": (snippet or "")[:500]}

def discover(query, country, limit=10):
    raw = search_web(query, country)
    results, seen = [], set()
    for item in raw:
        url = item.get("link", "")
        p = urlparse(url)
        domain = p.netloc.lower().removeprefix("www.")
        if not domain or domain in seen or p.scheme not in ("http", "https"):
            continue
        seen.add(domain)
        record = crawl_business(url, country, item.get("title", ""), item.get("snippet", ""))
        if record:
            results.append(record)
        if len(results) >= limit: break
    return results, len(raw)
