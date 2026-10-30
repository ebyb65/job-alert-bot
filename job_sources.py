import hashlib
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def stable_id(source, url):
    return f"{source}:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:18]}"


def make_job(source, title, company, location, link, description="", posted=""):
    link = (link or "").split("#")[0]
    return {
        "source": source,
        "title": clean(title),
        "company": clean(company) or "Company Not Listed",
        "location": clean(location),
        "link": link,
        "description": clean(description),
        "posted": clean(posted),
        "history_id": stable_id(source, link),
    }


def _get(url, timeout=18):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _jsonld_jobs(html, source, base_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for obj in items:
            if not isinstance(obj, dict) or obj.get("@type") != "JobPosting":
                continue
            org = obj.get("hiringOrganization") or {}
            addr = ((obj.get("jobLocation") or {}).get("address") or {}) if isinstance(obj.get("jobLocation"), dict) else {}
            location = ", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")] if x)
            link = obj.get("url") or base_url
            out.append(make_job(source, obj.get("title", ""), org.get("name", ""), location, link, obj.get("description", ""), obj.get("datePosted", "")))
    return out


def fetch_linkedin(keyword, location):
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={urllib.parse.quote(keyword)}&location={urllib.parse.quote(location)}&f_TPR=r604800&start=0"
    )
    try:
        soup = BeautifulSoup(_get(url).text, "html.parser")
    except Exception as e:
        print(f"LinkedIn source error: {e}")
        return []
    out = []
    for card in soup.find_all("li"):
        title = card.find("h3", class_="base-search-card__title")
        company = card.find("h4", class_="base-search-card__subtitle")
        loc = card.find("span", class_="job-search-card__location")
        link = card.find("a", class_="base-card__full-link")
        if title and link:
            out.append(make_job("LinkedIn", title.get_text(), company.get_text() if company else "", loc.get_text() if loc else location, link.get("href", "").split("?")[0]))
    return out


def fetch_naukrigulf(keyword, location):
    # Public search pages; parser is intentionally defensive because markup changes.
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    loc = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
    urls = [
        f"https://www.naukrigulf.com/{slug}-jobs-in-{loc}",
        f"https://www.naukrigulf.com/jobs?k={urllib.parse.quote(keyword)}&l={urllib.parse.quote(location)}",
    ]
    for url in urls:
        try:
            html = _get(url).text
            jobs = _jsonld_jobs(html, "Naukrigulf", url)
            if jobs:
                return jobs
            soup = BeautifulSoup(html, "html.parser")
            out = []
            for a in soup.select('a[href*="job-listings"], a[href*="jobs-in"]'):
                title = clean(a.get_text(" ", strip=True))
                href = urllib.parse.urljoin("https://www.naukrigulf.com", a.get("href", ""))
                if title and len(title) < 140 and href:
                    out.append(make_job("Naukrigulf", title, "", location, href))
            if out:
                return out
        except Exception as e:
            print(f"Naukrigulf source error: {e}")
    return []


def fetch_bayt(keyword, location):
    # Bayt exposes public job-search pages. Query parameters may evolve, so JSON-LD is preferred.
    url = f"https://www.bayt.com/en/saudi-arabia/jobs/?q={urllib.parse.quote(keyword)}"
    try:
        html = _get(url).text
        jobs = _jsonld_jobs(html, "Bayt", url)
        if jobs:
            return [j for j in jobs if not location or location.lower() in (j.get("location") or "").lower() or "saudi" in location.lower()]
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for card in soup.select('[data-js-aid="jobID"], .has-pointer-d'):
            a = card.select_one('a[href*="/job/"]') or card.find("a", href=True)
            if not a:
                continue
            title = clean(a.get_text(" ", strip=True))
            href = urllib.parse.urljoin("https://www.bayt.com", a.get("href", ""))
            if title:
                out.append(make_job("Bayt", title, "", location, href))
        return out
    except Exception as e:
        print(f"Bayt source error: {e}")
        return []


def fetch_gulftalent(keyword, location):
    # GulfTalent public Saudi job pages are a useful Gulf-specific fallback.
    url = f"https://www.gulftalent.com/saudi-arabia/jobs?keywords={urllib.parse.quote(keyword)}"
    try:
        html = _get(url).text
        jobs = _jsonld_jobs(html, "GulfTalent", url)
        if jobs:
            return jobs
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for a in soup.select('a[href*="/jobs/"]'):
            title = clean(a.get_text(" ", strip=True))
            href = urllib.parse.urljoin("https://www.gulftalent.com", a.get("href", ""))
            if title and 3 < len(title) < 140:
                out.append(make_job("GulfTalent", title, "", location, href))
        return out
    except Exception as e:
        print(f"GulfTalent source error: {e}")
        return []


def fetch_indeed(keyword, location):
    # Conservative public discovery only. If Indeed blocks automated access, fail closed rather than bypass controls.
    url = f"https://sa.indeed.com/jobs?q={urllib.parse.quote(keyword)}&l={urllib.parse.quote(location)}&fromage=7"
    try:
        html = _get(url).text
        jobs = _jsonld_jobs(html, "Indeed", url)
        if jobs:
            return jobs
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for card in soup.select("div.job_seen_beacon, .jobsearch-SerpJobCard"):
            a = card.select_one('a[href*="/viewjob"], a.jcs-JobTitle')
            if not a:
                continue
            title = clean(a.get_text(" ", strip=True))
            company = card.select_one('[data-testid="company-name"], .companyName')
            loc = card.select_one('[data-testid="text-location"], .companyLocation')
            href = urllib.parse.urljoin("https://sa.indeed.com", a.get("href", ""))
            out.append(make_job("Indeed", title, company.get_text() if company else "", loc.get_text() if loc else location, href))
        return out
    except Exception as e:
        print(f"Indeed source unavailable (no bypass attempted): {e}")
        return []


SOURCES = {
    "linkedin": fetch_linkedin,
    "indeed": fetch_indeed,
    "naukrigulf": fetch_naukrigulf,
    "bayt": fetch_bayt,
    "gulftalent": fetch_gulftalent,
}


def _dedupe_key(job):
    title = re.sub(r"\W+", " ", job.get("title", "").lower()).strip()
    company = re.sub(r"\W+", " ", job.get("company", "").lower()).strip()
    location = re.sub(r"\W+", " ", job.get("location", "").lower()).strip()
    return (title, company, location)


def fetch_all_jobs(profile, total_limit=50, enabled_sources=None):
    enabled_sources = enabled_sources or list(SOURCES)
    roles = (profile.get("target_roles") or ["HR Operations", "HR Executive", "HR Officer"])[:8]
    locations = (profile.get("preferred_locations") or ["Dammam", "Khobar", "Jubail", "Eastern Province", "Saudi Arabia"])[:6]
    collected = []
    seen = set()

    # Rotate role/location combinations so one source cannot consume the whole quota.
    for role in roles:
        for location in locations:
            for name in enabled_sources:
                fn = SOURCES.get(name.lower())
                if not fn:
                    continue
                for job in fn(role, location):
                    lower = f"{job.get('title','')} {job.get('description','')}".lower()
                    if any(x in lower for x in ["tamheer", "internship", "graduate trainee", "saudi nationals only", "saudi national only"]):
                        continue
                    key = _dedupe_key(job)
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(job)
                    if len(collected) >= total_limit:
                        return collected
                time.sleep(0.25)
    return collected
