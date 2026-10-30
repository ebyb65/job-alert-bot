import asyncio, json, os, re
from datetime import datetime, timedelta, timezone
from google import genai
from telegram import Bot
from job_sources import fetch_all

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
    if val is None:return True,"Salary not disclosed — verify before applying"
    if kind=="basic":return val>=p["local_min_basic_sar"],f"Basic salary detected: SAR {val:,}"
    if kind=="total":return val>=p["local_min_total_sar"],f"Total package detected: SAR {val:,}"
    return True,f"Salary detected around SAR {val:,}, but basic/total is unclear — verify"
def heuristic(j):
    text=(j["title"]+" "+j.get("description","")).lower(); score=40
    terms=("hr","human resources","admin","administration","workforce","manpower","personnel","employee services","onboarding","mobilization","recruitment","payroll","timekeeping","office administrator","project administrator","operations coordinator","qiwa","muqeem","gosi")
    score+=min(40,sum(4 for x in terms if x in text));
    if any(x.lower() in j.get("location","").lower() for x in PREFS["preferred_locations"]): score+=10
    if any(x in text for x in ("saudi national only","saudi nationals only","tamheer","internship")): return 0
    return min(100,score)
def ai_score(j):
    if not client:return None
    prompt="""Evaluate this vacancy for a candidate with 13+ years in Saudi/UAE HR operations, workforce/personnel administration, onboarding, recruitment coordination, Qiwa/Muqeem/GOSI, payroll validation, HR records/dashboards, visa/travel/housing coordination, vendor/timesheet coordination, document control and office administration. Do not invent qualifications. Return JSON: {\"should_apply\":true,\"match_score\":0,\"reason\":\"\",\"gaps\":[\"\"],\"keywords\":[\"\"]}. Consider HR, admin, workforce, onboarding, mobilization, employee services, payroll/timekeeping, project admin and operations coordination roles. Vacancy: """+json.dumps(j,ensure_ascii=False)
    try:
        r=client.models.generate_content(model=MODEL,contents=prompt,config={"response_mime_type":"application/json"}); return json.loads(r.text)
    except Exception as e: print("AI:",e); return None
async def run():
    if not TOKEN or not CHAT: raise RuntimeError("Telegram secrets are required")
    bot=Bot(token=TOKEN); sent=history(); jobs=[j for j in fetch_all(PREFS,50) if j["history_id"] not in sent]; matches=[]
    for j in jobs:
        ok,note=salary_ok(j)
        if not ok: mark(j["history_id"]); continue
        h=heuristic(j)
        if h<60: mark(j["history_id"]); continue
        a=ai_score(j) or {"should_apply":h>=PREFS["minimum_match_score"],"match_score":h,"reason":"Keyword/profile overlap","gaps":[],"keywords":[]}
        s=int(a.get("match_score",0))
        if a.get("should_apply") and s>=PREFS["minimum_match_score"]: matches.append((s,j,a,note))
        else: mark(j["history_id"])
    matches.sort(reverse=True,key=lambda x:x[0])
    if not matches: await bot.send_message(chat_id=CHAT,text="No new high-confidence HR/admin/workforce matches found today."); return
    for s,j,a,note in matches[:10]:
        gaps="; ".join(a.get("gaps",[])[:4]) or "No major gap identified"
        msg=f"🎯 {s}% MATCH\n{j['title']} | {j['company']}\n📍 {j['location']}\n🔎 {j['source']}\n💰 {note}\nWhy: {a.get('reason','Relevant profile overlap')}\nGaps: {gaps}\nApply: {j['link']}"
        await bot.send_message(chat_id=CHAT,text=msg,disable_web_page_preview=True); mark(j["history_id"]); await asyncio.sleep(1)
if __name__=="__main__": asyncio.run(run())
