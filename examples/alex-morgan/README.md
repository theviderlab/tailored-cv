# Demo workspace: Alex Morgan

A complete, **fictional** workspace that shows what tailored-cv produces. Alex Morgan, Fieldstone Analytics, Larkspur Logistics and every other name, number and link here are made up.

It is a snapshot taken right after Alex tailored a CV to one posting: the profile already holds the answers Alex gave during that application.

## What's inside

| Path | What it shows |
|---|---|
| [`posting.md`](posting.md) | The job posting: Senior Python Engineer, Data Platform at Fieldstone Analytics. |
| [`profile/`](profile/) | The source of truth. Entries with `source: application fieldstone-analytics-…` were added from Alex's answers during this application (Kubernetes, SQS/SNS pipelines, Kafka as a gap, on-site days in Lisbon). |
| [`cv-base.md`](cv-base.md), [`cover-letter-base.md`](cover-letter-base.md) | The default CV and cover letter every application starts from. |
| [`output/fieldstone-analytics-senior-python-engineer/`](output/fieldstone-analytics-senior-python-engineer/) | The tailored CV and cover letter, as markdown and as the PDFs the build generates. |
| [`applications.md`](applications.md) | The application log. Only the Fieldstone output folder is included in this demo. |
| [`jobs/criteria.md`](jobs/criteria.md) | What Alex is looking for and the filter rules for job alerts (`job-inbox`). |
| [`eml/`](eml/) | Mails for the `job-inbox` demo: job alerts, recruiter messages, application updates, irrelevant mail and a suspicious one. |

Compare `cv-base.md` with the tailored CV to see what the agent changed: the headline, the summary, the skills (Kubernetes and event-driven pipelines added) and the order and wording of the Larkspur bullets. Every new fact traces back to a profile entry.

## Try it

Build the demo PDFs yourself from `cv/`:

```sh
npm run cv -- ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cv-fieldstone-analytics-senior-python-engineer.md
npm run cover -- ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cover-letter-fieldstone-analytics-senior-python-engineer.md ../examples/alex-morgan/output/fieldstone-analytics-senior-python-engineer/cv-fieldstone-analytics-senior-python-engineer.md
```

Or explore the whole flow with your agent: copy this folder to `workspace/` (`cp -r examples/alex-morgan workspace`) and ask it to tailor Alex's CV to another posting. When you are ready to use your own data, replace it with `workspace.example/`.
