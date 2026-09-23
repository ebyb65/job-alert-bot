import asyncio
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from google import genai
from telegram import Bot

GEMINI_API_KEY = "YOUR_ACTUAL_API_KEY".strip()
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN".strip()
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID".strip()

client = genai.Client(api_key=GEMINI_API_KEY)

HISTORY_FILE = "sent_jobs.json"

def load_sent_jobs():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                cutoff = datetime.now() - timedelta(days=5)
                return {k: v for k, v in data.items() if datetime.fromisoformat(v) > cutoff}
        except Exception:
            return {}
    return {}

def save_sent_job(job_id):
    sent = load_sent_jobs()
    sent[job_id] = datetime.now().isoformat()
    with open(HISTORY_FILE, "w") as f:
        json.dump(sent, f)

def extract_job_id(url):
    match = re.search(r'(\d{8,12})', url)
    return match.group(1) if match else None

def generate_complete_word_cv(job_title, company, cv_data, filename="Eby_Benjamin_CV.docx"):
    doc = Document()

    for s in doc.sections:
        s.top_margin = Inches(0.5)
        s.bottom_margin = Inches(0.5)
        s.left_margin = Inches(0.6)
        s.right_margin = Inches(0.6)

    # Styling helper
    navy = RGBColor(16, 44, 87)
    charcoal = RGBColor(50, 50, 50)

    # 1. Header Section
    p_name = doc.add_paragraph()
    r_name = p_name.add_run("EBY BENJAMIN")
    r_name.bold = True
    r_name.font.size = Pt(20)
    r_name.font.color.rgb = navy

    p_title = doc.add_paragraph()
    r_title = p_title.add_run(f"Senior HR Operations & Administrative Executive | Target: {job_title}")
    r_title.bold = True
    r_title.font.size = Pt(11)
    r_title.font.color.rgb = RGBColor(90, 90, 90)

    p_contact = doc.add_paragraph("Jubail, Eastern Province, Saudi Arabia | Transferable Iqama (Immediate Joiner) | Fluent English & Spoken Arabic")
    p_contact.runs[0].font.size = Pt(9.5)
    p_contact.paragraph_format.space_after = Pt(8)

    def add_section_header(title):
        h = doc.add_heading(title, level=2)
        h.runs[0].font.size = Pt(11.5)
        h.runs[0].font.bold = True
        h.runs[0].font.color.rgb = navy
        h.paragraph_format.space_before = Pt(8)
        h.paragraph_format.space_after = Pt(3)
        return h

    # 2. Executive Professional Summary
    add_section_header("PROFESSIONAL SUMMARY")
    p_sum = doc.add_paragraph(cv_data.get("ats_summary", ""))
    p_sum.runs[0].font.size = Pt(10)
    p_sum.paragraph_format.line_spacing = 1.15

    # 3. Core Competencies
    add_section_header("CORE EXPERTISE & TECHNICAL COMPETENCIES")
    kw_str = " • ".join(cv_data.get("ats_keywords", []))
    p_kw = doc.add_paragraph(f"Operational Focus: {kw_str}\nKey Domains: End-to-End Mobilization, Saudi Labor Law Compliance, Muqeem/Qiwa/GOSI, Shift Logistics, Camp Administration, ERP Systems.")
    p_kw.runs[0].font.size = Pt(9.5)
    p_kw.paragraph_format.line_spacing = 1.15

    # 4. Tailored Target Contributions
    add_section_header(f"TAILORED STRATEGIC CONTRIBUTIONS ({company.upper()})")
    for b in cv_data.get("tailored_bullets", []):
        bp = doc.add_paragraph(b, style='List Bullet')
        bp.paragraph_format.line_spacing = 1.15
        bp.runs[0].font.size = Pt(9.5)

    # 5. Career History
    add_section_header("PROFESSIONAL EXPERIENCE")
    
    # Job 1
    p_j1 = doc.add_paragraph()
    r1 = p_j1.add_run("Administrative Executive & Workforce Operations Coordinator\n")
    r1.bold = True
    r1.font.size = Pt(10.5)
    r2 = p_j1.add_run("Plant-Tech Arabia | Jubail, Saudi Arabia\n")
    r2.font.italic = True
    r2.font.size = Pt(9.5)
    
    j1_bullets = [
        "Orchestrated end-to-end mobilization, onboarding, and gate passes for multi-disciplinary workforce scaling up to 3,000 personnel across major industrial sites.",
        "Governed compliance with Saudi Labor Regulations, Iqama transfers, medical insurance renewals, and corporate camp housing allocations.",
        "Managed shift logs, muster sheets, attendance tracking, and cross-functional administrative reporting for plant shutdowns and plant operations.",
        "Facilitated bilingual executive correspondence and vendor relations in English and spoken Arabic."
    ]
    for b in j1_bullets:
        bp = doc.add_paragraph(b, style='List Bullet')
        bp.paragraph_format.line_spacing = 1.1
        bp.runs[0].font.size = Pt(9.5)

    # Job 2
    p_j2 = doc.add_paragraph()
    p_j2.paragraph_format.space_before = Pt(6)
    r3 = p_j2.add_run("HR & Operations Support Executive\n")
    r3.bold = True
    r3.font.size = Pt(10.5)
    r4 = p_j2.add_run("Corporate Logistics & Administrative Services | UAE & KSA\n")
    r4.font.italic = True
    r4.font.size = Pt(9.5)

    j2_bullets = [
        "Directed personnel logistics, cross-border visa clearances, and employment documentation for regional projects across Saudi Arabia and the UAE.",
        "Spearheaded onboarding schedules, personnel records maintenance, and digital employee files in compliance with GCC labor standards.",
        "Monitored departmental supply chains, transport coordination, and corporate camp infrastructure."
    ]
    for b in j2_bullets:
        bp = doc.add_paragraph(b, style='List Bullet')
        bp.paragraph_format.line_spacing = 1.1
        bp.runs[0].font.size = Pt(9.5)

    # 6. Education & Credentials
    add_section_header("EDUCATION & TECHNICAL CREDENTIALS")
    p_edu = doc.add_paragraph("Bachelor's Degree | Advanced ERP & MS Office Workflow Management | Saudi Labor Law & Compliance Frameworks")
    p_edu.runs[0].font.size = Pt(9.5)

    doc.save(filename)
    return filename

