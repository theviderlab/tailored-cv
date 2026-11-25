---
# Stage 1 filter rules, applied by tools/job-filter to the postings found in job alerts.
# The job-inbox skill fills them in with you on the first run and later proposes changes
# as diffs to this block; it never changes them without your confirmation.
# Missing data never rejects a posting: a rule that lacks its field lets the posting through as "maybe".
filter:
  role_families:
    include: []        # families you want, e.g. [ai-engineering, backend-python]
    exclude: []        # families you never want, e.g. [sales, support]
    definitions: {}    # family: "titles and keywords that belong to it" (guides how postings are classified)
  title_exclude: []    # whole words in any language, e.g. [junior, intern, prácticas, becario]
  seniority:
    exclude: []        # any of: intern, junior, mid, senior, lead, director, vp
  remote:
    countries: []      # accepted for remote roles: ISO codes (ES, PT) or regions (EU, EMEA, EUROPE, WORLD)
  onsite:
    cities: []         # accepted for hybrid and on-site roles
  salary_floor:        # yearly gross; only for published salaries on employee contracts
    annualize: {month: 14, day: 220, hour: 1760}   # factors to turn a monthly/daily/hourly figure into a year
    remote: {}         # per currency, e.g. {EUR: 60000}
    hybrid: {}
    onsite: {}
  company_blocklist: []
max_detailed: 15       # postings analysed in detail per run; the rest wait for the next run
---

# Job search criteria

## What I'm looking for

<!-- The kind of role, work, team and company you want, in your own words. job-inbox uses it to judge role fit. -->

## Stage 2 criteria

<!-- What only the full posting shows and the rules above cannot express, e.g.
"Consultancy with a hidden end client: apply with reservations". -->

## Extra domains

<!-- Portal or ATS domains, besides the built-in ones, whose posting pages job-inbox may fetch,
and extra sender hints for sorting mail, e.g. "alerts@jobs.example.com: job alerts". -->
