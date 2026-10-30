import hashlib, json, re, urllib.parse
import requests
from bs4 import BeautifulSoup

HEADERS={"User-Agent":"Mozilla/5.0 Chrome/124 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}

def clean(x): return re.sub(r"\s+"," ",BeautifulSoup(x or "","html.parser").get_text(" ")).strip()
def make_job(source,title,company,location,link,description="",posted=""):
    link=(link or "").split("#")[0]
    return {"source":source,"title":clean(title),"company":clean(company) or "Company Not Listed","location":clean(location),"link":link,"description":clean(description),"posted":clean(posted),"history_id":source+":"+hashlib.sha256(link.encode()).hexdigest()[:18]}
def get(url):
    r=requests.get(url,headers=HEADERS,timeout=18); r.raise_for_status(); return r.text

def walk_json(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from walk_json(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk_json(v)

def jsonld(html,source,base):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for tag in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(tag.string or tag.get_text())
        except Exception: continue
        for obj in walk_json(data):
            typ=obj.get("@type")
            if typ!="JobPosting" and not (isinstance(typ,list) and "JobPosting" in typ): continue
            org=obj.get("hiringOrganization") or {}; jl=obj.get("jobLocation") or {}
            if isinstance(jl,list): jl=jl[0] if jl else {}
            addr=jl.get("address",{}) if isinstance(jl,dict) else {}
            loc=", ".join(str(addr.get(k,"")) for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))
            out.append(make_job(source,obj.get("title",""),org.get("name","") if isinstance(org,dict) else "",loc,obj.get("url") or base,obj.get("description",""),obj.get("datePosted","")))
    return out

def fetch_description(url):
    if not url: return ""
    try: html=get(url); soup=BeautifulSoup(html,"html.parser")
    except Exception as e: print("JD:",e); return ""
    jobs=jsonld(html,"Direct",url)
    if jobs and jobs[0].get("description"): return jobs[0]["description"]
    for sel in (".show-more-less-html__markup",".description__text","[data-automation-id='jobPostingDescription']","#jobDescriptionText",".job-description",".jobDescription","article"):
        node=soup.select_one(sel)
        if node and len(clean(str(node)))>=250: return clean(str(node))
    meta=soup.find("meta",attrs={"name":"description"})
    return clean(meta.get("content","")) if meta else ""

def linkedin(q,loc):
    url="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords="+urllib.parse.quote(q)+"&location="+urllib.parse.quote(loc)+"&f_TPR=r604800&start=0"
    try: soup=BeautifulSoup(get(url),"html.parser")
    except Exception as e: print("LinkedIn:",e); return []
    out=[]
    for c in soup.find_all("li"):
        t=c.find("h3",class_="base-search-card__title"); a=c.find("a",class_="base-card__full-link"); co=c.find("h4",class_="base-search-card__subtitle"); l=c.find("span",class_="job-search-card__location")
        if t and a: out.append(make_job("LinkedIn",t.get_text(),co.get_text() if co else "",l.get_text() if l else loc,a.get("href","").split("?")[0]))
    return out

def generic(source,url,loc):
    try: return jsonld(get(url),source,url)
    except Exception as e: print(source+":",e); return []
def indeed(q,loc): return generic("Indeed","https://sa.indeed.com/jobs?q="+urllib.parse.quote(q)+"&l="+urllib.parse.quote(loc)+"&fromage=7",loc)
def naukrigulf(q,loc): return generic("Naukrigulf","https://www.naukrigulf.com/jobs?k="+urllib.parse.quote(q)+"&l="+urllib.parse.quote(loc),loc)
def bayt(q,loc): return generic("Bayt","https://www.bayt.com/en/saudi-arabia/jobs/?q="+urllib.parse.quote(q),loc)
def gulftalent(q,loc): return generic("GulfTalent","https://www.gulftalent.com/saudi-arabia/jobs?keywords="+urllib.parse.quote(q),loc)
SOURCES={"linkedin":linkedin,"indeed":indeed,"naukrigulf":naukrigulf,"bayt":bayt,"gulftalent":gulftalent}

def fetch_all(prefs,limit=50):
    out=[]; seen=set()
    for q in prefs["target_roles"][:15]:
      for loc in prefs["preferred_locations"][:6]:
       for name,fn in SOURCES.items():
        for j in fn(q,loc):
            text=(j["title"]+" "+j.get("description","")).lower()
            if any(x in text for x in ("tamheer","internship","saudi nationals only","saudi national only")): continue
            key=(re.sub(r"\W+"," ",j["title"].lower()).strip(),re.sub(r"\W+"," ",j["company"].lower()).strip(),re.sub(r"\W+"," ",j["location"].lower()).strip())
            if key in seen: continue
            seen.add(key); out.append(j)
            if len(out)>=limit: return out
    return out
