# Stories (cover letter arguments)

Reusable blocks. The base cover letter (`cover-letter-base.md`) is a combination of these. When tailoring a letter, the skill picks the ones that fit the posting and adjusts them.

## Retries that never double-count

At Larkspur, carriers resend the same tracking event when their systems time out. Alex designed the tracking pipeline so every event carries an ID that the consumer stores in the same transaction as the write and skips if seen. The pipeline now handles 3M events per day and retries never corrupt a shipment's history.

source: initial CV (2026-09-20)

## From hours to minutes

At Quillon Health, incidents were usually reported by clinics, hours after they started. Alex added OpenTelemetry tracing and Sentry alerts to the integration services, and the team started finding problems within minutes, before the clinics noticed.

source: initial CV (2026-09-20)

## Teaching as part of the job

Alex mentors engineers at work and coaches first-time speakers at the Porto Python Meetup. The same habit drove the design documents now required for every cross-team change at Larkspur.

source: initial CV (2026-09-20)
