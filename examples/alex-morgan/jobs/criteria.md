---
# Stage 1 filter rules, applied by tools/job-filter to the postings found in job alerts.
# The job-inbox skill fills them in with you on the first run and later proposes changes
# as diffs to this block; it never changes them without your confirmation.
# Missing data never rejects a posting: a rule that lacks its field lets the posting through as "maybe".
filter:
  role_families:
    include: [backend-python, data-platform, platform-engineering]
    exclude: [data-analytics, frontend, sales, support]
    definitions:
      backend-python: "Backend Engineer, Python Developer, Software Engineer (Python), Desarrollador/a Backend Python"
      data-platform: "Data Platform Engineer, Data Engineer, Data Infrastructure, Ingeniero/a de Datos"
      platform-engineering: "Platform Engineer, Kubernetes, infrastructure for Python services"
      data-analytics: "Data Analyst, BI, Analytics Engineer"
  title_exclude: [junior, intern, internship, trainee, estágio, estagiário, prácticas, becario, sales, presales]
  seniority:
    exclude: [intern, junior, director, vp]
  remote:
    countries: [PT, EU, EUROPE, EMEA, WORLD]
  onsite:
    cities: [Porto]
  salary_floor:
    annualize: {month: 14, day: 220, hour: 1760}
    remote: {EUR: 65000}
    hybrid: {EUR: 70000}
    onsite: {EUR: 70000}
  company_blocklist: []
max_detailed: 15
---

# Job search criteria

## What I'm looking for

Senior backend or data platform roles where Python services and data pipelines are the core of the work, on a team that owns its platform end to end. Remote from Portugal, or hybrid in Porto.

## Stage 2 criteria

- Consultancy or agency placing engineers at a hidden end client: apply with reservations.
- Kafka as a hard requirement: a known gap (`profile/gaps.md`), and the reason Corvane Robotics turned Alex down.
- Freelance or B2B contracts: compare the day rate with the yearly expectation in `profile/facts.md`.

## Extra domains

None.
