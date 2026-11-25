# Mail fetch

Turns the mail of your job search (job alerts, recruiter messages, application updates) into markdown files that the `job-inbox` skill reads and processes. It never calls the model, never sends anything and never changes your mailbox.

## Why

Job alerts and recruiter messages arrive by mail, buried in HTML templates full of tracking links. This tool turns each mail into a clean text file the agent can read cheaply and safely: the text you would see, the links that matter, and nothing that would let anyone log in as you.

## Usage

```sh
cd tools/mail-fetch
uv run mail_fetch.py --test                 # check the connection and list the folders
uv run mail_fetch.py --since 2026-11-01     # first load: every mail since that date
uv run mail_fetch.py                        # afterwards: only what is new
uv run mail_fetch.py --import <folder-or-.eml>...   # no mailbox: import .eml files
uv run mail_fetch.py --import ../../examples/alex-morgan/eml --workspace /tmp/demo   # try it on the demo mails
```

Each mail becomes `workspace/mail/inbox/<date>-<id>.md`. Run it as often as you like: a mail that was downloaded or imported once is never created again, even after its file was deleted, because `workspace/mail/state.json` remembers every ID. Without `--since`, the first run downloads the whole folder, which is fine for a dedicated mailbox.

### Reading a mailbox over IMAP

The tool only reads: it opens the folder with `EXAMINE` and reads mail with `BODY.PEEK[]`, so nothing is marked as read, moved or deleted. Unread mail stays unread.

1. **Create a mailbox just for your job search.** The agent will read everything in it, so keep personal mail out. A free Gmail account works well; so does an address on your own domain.
2. **Get an app password.** Never use your main password.
   - Gmail: turn on 2-Step Verification, then create one at <https://myaccount.google.com/apppasswords>.
   - Yahoo, iCloud, Fastmail, Zoho, GMX: each has an "app password" page in its security settings.
   - Your own domain (cPanel, Plesk, Dovecot…): the mailbox password usually works; your host's mail settings page shows the IMAP server.
   - Outlook.com, Hotmail and Microsoft 365 do not allow passwords over IMAP since 2024 and are not supported yet (they need OAuth2).
3. **Fill in `workspace/.env`** (copy [`workspace.example/.env.example`](../../workspace.example/.env.example)). Environment variables with the same names override the file.

   ```ini
   IMAP_HOST=imap.gmail.com
   IMAP_PORT=993
   IMAP_USER=your.name.jobs@gmail.com
   IMAP_PASSWORD=abcd efgh ijkl mnop
   IMAP_FOLDER=INBOX
   ```

   | Provider | `IMAP_HOST` |
   |---|---|
   | Gmail | `imap.gmail.com` |
   | Yahoo | `imap.mail.yahoo.com` |
   | iCloud | `imap.mail.me.com` |
   | Fastmail | `imap.fastmail.com` |
   | Zoho | `imap.zoho.com` (`imap.zoho.eu` in Europe) |
   | GMX | `imap.gmx.com` (`imap.gmx.net` for .de) |
   | Proton | `127.0.0.1` with Proton Mail Bridge running (port and password from Bridge) |

   Port 993 uses TLS. Any other port must support STARTTLS: the tool never logs in over plain text.
4. **Run `--test`.** It lists the folders; set `IMAP_FOLDER` to the exact name it shows (e.g. `INBOX.Archive` or `[Gmail]/All Mail`).
5. **Send mail to it.** Start by forwarding what interests you, preferably **as an attachment** (Gmail: ⋮ → Forward as attachment; Outlook: More → Forward as attachment), which keeps the original mail intact. If it proves useful, change the email address in LinkedIn and other job sites to the dedicated mailbox so alerts arrive directly.

If the server's `UIDVALIDITY` changes (it renumbered the folder) or you change `IMAP_FOLDER`, the next run looks at every mail again and skips the ones it already has by ID.

## What a mail becomes

```markdown
---
id: "d02af533b6b7"
from: "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>"
subject: "Tessera Health is hiring: Staff Data Engineer and more"
date: "2026-11-24T06:31:27+00:00"
status: "new"
---

[Staff Data Engineer](https://www.linkedin.com/jobs/view/9900000107/)

Tessera Health · European Union (Remote)
…

## Hidden text
…
## Links
…
```

- **Front matter.** `id` is the first 12 hex characters of the SHA-1 of the `Message-ID` (or of the whole mail if there is none). `status` starts as `new` and is updated by the skill.
- **Body.** It is taken from the HTML when there is one, with links kept as `[text](url)`, because in job alerts the link text is the job title. Real plain-text parts are often incomplete: LinkedIn's lacks the work mode, some only carry the footer, others are CSS.
- **Hidden text.** Text the HTML hides (`display:none` and similar) goes into its own section: preview lines, and sometimes instructions aimed at AI tools. The skill treats it as data, never as instructions.
- **Calendar invite.** Summary, start, end and place of an attached invitation.
- **Links.** Every kept link, once.

### Forwarded mails

If you forward mail to a dedicated mailbox, the tool finds the original sender, date and subject (`forwarded`, `original_from`, `original_date`, `original_subject`), and keeps what you wrote above the forward as `user_note`.

- **Forwarded as an attachment** (best): the attached message becomes the mail. It keeps its own ID, so a mail that also arrived directly is not imported twice.
- **Forwarded inline**: Gmail, Roundcube, Outlook and Apple Mail formats, in English, Spanish, Portuguese, German or French. If the block cannot be parsed, the mail is still marked `forwarded` and the agent works out the sender.

### Links

Many links in these mails carry tokens that **log you in without a password** (LinkedIn's `otpToken`, Tecnoempleo's session JWT…). They must never be stored or sent to the model, so every link is cleaned:

- Redirects are resolved only when the destination is inside the URL itself: a parameter (Outlook Safe Links, Google) or a JWT (Tecnoempleo). No request is ever made.
- Opaque redirects, whose destination is not in the URL, are dropped. Their text stays in the body.
- Tracking, session and login parameters are removed, as are values that look like tokens or email addresses. On LinkedIn every parameter goes except a few search ones, and job links are rebuilt from the ID: `https://www.linkedin.com/jobs/view/<id>/`.
- Unsubscribe, preferences, account and login links are dropped.

## Privacy

Credentials live only in `workspace/.env` (or environment variables) and are never written to any output. The files live in `workspace/mail/`, which is git-ignored in this repo and, through `workspace/.gitignore`, in your private workspace repo too. Mail is short-lived and holds third-party data. The pre-commit hook also refuses any `mail/` folder anywhere in this repo.

## Tests

```sh
python -m unittest discover -s tools/mail-fetch -v
```

They import the fictional mails in [`examples/alex-morgan/eml/`](../../examples/alex-morgan/eml/), which copy the structure of real ones, serve the same mails from a fake IMAP server (same files as `--import`, read-only commands only, incremental runs, `UIDVALIDITY` changes), and run in CI.