def fetch_linkedin_jobs(keywords=["HR Operations", "Workforce Coordinator", "HR Supervisor", "Operations Coordinator"], location="Saudi Arabia", total_limit=15):
    all_jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sent_history = load_sent_jobs()

    for kw in keywords:
        if len(all_jobs) >= total_limit:
            break
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={urllib.parse.quote(kw)}&location={urllib.parse.quote(location)}&start=0"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for card in soup.find_all("li"):
                    title = card.find("h3", class_="base-search-card__title")
                    company = card.find("h4", class_="base-search-card__subtitle")
                    loc = card.find("span", class_="job-search-card__location")
                    link = card.find("a", class_="base-card__full-link")
                    if title and link:
                        t_txt = title.text.strip()
                        if "tamheer" in t_txt.lower():
                            continue
                        clean_link = link['href'].split('?')[0]
                        job_id = extract_job_id(clean_link)
                        
                        if job_id and job_id in sent_history:
                            continue

                        if not any(j['link'] == clean_link for j in all_jobs):
                            all_jobs.append({
                                "title": t_txt,
                                "company": company.text.strip() if company else "Company Not Listed",
                                "location": loc.text.strip() if loc else location,
                                "link": clean_link,
                                "job_id": job_id
                            })
                    if len(all_jobs) >= total_limit:
                        break
        except Exception:
            pass
    return all_jobs

