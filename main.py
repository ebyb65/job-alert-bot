import asyncio
import json
import urllib.parse
import requests
import re
import os
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from google import genai
from telegram import Bot

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

client = genai.Client(api_key=GEMINI_API_KEY)

MASTER_CV_DATA = """
CANDIDATE: Eby Benjamin
EXPERIENCE: 13+ years GCC experience in Saudi Arabia & UAE.
DOMAINS: HR Operations, Workforce Mobilization, Personnel Logistics, Onboarding, Executive Administration.
HIGHLIGHTS: Scaled, mobilized, and managed documentation for up to 3,000 personnel (Plant-Tech Arabia). Shift scheduling, gate passes, camp administration, safety compliance, labor relations.
LOCATION: Jubail, Saudi Arabia (Transferable Iqama, Immediate Joiner).
LANGUAGES: Fluent English, Professional working proficiency in spoken Arabic.
"""

def extract_job_id(url):
    match = re.search(r'(\d{8,12})', url)
    return match.group(1) if match else None

def generate_word_cv(job_title, company, cv_data, filename="Tailored_CV.docx"):
    doc = Document()
    
    # Page margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    # Header
    name_p = doc.add_paragraph()
    run_name = name_p.add_run("EBY BENJAMIN")
    run_name.bold = True
    run_name.font.size = Pt(18)
    run_name.font.color.rgb = RGBColor(16, 44, 87)
    
    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"Senior HR Operations & Administration Professional | Tailored for: {job_title}")
    sub_run.bold = True
    sub_run.font.size = Pt(10)
    sub_run.font.color.rgb = RGBColor(80, 80, 80)
    
    contact_p = doc.add_paragraph("Jubail, Eastern Province, Saudi Arabia | Transferable Iqama (Immediate Joiner) | Fluent English & Spoken Arabic")
    contact_p.runs[0].font.size = Pt(9)
    contact_p.runs[0].font.italic = True
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # Professional Summary
    h1 = doc.add_heading("PROFESSIONAL SUMMARY", level=2)
    h1.runs[0].font.size = Pt(12)
    h1.runs[0].font.color.rgb = RGBColor(16, 44, 87)
    p_sum = doc.add_paragraph(cv_data.get("ats_summary", ""))
    p_sum.paragraph_format.line_spacing = 1.15
    p_sum.runs[0].font.size = Pt(10)

    # Core Competencies / ATS Keywords
    h2 = doc.add_heading("CORE EXPERTISE & ALIGNED COMPETENCIES", level=2)
    h2.runs[0].font.size = Pt(12)
    h2.runs[0].font.color.rgb = RGBColor(16, 44, 87)
    keywords = ", ".join(cv_data.get("ats_keywords", []))
    p_kw = doc.add_paragraph(f"Key Domains: {keywords} | Workforce Mobilization | GCC Labor Compliance | Operational Logistics")
    p_kw.runs[0].font.size = Pt(10)

    # Key Tailored Contributions
    h3 = doc.add_heading(f"TARGETED ACHIEVEMENTS & CONTRIBUTIONS ({company})", level=2)
    h3.runs[0].font.size = Pt(12)
    h3.runs[0].font.color.rgb = RGBColor(16, 44, 87)
    for bullet in cv_data.get("tailored_bullets", []):
        bp = doc.add_paragraph(bullet, style='List Bullet')
        bp.paragraph_format.line_spacing = 1.15
        bp.runs[0].font.size = Pt(10)

    # Baseline Work History
    h4 = doc.add_heading("CAREER TIMELINE & CORE SCOPE", level=2)
    h4.runs[0].font.size = Pt(12)
    h4.runs[0].font.color.rgb = RGBColor(16, 44, 87)
    
    p_job = doc.add_paragraph()
    r_j1 = p_job.add_run("Administrative Executive & Operations Coordinator | Plant-Tech Arabia, Jubail\n")
    r_j1.bold = True
    r_j1.font.size = Pt(10)
    r_j2 = p_job.add_run("• Directed end-to-end mobilization, onboarding, and gate passes for up to 3,000 workforce.\n• Managed multi-shift camp logistics, resource allocation, and regulatory compliance.\n• Facilitated executive communications, ERP HR reports, and dispute resolutions.")
    r_j2.font.size = Pt(9.5)
    
    doc.save(filename)
    return filename

def fetch_linkedin_jobs(keywords=["HR Operations", "Workforce Coordinator", "People Culture"], location="Saudi Arabia", total_limit=6):
    all_jobs = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
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
                        if not any(j['link'] == clean_link for j in all_jobs):
                            all_jobs.append({
                                "title": t_txt,
                                "company": company.text.strip() if company else "Company Not Listed",
                                "location": loc.text.strip() if loc else location,
                                "link": clean_link,
                                "job_id": extract_job_id(clean_link)
                            })
                    if len(all_jobs) >= total_limit:
                        break
        except Exception:
            pass
    return all_jobs

async def run_live_agent():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    live_jobs = fetch_linkedin_jobs(total_limit=4)

    for job in live_jobs:
        prompt = f"""
        Act as an ATS Expert. Create a tailored application alignment.
        {MASTER_CV_DATA}
        TARGET JOB: {job['title']} at {job['company']} in {job['location']}
        
        Return JSON ONLY:
        {{
          "should_apply": true,
          "match_score": 88,
          "ats_keywords": ["Keyword 1", "Keyword 2", "Keyword 3", "Keyword 4"],
          "ats_summary": "ATS optimized professional summary aligning candidate experience...",
          "tailored_bullets": [
             "Action verb + metric + keyword matching target role",
             "Point 2", "Point 3", "Point 4"
          ],
          "cover_letter": "Authentic, human cover letter"
        }}
        """
        try:
            response = client.models.generate_content(
                model="models/gemini-2.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            
            if data.get("should_apply") and data.get("match_score", 0) >= 78:
                app_link = f"linkedin://jobs/view/{job['job_id']}" if job.get("job_id") else job['link']
                
                msg = (
                    f"🎯 *MATCHING ROLE ({data['match_score']}%)*\n\n"
                    f"📌 *Role:* {job['title']}\n"
                    f"🏢 *Company:* {job['company']}\n"
                    f"📍 *Location:* {job['location']}\n"
                    f"🔑 *ATS Keywords:* `{', '.join(data.get('ats_keywords', []))}`\n\n"
                    f"📱 [Open in LinkedIn Mobile App]({app_link})\n"
                    f"🌐 [Open in Web Browser]({job['link']})\n\n"
                    f"📝 *Cover Letter:*\n`{data['cover_letter']}`\n\n"
                    f"📎 *Tailored Word CV attached below:* 👇"
                )
                
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
                
                # വേർഡ് ഫയൽ (.docx) ഉണ്ടാക്കി അയക്കുന്നു
                filename = f"Eby_Benjamin_{job['company'].replace(' ', '_')[:12]}.docx"
                doc_path = generate_word_cv(job['title'], job['company'], data, filename=filename)
                
                with open(doc_path, 'rb') as doc_file:
                    await bot.send_document(chat_id=TELEGRAM_CHAT_ID, document=doc_file, caption=f"📄 Tailored ATS CV for {job['title']}")
                
                if os.path.exists(doc_path):
                    os.remove(doc_path)

                await asyncio.sleep(4)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_live_agent())
