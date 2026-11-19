"""Daily job matcher for Eby Benjamin.

Pipeline (cheapest checks first, so the AI only sees plausible jobs):
  1. Scrape boards                     -> job_sources.fetch_all
  2. Title + location gate             -> drops sales/engineering/junior/Saudi-only/out-of-area jobs instantly
  3. Full job description required     -> no more "UNVERIFIED" alerts based on a title alone
  4. Description blockers + salary floor
  5. Strict AI review                  -> must be a core HR/Admin/Mobilization role, right seniority, no blockers
Only jobs that pass every step are sent to Telegram.
"""
import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from google import genai
from telegram import Bot

from job_sources import fetch_all, fetch_description

PREFS = json.load(open("search_preferences.json", encoding="utf-8"))
HISTORY = "sent_jobs.json"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
API = os.getenv("GEMINI_API_KEY", "")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
client = genai.Client(api_key=API) if API else None


# ---- history -------------------------------------------------------------
def load_history():
    try:
        data = json.load(open(HISTORY, encoding="utf-8"))
    except Exception:
        data = {}
    cut = datetime.now(timezone.utc) - timedelta(days=30)
    out = {}
    for k, v in data.items():
        try:
            d = datetime.fromisoformat(v)
            d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            if d > cut:
                out[k] = v
        except Exception:
            pass
    return out


def save_history(h):
    json.dump(h, open(HISTORY, "w", encoding="utf-8"), indent=2)


# ---- rule-based gates ----------------------------------------------------
def _rx(words):
    return re.compile(r"(?<![\w])(?:" + "|".join(words) + r")(?![\w])", re.I) if words else None


TITLE_OK = _rx(PREFS["title_must_match_any"])
TITLE_BAD = _rx(PREFS["title_reject_any"])
DESC_BAD = _rx(PREFS["description_reject_any"])
LOCAL = [x.lower() for x in PREFS["local_locations"]]
RELOC = [x.lower() for x in PREFS["relocation_locations"]]


def location_kind(job):
    loc = (job.get("location") or "").lower()
    if any(x in loc for x in LOCAL):
        return "local"
    if any(x in loc for x in RELOC):
        return "relocation"
    if loc.strip() in ("saudi arabia", "ksa", "kingdom of saudi arabia", ""):
        return "local"  # city not stated — let the AI/description decide
    return None


def title_gate(job):
    """Return a rejection reason, or None if the job may proceed."""
    t = job["title"]
    if not TITLE_OK.search(t):
        return "title not HR/Admin"
    m = TITLE_BAD.search(t)
    if m:
        return f"title blocked ('{m.group(0)}')"
    if location_kind(job) is None:
        return f"location '{job.get('location')}' outside target area"
    return None


def parse_salary(text):
    t = (text or "").lower()
    nums = []
    num = r"([0-9][0-9,]{2,})"
    rng = num + r"(?:\s*(?:-|–|to)\s*" + num + ")?"
    for m in re.finditer(r"(?:sar|sr|riyals?)\s*\.?\s*" + rng + "|" + rng + r"\s*(?:sar|sr|riyals?)\b", t):
        for g in m.groups():
            if g:
                try:
                    nums.append(int(g.replace(",", "")))
                except Exception:
                    pass
    nums = [n for n in nums if 1500 <= n <= 60000]  # monthly figures only
    if not nums:
        return None, "undisclosed"
    kind = "basic" if "basic salary" in t else ("total" if any(x in t for x in ("total package", "total salary", "all inclusive", "all-inclusive", "gross")) else "unclear")
    return max(nums), kind


def salary_check(job):
    val, kind = parse_salary(job.get("description", "") + " " + job.get("title", ""))
    p = PREFS["salary_policy"]
    reloc = location_kind(job) == "relocation"
    if val is None:
        return True, "Not disclosed — verify before applying"
    if kind == "basic" and not reloc:
        return val >= p["local_min_basic_sar"], f"Basic salary: SAR {val:,}"
    floor = p["relocation_min_total_sar"] if reloc else p["local_min_total_sar"]
    label = "Total package" if kind == "total" else "Around"
    note = f"{label} SAR {val:,}" + ("" if kind == "total" else " (basic/total unclear — verify)")
    return val >= floor, note


