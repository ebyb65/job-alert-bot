# Job Alert Bot

Automated daily HR job discovery, CV matching and ATS tailoring for Eby Benjamin.

## Sources

The bot now uses a source-adapter architecture and searches these public job sources when accessible:

- LinkedIn
- Indeed Saudi Arabia
- Naukrigulf
- Bayt
- GulfTalent

Sources fail independently. If one site changes markup, throttles or blocks automated public access, the other sources continue. The code deliberately does not bypass CAPTCHAs, authentication or anti-bot controls.

## What it does

- Searches HR Operations, Senior HR Executive, HR Specialist/Officer, HR Administration, Workforce/Personnel Administration and Employee Services roles.
- Prioritizes Dammam, Khobar, Dhahran, Jubail and Eastern Province, then Saudi Arabia more broadly.
- Normalizes vacancies from different boards into one format and deduplicates overlapping listings.
- Uses full job-description text when publicly retrievable.
- Filters Tamheer, internships, graduate-trainee and explicit Saudi-national-only vacancies.
- Performs a lightweight relevance filter before spending an AI request.
- Scores each vacancy against `candidate_profile.json`, which contains verified CV facts only.
- Treats unsupported requirements as gaps rather than inventing experience.
- Classifies matches as Priority Apply (85+), Strong Match (75-84), Review (65-74), or Low Match.
- Sends high-confidence matches to Telegram with source, score, reasoning, gaps, ATS keywords and direct application link.
- Generates an ATS-friendly Word CV and short cover letter for strong matches.
- Persists processed job identifiers for 30 days to reduce duplicate alerts.
- Runs daily through GitHub Actions independently of ChatGPT.

## Required GitHub secrets

Add under **Settings > Secrets and variables > Actions**:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository variable:

- `GEMINI_MODEL` — defaults to `gemini-2.5-flash`

## Configuration

The workflow sets:

- `JOB_SOURCES=linkedin,indeed,naukrigulf,bayt,gulftalent`
- `MIN_MATCH_SCORE=78`
- `HISTORY_LOOKBACK_DAYS=30`
- `MAX_JOBS=50`

These can be changed in `.github/workflows/daily_run.yml`.

## Schedule

The workflow runs every day at **09:17 Asia/Riyadh** and can also be launched manually from **Actions > Daily HR Job Search > Run workflow**.

## Important limitations

This project discovers, ranks and prepares applications; it does not log into job-board accounts or automatically submit applications. Job boards can change public markup, URLs or access rules at any time. Source adapters are defensive and fail closed rather than trying to evade access controls.

Indeed in particular may restrict automated access. Its adapter only uses publicly accessible responses and will simply return no results if access is denied. For long-term reliability, direct employer career feeds/APIs should be added where available.

The AI must use only facts in `candidate_profile.json`. Keep that file accurate whenever experience, contact details, systems knowledge, preferred locations or target roles change.

## Persistence

`sent_jobs.json` is updated by the workflow and committed back to the repository, allowing duplicate prevention to survive fresh GitHub-hosted runners.
