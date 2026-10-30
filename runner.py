import asyncio
import os
import re

from telegram import Bot

import main
from job_sources import fetch_all_jobs

ENABLED_SOURCES = [x.strip().lower() for x in os.getenv("JOB_SOURCES", "linkedin,indeed,naukrigulf,bayt,gulftalent").split(",") if x.strip()]


def tier(score):
    if score >= 85: return "PRIORITY APPLY"
    if score >= 75: return "STRONG MATCH"
    if score >= 65: return "REVIEW"
    return "LOW MATCH"


def salary_policy_note(job, profile):
    prefs = profile.get("compensation_preferences", {})
    text = " ".join([job.get("title", ""), job.get("description", "")])
    amounts = [int(x.replace(",", "")) for x in re.findall(r"(?i)(?:SAR|SR|﷼)\s*([0-9]{4,6}(?:,[0-9]{3})?)", text)]
    if not amounts:
        return True, "Salary not disclosed — verify before applying."
    amount = max(amounts)
    lower = text.lower()
    local = any(x.lower() in job.get("location", "").lower() for x in ["dammam", "khobar", "dhahran", "jubail", "eastern province"])
    is_basic = "basic salary" in lower or "basic:" in lower
    is_total = any(x in lower for x in ["total package", "total salary", "all inclusive", "all-inclusive", "package"])
    junior = any(x in job.get("title", "").lower() for x in ["junior", "assistant", "entry level", "entry-level"])
    if junior and amount < prefs.get("junior_role_min_total_sar", 8000):
        return False, f"Junior role salary SAR {amount:,} is below preference."
    if not local and amount <= prefs.get("relocation_min_total_sar_exclusive", 8000):
        return False, f"Relocation salary SAR {amount:,} does not exceed preference."
    if local and is_basic and amount < prefs.get("eastern_province_min_basic_sar", 5500):
        return False, f"Basic salary SAR {amount:,} is below Eastern Province preference."
    if local and is_total and amount < prefs.get("eastern_province_min_total_sar", 7500):
        return False, f"Total package SAR {amount:,} is below Eastern Province preference."
    if not is_basic and not is_total:
        return True, f"Salary stated as SAR {amount:,}, but basic/total type is unclear — verify before applying."
    return True, f"Salary indication: SAR {amount:,} ({'basic' if is_basic else 'total/package'})."


async def run():
    if not main.TELEGRAM_BOT_TOKEN or not main.TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    profile = main.load_profile()
    if not profile:
        raise RuntimeError("candidate_profile.json is missing or invalid")

    bot = Bot(token=main.TELEGRAM_BOT_TOKEN)
    sent = main.load_sent_jobs()
    jobs = fetch_all_jobs(profile, total_limit=max(main.MAX_JOBS, 50), enabled_sources=ENABLED_SOURCES)
    jobs = [j for j in jobs if j.get("history_id") not in sent]
    print(f"Discovered {len(jobs)} unseen vacancies from {', '.join(ENABLED_SOURCES)}")

    matches = []
    for idx, job in enumerate(jobs, 1):
        print(f"[{idx}/{len(jobs)}] {job.get('source')} | {job['title']} | {job['company']}")
        description = job.get("description") or main.fetch_job_description(job)
        job["description"] = description
        salary_ok, salary_note = salary_policy_note(job, profile)
        if not salary_ok:
            main.save_sent_job(job.get("history_id"))
            continue
        heuristic = main.heuristic_score(job, profile, description)
        if heuristic < 60:
            main.save_sent_job(job.get("history_id"))
            continue
        data = main.evaluate_with_ai(job, profile, description)
        if data is None:
            data = {"should_apply": heuristic >= main.MIN_MATCH_SCORE, "match_score": heuristic,
                    "match_reason": "AI unavailable; ranked from title, location and verified-profile overlap.",
                    "gaps": [], "ats_keywords": [], "ats_summary": profile.get("summary", ""),
                    "tailored_bullets": profile.get("verified_experience", [])[:5], "cover_letter": ""}
        score = int(data.get("match_score", 0))
        if data.get("should_apply") and score >= main.MIN_MATCH_SCORE:
            matches.append((score, job, data, salary_note))
        else:
            main.save_sent_job(job.get("history_id"))
        await asyncio.sleep(1.5)

    matches.sort(key=lambda x: x[0], reverse=True)
    if not matches:
        await main.notify(bot, "No new high-confidence HR/admin/workforce/onboarding matches were found today across the enabled sources.")
        return

    for score, job, data, salary_note in matches[:10]:
        gaps = "; ".join(data.get("gaps", [])[:4]) or "No major gap identified from the available description."
        keywords = ", ".join(data.get("ats_keywords", [])[:6]) or "Not extracted"
        msg = (f"🎯 {score}% — {tier(score)}\n{job['title']} | {job['company']}\n📍 {job.get('location','')}\n"
               f"🔎 Source: {job.get('source','Unknown')}" + (f" | Posted: {job['posted']}" if job.get('posted') else "") + "\n"
               f"💰 {salary_note}\nWhy: {data.get('match_reason','Strong overlap with verified experience.')}\n"
               f"Gaps: {gaps}\nATS: {keywords}\nApply: {job['link']}")
        await main.notify(bot, msg)
        safe_co = re.sub(r"[^A-Za-z0-9_-]+", "_", job["company"])[:24].strip("_") or "Company"
        filename = f"Eby_Benjamin_{safe_co}_{score}.docx"
        main.generate_complete_word_cv(job["title"], job["company"], profile, data, filename)
        with open(filename, "rb") as f:
            await bot.send_document(chat_id=main.TELEGRAM_CHAT_ID, document=f,
                                    caption=f"ATS CV | {job['title']} | {job['company']} | {score}% | {job.get('source','')}")
        os.remove(filename)
        cover = data.get("cover_letter", "").strip()
        if cover: await main.notify(bot, "Cover letter:\n\n" + cover)
        main.save_sent_job(job.get("history_id"))
        await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(run())