async def run_live_agent():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    print("Fetching active jobs from LinkedIn...")
    live_jobs = fetch_linkedin_jobs(total_limit=15)
    print(f"Discovered {len(live_jobs)} new vacancies. Processing...")

    for idx, job in enumerate(live_jobs):
        print(f"\nProcessing ({idx+1}/{len(live_jobs)}): {job['title']} at {job['company']}")

        prompt = f"""
        Act as an Executive Recruiter and ATS Specialist.
        Create an authentic, customized alignment for candidate Eby Benjamin (13+ years GCC experience in Saudi Arabia/UAE, workforce mobilization up to 3,000 personnel at Plant-Tech Arabia, Iqama transferable, spoken Arabic).

        TARGET ROLE:
        Title: {job['title']}
        Company: {job['company']}
        Location: {job['location']}

        REQUIREMENTS:
        1. Exclude roles strictly restricted to Saudi nationals only (Tamheer / Saudis only).
        2. Give genuine fit score (0-100).
        3. Identify salary if mentioned, otherwise "Not Disclosed".
        4. Generate 4 critical ATS keywords found in this specific job context.
        5. Write a completely UNIQUE 3-sentence ATS Professional Summary tailored directly to this vacancy's primary responsibilities. DO NOT USE GENERIC INTROS.
        6. Write 4 distinct bullet points showing how candidate's Plant-Tech Arabia / GCC background directly solves this company's challenges.
        7. Write an authentic, human cover letter (2 paragraphs max) addressing the hiring team directly without robotic AI clichés.

        Return JSON ONLY:
        {{
          "should_apply": true,
          "match_score": 88,
          "salary": "Not Disclosed",
          "ats_keywords": ["Keyword 1", "Keyword 2", "Keyword 3", "Keyword 4"],
          "ats_summary": "Unique ATS Summary...",
          "tailored_bullets": ["Detailed point 1", "Detailed point 2", "Detailed point 3", "Detailed point 4"],
          "cover_letter": "Authentic cover letter text..."
        }}
        """

        data = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                break
            except Exception as api_err:
                if "503" in str(api_err) and attempt < 2:
                    print(f"Gemini busy, retrying in 5s (Attempt {attempt+1}/3)...")
                    await asyncio.sleep(5)
                else:
                    print(f"Evaluation failed: {api_err}")

        # Universal app link
        job_id = job.get('job_id')
        app_url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else job['link']

        # Fallback if AI fails or limits out
        if not data:
            fallback_msg = (
                f"⚠️ *NEW JOB OPPORTUNITY (Manual Review)*\n\n"
                f"📌 *Designation:* {job['title']}\n"
                f"🏢 *Company:* {job['company']}\n"
                f"📍 *Location:* {job['location']}\n\n"
                f"🔗 [Direct LinkedIn Vacancy Link]({app_url})\n"
                f"_(AI evaluation was unavailable; link captured directly)_"
            )
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=fallback_msg, parse_mode="Markdown")
            if job_id:
                save_sent_job(job_id)
            continue

        if data.get("should_apply") and data.get("match_score", 0) >= 78:
            salary_val = data.get("salary", "Not Disclosed")
            keywords_str = ", ".join(data.get("ats_keywords", []))

            msg = (
                f"🎯 *MATCHING ROLE ({data['match_score']}%)*\n\n"
                f"📌 *Designation:* {job['title']}\n"
                f"🏢 *Company:* {job['company']}\n"
                f"📍 *Location:* {job['location']}\n"
                f"💰 *Salary:* `{salary_val}`\n"
                f"🔑 *ATS Keywords:* `{keywords_str}`\n\n"
                f"🚀 [Open Vacancy in LinkedIn App]({app_url})\n\n"
                f"📝 *Cover Letter:*\n`{data['cover_letter']}`\n\n"
                f"📎 *Tailored Word CV attached below:* 👇"
            )

            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")

            # Generate full-length tailored CV
            safe_co = "".join(c for c in job['company'] if c.isalnum() or c in (' ', '_')).rstrip()[:12].replace(" ", "_")
            cv_filename = f"Eby_Benjamin_{safe_co}.docx"
            doc_path = generate_complete_word_cv(job['title'], job['company'], data, filename=cv_filename)

            with open(doc_path, 'rb') as f:
                await bot.send_document(
                    chat_id=TELEGRAM_CHAT_ID,
                    document=f,
                    caption=f"📄 Complete ATS CV Tailored for {job['company']}"
                )

            if os.path.exists(doc_path):
                os.remove(doc_path)

            if job_id:
                save_sent_job(job_id)

            print(f"✅ Dispatched tailored package for {job['title']}")
        else:
            print(f"⏩ Filtered out: {job['title']} (Score: {data.get('match_score', 0)}%)")

        await asyncio.sleep(6)

if __name__ == "__main__":
asyncio.run(run_live_agent())
