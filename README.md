# Job Alert Bot

Runs daily on GitHub Actions (`runner.py`) and sends matching HR / Admin vacancies in Saudi Arabia to Telegram.

## How a job gets to you
1. **Scrape** LinkedIn, Indeed, Naukrigulf, Bayt, GulfTalent (a blocked source is skipped for the rest of the run).
2. **Title + location gate.** The title must contain an HR/Admin word and none of the blocked words. The location must be in `local_locations` or `relocation_locations`.
3. **Full job description required.** Nothing is sent from a title alone.
4. **Description blockers** (Saudi-only, female-only, Tamheer, fresh graduates) and **salary floor**.
5. **Strict AI review.** The job must be a core HR/Admin/Mobilization role at the right seniority, with no blockers, scoring at least `minimum_match_score`.

If the AI is down, jobs are **not** sent. They are retried on the next run.

## Tuning (`search_preferences.json`)
| Setting | What it does |
|---|---|
| `search_queries` | What is searched on each job board |
| `title_must_match_any` / `title_reject_any` | Title allow-list / block-list (regex, whole words) |
| `description_reject_any` | Phrases in the description that disqualify a job |
| `minimum_match_score` | Raise to get fewer, tighter alerts |
| `max_alerts_per_run` | Daily cap on alerts |
| `send_unverified` | `true` to also get jobs whose description couldn't be read (noisier) |

The candidate profile used by the AI is `PROFILE` in `runner.py`. Update it when your CV changes.

`main.py` is the old version and is not run by the workflow.
