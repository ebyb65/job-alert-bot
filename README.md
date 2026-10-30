# Job Alert Bot

Automated daily HR job search and ATS matching for Eby Benjamin.

## What it does

- Searches recent LinkedIn public job listings with focus on HR Operations, HR Executive, HR Officer, HR Administration, Workforce Administration, Employee Services and Personnel roles.
- Prioritizes Dammam, Khobar, Dhahran, Jubail and the Eastern Province, then broadens to Saudi Arabia.
- Retrieves the job description when available.
- Performs a lightweight pre-filter before using AI.
- Scores each vacancy against a factual candidate profile.
- Explicitly treats unsupported requirements as gaps instead of inventing experience.
- Sends strong matches to Telegram with fit score, reasoning, ATS keywords, identified gaps and application link.
- Generates an ATS-friendly Word CV and short cover letter for high-confidence matches.
- Remembers previously processed LinkedIn job IDs for 30 days so the same vacancy is not repeatedly sent.
- Runs daily through GitHub Actions independently of ChatGPT.

## Required GitHub secrets

Add these under **Settings > Secrets and variables > Actions**:

- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository variable:

- `GEMINI_MODEL` — defaults to `gemini-2.5-flash`

## Schedule

The workflow runs every day at **09:17 Asia/Riyadh**. It intentionally avoids the top of the hour because scheduled GitHub Actions can experience more queue pressure then.

You can also run it manually from **Actions > Daily HR Job Search > Run workflow**.

## Important limitations

The bot discovers and evaluates jobs; it does not automatically submit applications or log in to LinkedIn. LinkedIn's public guest endpoints can change or throttle automated access, so a failed search should be treated as a source/API problem rather than evidence that no jobs exist.

The AI is instructed to use only facts in `candidate_profile.json`. Keep that file accurate whenever your experience, contact information, systems knowledge, location preferences or target roles change.

## Persistence

`sent_jobs.json` is updated by the workflow and committed back to the repository. This makes duplicate prevention survive fresh GitHub-hosted runners.
