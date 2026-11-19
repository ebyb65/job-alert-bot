"""Job board scrapers. Each source returns a list of job dicts built with make_job()."""
import hashlib
import json
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def clean(x):
    return re.sub(r"\s+", " ", BeautifulSoup(x or "", "html.parser").get_text(" ")).strip()


def linkedin_id(link):
    m = re.findall(r"(\d{8,})", link or "")
    return m[-1] if m else None


def make_job(source, title, company, location, link, description="", posted=""):
    link = (link or "").split("#")[0].split("?")[0]
    return {"source": source, "title": clean(title), "company": clean(company) or "Company Not Listed",
            "location": clean(location), "link": link, "description": clean(description), "posted": clean(posted),
            "history_id": source + ":" + hashlib.sha256(link.encode()).hexdigest()[:18]}


def get(url, retries=1):
    """GET with one polite retry when the site says 'too many requests'."""
    for attempt in range(retries + 1):
        r = SESSION.get(url, timeout=15)
        if r.status_code == 429 and attempt < retries:
            time.sleep(12)
            continue
        r.raise_for_status()
        return r.text


def walk_json(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_json(v)


def jsonld(html, source, base):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        for obj in walk_json(data):
            typ = obj.get("@type")
            if typ != "JobPosting" and not (isinstance(typ, list) and "JobPosting" in typ):
                continue
            org = obj.get("hiringOrganization") or {}
            jl = obj.get("jobLocation") or {}
            if isinstance(jl, list):
                jl = jl[0] if jl else {}
            addr = jl.get("address", {}) if isinstance(jl, dict) else {}
            if not isinstance(addr, dict):
                addr = {}
            loc = ", ".join(str(addr.get(k, "")) for k in ("addressLocality", "addressRegion", "addressCountry") if addr.get(k))
            out.append(make_job(source, obj.get("title", ""), org.get("name", "") if isinstance(org, dict) else "",
                                loc, obj.get("url") or base, obj.get("description", ""), obj.get("datePosted", "")))
    return out


def fetch_description(job):
    """Get the full job description. LinkedIn uses its public guest API, which works without login."""
    link = job.get("link", "")
    if not link:
        return ""
    if job.get("source") == "LinkedIn":
        jid = linkedin_id(link)
        if jid:
            try:
                soup = BeautifulSoup(get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"), "html.parser")
                node = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
                crit = " ".join(clean(str(li)) for li in soup.select(".description__job-criteria-item"))
                if node:
                    return clean(str(node)) + (" | " + crit if crit else "")
            except Exception as e:
                print("LinkedIn JD:", e)
        return ""  # LinkedIn's normal job page needs login; no point trying it
    try:
        html = get(link)
    except Exception as e:
        print("JD:", e)
        return ""
    jobs = jsonld(html, "Direct", link)
    if jobs and jobs[0].get("description"):
        return jobs[0]["description"]
    soup = BeautifulSoup(html, "html.parser")
    for sel in (".show-more-less-html__markup", ".description__text", "[data-automation-id='jobPostingDescription']",
                "#jobDescriptionText", ".job-description", ".jobDescription", "article"):
        node = soup.select_one(sel)
        if node and len(clean(str(node))) >= 250:
            return clean(str(node))
    return ""


# ---- sources -------------------------------------------------------------
def linkedin(q, loc):
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=" + urllib.parse.quote(q)
           + "&location=" + urllib.parse.quote(loc) + "&f_TPR=r604800&start=0")
    soup = BeautifulSoup(get(url), "html.parser")
    out = []
    for c in soup.find_all("li"):
        t = c.find("h3", class_="base-search-card__title")
        a = c.find("a", class_="base-card__full-link")
        co = c.find("h4", class_="base-search-card__subtitle")
        lo = c.find("span", class_="job-search-card__location")
        if t and a:
            out.append(make_job("LinkedIn", t.get_text(), co.get_text() if co else "", lo.get_text() if lo else loc, a.get("href", "")))
    time.sleep(3)  # be gentle; LinkedIn returns 429 if hammered
    return out


def indeed(q, loc):
    return jsonld(get("https://sa.indeed.com/jobs?q=" + urllib.parse.quote(q) + "&l=" + urllib.parse.quote(loc) + "&fromage=7"), "Indeed", "")


def naukrigulf(q, loc):
    return jsonld(get("https://www.naukrigulf.com/jobs?k=" + urllib.parse.quote(q) + "&l=" + urllib.parse.quote(loc)), "Naukrigulf", "")


def bayt(q, loc):
    return jsonld(get("https://www.bayt.com/en/saudi-arabia/jobs/?q=" + urllib.parse.quote(q)), "Bayt", "")


def gulftalent(q, loc):
    return jsonld(get("https://www.gulftalent.com/saudi-arabia/jobs?keywords=" + urllib.parse.quote(q)), "GulfTalent", "")


# name -> (function, uses location?)  Sources that ignore location are queried once per search term.
SOURCES = {"linkedin": (linkedin, True), "indeed": (indeed, True), "naukrigulf": (naukrigulf, True),
           "bayt": (bayt, False), "gulftalent": (gulftalent, False)}


def fetch_all(prefs, keep=lambda j: True):
    """Collect jobs from every enabled source. A source that errors (blocked, 403, 429) is skipped for the rest of the run."""
    enabled = prefs.get("sources", {})
    dead, seen, out, stats = set(), set(), [], {}
    for q in prefs["search_queries"]:
        for name, (fn, uses_loc) in SOURCES.items():
            if not enabled.get(name, True) or name in dead:
                continue
            for loc in (prefs["search_locations"] if uses_loc else prefs["search_locations"][:1]):
                if name in dead:
                    break
                try:
                    found = fn(q, loc)
                except Exception as e:
                    print(f"{name}: disabled for this run ({e})")
                    dead.add(name)
                    break
                stats[name] = stats.get(name, 0) + len(found)
                for j in found:
                    key = (re.sub(r"\W+", " ", j["title"].lower()).strip(), re.sub(r"\W+", " ", j["company"].lower()).strip())
                    if key in seen:
                        continue
                    seen.add(key)
                    if keep(j):
                        out.append(j)
    print("Raw results per source:", stats)
    return out
