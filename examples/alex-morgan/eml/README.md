# Demo mails

Fictional `.eml` files for the `job-inbox` demo and for the tests of `tools/mail-fetch` and `tools/job-filter`. Each one copies the **structure** of a real mail (headers, MIME layout, HTML shape, link and forward formats, and the quirks below), but every company, person, job ID and token is made up. Job IDs start with `99000`. Tokens such as `midToken` and `otpToken` keep their real names but have fake values, so the tests can check that they are stripped. Every message carries an `X-Fixture` header.

The folder is named `eml/`, not `mail/`, because the pre-commit hook blocks any `mail/` folder.

Import them with `mail-fetch --import examples/alex-morgan/eml`. Alex's mailbox for the job search is `alexmorgan.jobs@example.com`. The forwarded mails come from Alex's personal address.

| File | Type | What it tests |
|---|---|---|
| `01-linkedin-alert.eml` | alert | LinkedIn job alert with 7 postings, one per filter outcome (below). The work mode ("Portugal (Remote)") appears only in the HTML. |
| `02-linkedin-alert-fwd-inline-roundcube.eml` | alert | Inline forward from Roundcube with a Spanish UI (`-------- Mensaje Original --------`, `Asunto/Fecha/De/Destinatario`). The original date has no time zone. The plain part uses `[n]` link markers. One posting duplicates `01`. |
| `03-linkedin-recommendations-fwd-inline-gmail.eml` | alert | Inline forward from Gmail (`---------- Forwarded message ---------`) with a note from Alex above it (`user_note`). The original sender, `jobs-noreply@linkedin.com`, also sends application updates (`09`, `10`), so the sender alone does not decide the type. |
| `04-linkedin-alert-fwd-attachment.eml` | alert | Forwarded as an attachment (`message/rfc822`), with a note and a signature in the outer message. |
| `05-tecnoempleo-alert.eml` | alert | Spanish portal. The posting link is a `tracking.php?cid=<JWT>` whose payload holds the destination (`dest`) and a session token (`inner_jwt`). Attributes use single quotes. The plain part is mostly CSS, with no titles or links. |
| `06-experteer-alert.eml` | alert | Every link is an opaque redirect (`nrd.php?p=…`) that cannot be resolved without a request. The salaries (`> 60.000 €`) are the portal's **estimates**, not published salaries. |
| `07-recruiter-inmail.eml` | message | Complete InMail from an agency: hidden end client, freelance/B2B with a day rate. It asks for a CV, a phone number and a rate. |
| `08-message-notification-truncated.eml` | message | "Daniel just messaged you" with no text at all: `truncated`, so it needs the full message before any draft. |
| `09-application-sent.eml` | update | LinkedIn "application was sent" for Kestrel Analytics, which has no row in `applications.md` (Easy Apply outside `cv-tailor`). It also contains job cards that are not an alert. |
| `10-application-viewed.eml` | update | "Tidewater Systems viewed your application". The plain part has only the footer: the content is only in the HTML. The row status is `?`, so it becomes `sent`. |
| `11-rejection.eml` | update | SmartRecruiters rejection from Corvane Robotics, with the reason (Kafka, a gap in `profile/gaps.md`). The plain part contains literal `&nbsp;`. |
| `12-interview-invitation.eml` | update | Personio invitation from Halcyon Labs: HTML only, no plain part, with a booking link and no date yet. |
| `13-interview-confirmation.eml` | update | Halcyon Labs interview confirmation from Outlook: `windows-1252`, a Teams link with its passcode, an Ashby reschedule link and a `text/calendar` invite with the date. |
| `14-irrelevant-newsletter.eml` | irrelevant | A LinkedIn newsletter about job hunting: on topic, but not an offer. |
| `15-irrelevant-invitation-accepted.eml` | irrelevant | A connection request was accepted. |
| `16-suspicious-injection.eml` | message, suspicious | A fake offer from a look-alike domain: no interview, asks for the passport, the IBAN and a deposit, WhatsApp only, a 24 h deadline. Text hidden in the HTML (and visible at the end of the plain part) tells AI assistants to send the profile and `.env` away. It must be reported, never acted on. |

## Expected stage 1 filter outcomes

Against [`../jobs/criteria.md`](../jobs/criteria.md) and [`../applications.md`](../applications.md). [`../jobs/extracted/`](../jobs/extracted/) holds the postings of each alert as the model should extract and normalize them (one `<mail-id>.json` per alert), and the tests of `tools/job-filter` check these outcomes on them, filtering the mails oldest first. A posting with no seniority in its title is `maybe`, not `pass`: the seniority rule cannot be checked, and missing data never rejects.

| Posting | Mail | Expected |
|---|---|---|
| Tessera Health, Senior Data Platform Engineer (9900000101) | 01 | `duplicate`: already applied |
| Tessera Health, Staff Data Engineer (9900000107) | 01 | `repost`: same company as an application, different ID |
| Ardent Robotics, Junior Python Developer | 01 | `reject` · `title_exclude` |
| Saltmarsh Mobility, Senior Backend Engineer (Python), Berlin on-site | 01 | `reject` · `location` |
| Veridian Ledger, Senior Python Engineer, €55K–62K remote | 01 | `reject` · `salary_floor` |
| Kestrel Analytics, Python Engineer, Data Platform | 01 | `maybe`: no seniority (in `02` it is a `duplicate`) |
| Lumen & Hale Consulting, Senior Data Engineer, Lisbon, no work mode | 01 | `maybe` |
| Copperline Pay, Backend Engineer, Payments, Porto hybrid | 02 | `maybe`: no seniority |
| Northwind Grid, Senior Software Engineer, Data Infrastructure, EMEA remote, €80K–95K | 02 | `pass` |
| Pinecrest Labs and Harbor & Vine, no work mode | 03 | `maybe` |
| Moonrise Data, Sales Engineer | 03 | `reject` · `role_family` (`sales`; the title also matches `title_exclude`, but the first rule wins) |
| Glasshouse Studio, Platform Engineer, EU remote | 04 | `maybe`: no seniority |
| Brindle Retail, Senior Data Analyst | 04 | `reject` · `role_family` |
| Ostrava Freight, Lead Python Engineer, Spain remote | 04 | `reject` · `location` |
| Tecnoempleo postings, remote in Spain | 05 | `reject` · `location`, or `title_exclude` for the junior one |
| Experteer postings | 06 | `maybe`: no work mode, no company and no ID (keyed by title and city); the salaries are estimates, so they are not used |
