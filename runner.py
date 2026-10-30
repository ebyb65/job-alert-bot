import asyncio, json, os, re
from datetime import datetime, timedelta, timezone
from google import genai
from telegram import Bot
from job_sources import fetch_all, fetch_description

PREFS=json.load(open("search_preferences.json",encoding="utf-8")); HISTORY="sent_jobs.json"
MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash"); API=os.getenv("GEMINI_API_KEY",""); TOKEN=os.getenv("TELEGRAM_BOT_TOKEN",""); CHAT=os.getenv("TELEGRAM_CHAT_ID","")
client=genai.Client(api_key=API) if API else None

def history():
    try: data=json.load(open(HISTORY,encoding="utf-8"))
    except Exception: data={}
    cut=datetime.now(timezone.utc)-timedelta(days=30); out={}
    for k,v in data.items():
        try:
            d=datetime.fromisoformat(v); d=d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            if d>cut: out[k]=v
        except Exception: pass
    return out
def mark(i):
    d=history(); d[i]=datetime.now(timezone.utc).isoformat(); json.dump(d,open(HISTORY,"w",encoding="utf-8"),indent=2)
def salary(text):
    t=(text or "").lower(); nums=[]
    for m in re.finditer(r"(?:sar|riyal|riyals)\s*([0-9][0-9,]*)|([0-9][0-9,]*)\s*(?:sar|riyal|riyals)",t):
        try: nums.append(int((m.group(1) or m.group(2)).replace(",","")))
        except Exception: pass
    if not nums:return None,"undisclosed"
    val=max(nums); kind="basic" if "basic salary" in t else ("total" if any(x in t for x in ("total package","total salary","all inclusive","all-inclusive")) else "unclear")
    return val,kind
def salary_ok(job):
    val,kind=salary(job.get("description","")+" "+job.get("title","")); p=PREFS["salary_policy"]
    if val is None:return True,"Not disclosed — verify before applying"
    if kind=="basic":return val>=p["local_min_basic_sar"],f"Basic salary: SAR {val:,}"
    if kind=="total":return val>=p["local_min_total_sar"],f"Total package: SAR {val:,}"
    return True,f"Around SAR {val:,}; basic/total unclear — verify"
def heuristic(j):
    text=(j["title"]+" "+j.get("description","")).lower(); score=40
    terms=("hr","human resources","admin","administration","workforce","manpower","personnel","employee services","onboarding","mobilization","recruitment","payroll","timekeeping","office administrator","project administrator","operations coordinator","qiwa","muqeem","gosi")
    score+=min(40,sum(4 for x in terms if x in text))
    if any(x.lower() in j.get("location","").lower() for x in PREFS["preferred_locations"]): score+=10
    if any(x in text for x in ("saudi national only","saudi nationals only","tamheer","internship")): return 0
    return min(100,score)
def ai_score(j):
    if not client:return None
    prompt="""Evaluate the FULL vacancy against this verified candidate profile: 13+ years Saudi/UAE HR operations and administration; workforce/personnel administration; onboarding and recruitment coordination; Qiwa, Muqeem and GOSI; medical insurance; payroll validation; HR records and dashboards; visa/travel/housing coordination; vendor invoices/timesheets; document control; office/project administration. Bachelor of Computer Science. Do not invent qualifications. Assess evidence in the supplied job description, not title alone. Return JSON exactly with should_apply, match_score (0-100), reason, gaps (array), keywords (array), recommendation (Strong Apply/Apply/Consider/Skip). Vacancy: """+json.dumps(j,ensure_ascii=False)
    try:
        r=client.models.generate_content(model=MODEL,contents=prompt,config={"response_mime_type":"application/json"}); return json.loads(r.text)
    except Exception as e: print("AI:",e); return None
async def run():
    if not TOKEN or not CHAT: raise RuntimeError("Telegram secrets are required")
    bot=Bot(token=TOKEN); sent=history(); jobs=[j for j in fetch_all(PREFS,50) if j["history_id"] not in sent]; verified=[]; unverified=[]
    for j in jobs:
        if len(j.get("description","").strip())<250: j["description"]=fetch_description(j.get("link",""))
        if len(j.get("description","").strip())<250:
            if heuristic(j)>=60: unverified.append(j)
            else: mark(j["history_id"])
            continue
        ok,note=salary_ok(j)
        if not ok: mark(j["history_id"]); continue
        if heuristic(j)<60: mark(j["history_id"]); continue
        a=ai_score(j)
        if not a:
            unverified.append(j); continue
        s=int(a.get("match_score",0))
        if a.get("should_apply") and s>=PREFS["minimum_match_score"]: verified.append((s,j,a,note))
        else: mark(j["history_id"])
    verified.sort(reverse=True,key=lambda x:x[0])
    for s,j,a,note in verified[:10]:
        gaps="; ".join(a.get("gaps",[])[:4]) or "No major gap identified"
        rec=a.get("recommendation") or ("Strong Apply" if s>=85 else "Apply")
        msg=f"🤖 AI VERIFIED — {s}%\n{j['title']} | {j['company']}\n📍 {j['location']}\n🔎 {j['source']}\n💰 {note}\n✅ {rec}\nWhy: {a.get('reason','Relevant verified profile overlap')}\nGaps: {gaps}\nApply: {j['link']}"
        await bot.send_message(chat_id=CHAT,text=msg,disable_web_page_preview=True); mark(j["history_id"]); await asyncio.sleep(1)
    for j in unverified[:5]:
        msg=f"⚠️ UNVERIFIED — JD unavailable\n{j['title']} | {j['company']}\n📍 {j['location']}\n🔎 {j['source']}\nAI match score withheld because the full job description could not be retrieved.\nReview link: {j['link']}"
        await bot.send_message(chat_id=CHAT,text=msg,disable_web_page_preview=True); mark(j["history_id"]); await asyncio.sleep(1)
    if not verified and not unverified: await bot.send_message(chat_id=CHAT,text="No new suitable vacancies found today.")
if __name__=="__main__": asyncio.run(run())