# ---- AI review -----------------------------------------------------------
PROFILE = """CANDIDATE: Eby Benjamin — Indian national, transferable Iqama, lives in Jubail (Eastern Province, KSA).
Open to Jubail/Dammam/Khobar/Dhahran and relocation to Riyadh.
Experience: 12+ years in the GCC. Craft Accessories LLC, Abu Dhabi (2013–2016); Plant-Tech Arabia, Jubail (2017–present),
an industrial plant-maintenance/shutdown contractor. Official title Sr. Admin Executive; in practice runs HR operations
and administration.
Verified hands-on work:
- HR operations for ~1,500 permanent staff: full employee lifecycle for permanent AND visit-visa staff
- Workforce mobilization: 600–1,200 visit-visa workers per year; peak 1,000–1,600 for a single shutdown
- Saudi government systems: Qiwa contracts (create/edit/terminate), Muqeem, GOSI; iqama, visa, exit/re-entry processing
- Recruitment coordination: collects manpower requests, briefs recruitment agencies, schedules interviews, posts job ads
- Onboarding, HR letters, salary/experience certificates, personnel files, headcount reports, recruitment and leave trackers
- Medical insurance, accommodation/camp, transport and travel coordination; vendor invoices and timesheets; document control
- Office administration: supplies, ERP requests, supervises office boys and housekeeping staff
Working knowledge only (NOT hands-on): Mudad, payroll processing, Power BI (learning).
Education: Bachelor of Computer Science (not an HR degree). No CIPD/SHRM/HRCI certification.
TARGET ROLES: HR Operations, HR Officer/Coordinator/Generalist/Supervisor, HR & Admin, Personnel/Workforce administration,
Mobilization, Recruitment/Talent Acquisition, Global Mobility, senior Office/Project Administration.
NOT WANTED: sales, marketing, engineering, IT, finance/accounting, customer service, logistics/procurement, healthcare,
clerical/assistant/receptionist roles, internships/fresh-graduate roles, director/head-of/C-level roles,
roles for Saudi nationals only or female candidates only."""

PROMPT = PROFILE + """

You are a strict recruiter screening on the candidate's behalf. He is tired of irrelevant alerts: when in doubt, SKIP.
Judge from the FULL job description, not the title. Do not invent qualifications he does not have.

Rules:
- core_function_match = true ONLY if most of the listed duties are HR operations, HR/personnel administration,
  recruitment, mobilization, or general administration. A job that merely mentions "HR" or "coordination" while being
  mainly sales/technical/finance/logistics/customer work is false.
- seniority_fit: "too_junior" (assistant/clerk/0–3 yrs, or pay clearly below an experienced officer),
  "fit" (officer/specialist/coordinator/supervisor/manager needing about 3–15 yrs), or "too_senior" (director/head/C-level).
- hard_blockers: list anything that makes him ineligible: Saudi nationals only, female only, must already be in another
  country, mandatory professional licence he lacks, role located outside Saudi Arabia. Missing a preferred HR degree or
  certificate is a GAP, not a blocker.
- match_score (0–100): 90+ = duties are almost exactly what he does today; 80–89 = strong overlap with a few gaps;
  60–79 = partial overlap; below 60 = poor fit.
- evidence: 2–4 short phrases copied from the job description that justify the score.

Return JSON only:
{"core_function_match": bool, "seniority_fit": "fit|too_junior|too_senior", "hard_blockers": [str],
 "match_score": int, "reason": str (one sentence), "evidence": [str], "gaps": [str],
 "recommendation": "Strong Apply|Apply|Skip"}

VACANCY:
"""


def ai_review(job):
    if not client:
        return None
    vacancy = {k: job[k] for k in ("title", "company", "location", "description")}
    vacancy["description"] = vacancy["description"][:9000]
    for attempt in range(3):
        try:
            r = client.models.generate_content(model=MODEL, contents=PROMPT + json.dumps(vacancy, ensure_ascii=False),
                                               config={"response_mime_type": "application/json", "temperature": 0})
            return json.loads(r.text)
        except Exception as e:
            print(f"AI attempt {attempt + 1}: {e}")
            time.sleep(5 * (attempt + 1))
    return None


def accept(a):
    try:
        score = int(a.get("match_score", 0))
    except Exception:
        score = 0
    ok = (a.get("core_function_match") is True and a.get("seniority_fit") == "fit" and not a.get("hard_blockers")
          and a.get("recommendation") != "Skip" and score >= PREFS["minimum_match_score"])
    return ok, score


# ---- main ----------------------------------------------------------------
async def run():
    if not TOKEN or not CHAT:
        raise RuntimeError("Telegram secrets are required")
    bot = Bot(token=TOKEN)
    hist = load_history()
    now = lambda: datetime.now(timezone.utc).isoformat()
    stats = {"title/location rejected": 0, "no description": 0, "description blocked": 0,
             "salary too low": 0, "AI rejected": 0, "AI unavailable": 0}

    def keep(j):
        if j["history_id"] in hist:
            return False
        reason = title_gate(j)
        if reason:
            stats["title/location rejected"] += 1
            hist[j["history_id"]] = now()  # never look at it again
            return False
        return True

    try:
        candidates = fetch_all(PREFS, keep)
        candidates.sort(key=lambda j: location_kind(j) != "local")  # local jobs first
        print(f"{len(candidates)} jobs passed the title/location gate")

        verified, unverified, ai_calls = [], [], 0
        for j in candidates:
            if ai_calls >= PREFS["max_ai_evaluations_per_run"]:
                break  # the rest stay unmarked and will be checked next run
            if len(j.get("description", "")) < 250:
                j["description"] = fetch_description(j)
                time.sleep(1)
            if len(j["description"]) < 250:
                stats["no description"] += 1
                if PREFS.get("send_unverified"):
                    unverified.append(j)
                continue  # not marked: retried next run while the posting is still live
            m = DESC_BAD.search(j["description"])
            if m:
                stats["description blocked"] += 1
                hist[j["history_id"]] = now()
                print(f"  ✗ {j['title']} — description: '{m.group(0)}'")
                continue
            ok, sal_note = salary_check(j)
            if not ok:
                stats["salary too low"] += 1
                hist[j["history_id"]] = now()
                continue
            ai_calls += 1
            a = ai_review(j)
            if not a:
                stats["AI unavailable"] += 1
                continue  # not marked, retried next run — never sent blind
            good, score = accept(a)
            print(f"  {'✓' if good else '✗'} {score:>3}% {j['title']} | {j['company']} — {a.get('reason', '')}")
            if good:
                verified.append((score, j, a, sal_note))
            else:
                stats["AI rejected"] += 1
                hist[j["history_id"]] = now()

        verified.sort(key=lambda x: -x[0])
        for score, j, a, sal_note in verified[:PREFS["max_alerts_per_run"]]:
            evidence = "\n".join("• " + e for e in a.get("evidence", [])[:3])
            gaps = "; ".join(a.get("gaps", [])[:3]) or "None significant"
            msg = (f"🎯 {score}% MATCH — {a.get('recommendation', 'Apply')}\n"
                   f"{j['title']}\n🏢 {j['company']}\n📍 {j['location']}   🔎 {j['source']}\n💰 {sal_note}\n\n"
                   f"Why: {a.get('reason', '')}\n{evidence}\n\n⚠️ Gaps: {gaps}\n\n👉 {j['link']}")
            await bot.send_message(chat_id=CHAT, text=msg, disable_web_page_preview=True)
            hist[j["history_id"]] = now()
            await asyncio.sleep(1)

        for j in unverified[:3]:
            await bot.send_message(chat_id=CHAT, disable_web_page_preview=True,
                                   text=f"⚠️ UNVERIFIED (description unavailable)\n{j['title']} | {j['company']}\n📍 {j['location']}\n👉 {j['link']}")
            hist[j["history_id"]] = now()

        print("Summary:", stats)
        if not verified:
            note = "No new jobs matching your profile today."
            if stats["AI unavailable"]:
                note += f"\n({stats['AI unavailable']} jobs couldn't be AI-checked — they'll be retried tomorrow.)"
            await bot.send_message(chat_id=CHAT, text=note)
    finally:
        save_history(hist)


if __name__ == "__main__":
    asyncio.run(run())
