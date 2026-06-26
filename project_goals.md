# TRACE — Project Goals (Iteration: Email Submission + Broadcast + Wording + Magic-Link + Object Storage)

> **Audience:** This document is a build spec for Claude Code. It is intended to be executed autonomously against the existing TRACE codebase. Read sections 0 and 0.5 in full before writing any code — section 0.5 documents the existing system that must not be broken.
>
> **Style:** Match the existing Tailwind UI conventions exactly — dark sidebar, Inter font, cyan/purple accents, rounded-2xl cards, slate neutrals, mobile responsive at `xl` (1280px) breakpoint.
>
> **Do not** rewrite existing functionality unless this document explicitly says to. Reuse existing models, views, templates, and helpers wherever possible. **Extend, don't replace.**

---

## 0. Scope of This Iteration

There are six pillars to this iteration. They must all be completed.

1. **Student Email Submission for Lost Items** — completing and hardening the IMAP-based student lost-item submission flow so it works end-to-end against a single configured mailbox (initially `raadvait@tisb.ac.in`). The existing `check_emails` command and `StudentLostItem` model are the foundation; this iteration finishes the loop.
2. **Broadcast to School Body** — a Super-User-controlled action on each approved student lost item (and optionally on found items) that sends a formatted email to a configured list of school recipients (initially `raadvait@tisb.ac.in`, `nsiddharth@tisb.ac.in`).
3. **Precise Wording Overhaul** — a full audit and rewrite of every user-facing string so that no claim, collection, submission, or disclaimer wording can be exploited or reinterpreted by a bad-faith student.
4. **Per-Student "My Reports" via Email Magic Link** — a passwordless self-service page where any TISB student can see the lost reports they have submitted and the claims they have made, signed in via a one-time email link.
5. **Object Storage for Media (S3 / Cloudflare R2)** — move uploaded images off Railway's ephemeral disk onto an S3-compatible bucket so deploys do not destroy uploads. Keep a clean local-disk fallback for development.
6. **Staff User Management UI** — a dedicated Super-User-only page at `/staff/users/` that replaces the cluttered Django admin User editor with a clean, focused Tailwind UI for creating staff users, promoting/demoting between Admin and Super User, deactivating accounts, resetting passwords, and viewing a full audit log of role changes. Hard safeguards prevent accidental lockout.

Everything below is mandatory unless prefixed with **OPTIONAL**.

---

## 0.5 Current System Foundation (do not break)

This section documents what already exists in the repo. Claude Code must preserve all of it and integrate the new work on top.

### 0.5.1 Tech Stack (already in place)

- Django 4.2 (Python), Gunicorn for WSGI in prod.
- SQLite in dev, PostgreSQL in prod (via `dj-database-url`, with SSL when `DATABASE_URL` is set).
- Django templates + Tailwind CSS via CDN + vanilla JS + Inter font (Google Fonts).
- Google **Gemini 2.5 Flash** Vision API for image analysis (`inventory/services.py`); a commented-out OpenAI GPT-4.1-mini fallback exists in the same file.
- Pillow + pillow-heif for HEIC→JPEG server-side conversion (via a `pre_save` Django signal on `ItemImage`); heic2any.js for client-side preview.
- Django SMTP for outbound email, IMAP for inbound (`check_emails` management command). **Authentication is OAuth2 / XOAUTH2 against Microsoft 365** (§1.9) — basic auth is not viable. `msal` and `cryptography` are required Python deps for this.
- WhiteNoise compressed manifest storage for static files.
- Deployed to Railway. Auto-detects Railway via `DATABASE_URL` / `RAILWAY_ENVIRONMENT` / `RAILWAY_PUBLIC_DOMAIN`.

### 0.5.2 Repository Layout (already in place)

```
LostAndFoundSystem/
├── manage.py
├── requirements.txt
├── db.sqlite3
├── lost_and_found_project/        # Project config: settings.py, urls.py, wsgi.py, asgi.py
├── inventory/                     # The only app
│   ├── models.py
│   ├── views.py
│   ├── urls.py                    # namespace="inventory"
│   ├── forms.py
│   ├── admin.py                   # Custom SuperUserOnlyAdminSite
│   ├── services.py                # Gemini Vision integration
│   ├── signals.py                 # HEIC→JPEG pre_save signal
│   ├── apps.py                    # Registers custom User admin in ready()
│   ├── context_processors.py      # Adds is_super_user to all templates
│   ├── management/commands/
│   │   ├── check_emails.py
│   │   └── promote_superuser.py
│   ├── tests/                     # test_models, test_views, test_forms, test_vision
│   └── migrations/                # 0001 through 0010
├── templates/
│   ├── base.html                  # Legacy Bootstrap base (leave as-is)
│   ├── registration/login.html    # Tailwind-styled
│   └── inventory/                 # All other Tailwind templates
├── staticfiles/
├── media/
└── venv/
```

### 0.5.3 Existing Models (do not break their fields or behavior)

| Model | Key fields | Notes |
|---|---|---|
| `UserProfile` | `user` (OneToOne to AUTH_USER_MODEL) | Minimal; roles use Django's `is_staff` / `is_superuser`. |
| `Item` | `title`, `description`, `location_found`, `date_found`, `status` (FOUND/CLAIMED), `category` (7 choices), `approval_status` (PENDING/APPROVED/REJECTED), `item_type` (SENIOR/PY), `created_by` (FK User), `claimed_by_name`, `claimed_at`, `created_at`, `updated_at` | Indexes on `status`, `date_found`, `category`, `approval_status`, `item_type`, and composite `(approval_status, item_type)`. Default ordering `-date_found, -created_at`. Properties: `claim_count`, `latest_claim`. **This iteration will add `approved_by`, `approved_at`, `rejection_reason` — see §2.10.** |
| `Claim` | `item` (FK Item), `claimant_name`, `claimant_email`, `claimed_at` | Multiple claims per item allowed. Index on `(item, -claimed_at)`. |
| `ItemImage` | `item` (FK), `image` (→ `item_images/`), `created_at` | HEIC pre_save signal applies here. |
| `StudentLostItem` | `title`, `description`, `email_subject`, `email_from`, `submitted_at`, `approval_status` (PENDING/APPROVED/REJECTED), `approved_by` (FK User), `approved_at` | Email-sourced. |
| `StudentLostItemImage` | `student_lost_item` (FK), `image` (→ `student_item_images/`), `created_at` | |

**Category choices on `Item` (7):** `Electronics`, `Bags and Carry`, `Sports and Clothing`, `Bottles and Containers`, `Documents and IDs`, `Notebooks/Books`, `Other/Misc`.

**Migration count:** 10 migrations exist (0001–0010). New migrations in this iteration start at 0011.

### 0.5.4 Roles & Permissions (do not break)

- **Public users:** browse landing, Senior Years, Primary Years, Students' Lost Items; view item detail; claim items (name + `@tisb.ac.in` email).
- **Admin (`is_staff=True`, `is_superuser=False`):** all public actions + upload items (PENDING) + Admin Dashboard. Cannot access Django admin, cannot approve.
- **Super User (`is_superuser=True`):** everything; uploads auto-APPROVED; access Approval Queue; access Django admin (replaced with `SuperUserOnlyAdminSite`); manage user roles (**now via the new `/staff/users/` UI in §6, not Django admin**).

**Helpers that exist and must be reused:** `is_super_user(user)`, `is_admin(user)`, `SuperUserRequiredMixin`, `AdminOrSuperUserRequiredMixin`, `StaffRequiredMixin`. Do not invent new ones if an existing one fits.

**Note on user management workflow change:** previously, granting and revoking staff access was done through Django admin's User editor. This iteration introduces a dedicated UI at `/staff/users/` (§6) that becomes the official path. Django admin User editing remains accessible as a fallback but should not be the primary workflow.

### 0.5.5 Existing URL Routes (namespace `inventory`)

| URL | View | Access |
|---|---|---|
| `/` | `LandingPageView` | Public |
| `/browse/` | `ItemListView` | Public (Senior Years) |
| `/primary-years/` | `PrimaryYearsListView` | Public |
| `/students-lost-items/` | `StudentLostItemsListView` | Public |
| `/items/<pk>/` | `ItemDetailView` | Public |
| `/items/<pk>/claim/` | `ClaimItemView` | Public POST |
| `/student-items/<pk>/` | `StudentLostItemDetailView` | Public |
| `/staff/items/upload/` | `ItemUploadView` | Staff |
| `/staff/items/analyze/` | `analyze_images_ajax` | Staff AJAX |
| `/staff/dashboard/` | `AdminDashboardView` | Staff |
| `/staff/approval-queue/` | `ApprovalQueueView` | Super User |
| `/staff/approve/<type>/<id>/` | `ApproveItemView` | Super User |
| `/staff/reject/<type>/<id>/` | `RejectItemView` | Super User |
| `/admin/` | Django admin | Super User |
| `/accounts/...` | Django auth | — |

### 0.5.6 Existing Key Features (do not break)

- **Multi-image upload (up to 3)** on found items with **AI auto-fill** (Gemini Vision returns `title`, `description`, `category`; category normalized to model choices; category-specific prompt rules — e.g., TISB notebooks → color, name, class/section, subject only).
- **Multi-image carousel** on browse cards (prev/next arrows + dot indicators) and full gallery on detail page (thumbnails + arrows + counter + arrow-key navigation).
- **Multi-claim system:** any number of claims per item, each its own `Claim` row. Claimed items stay visible (reduced opacity) and auto-hide after a category-specific window: Electronics 7 days, Sports & Clothing 3 days, others 1 day. Claimant gets a confirmation email.
- **Approval workflow:** Admin uploads → PENDING; Super User uploads → AUTO-APPROVED; student email submissions → PENDING. Single Approval Queue shows both pending types.
- **Email submissions:** `check_emails` IMAP poller (already exists; will be hardened in §1) creates `StudentLostItem` entries from `@tisb.ac.in` senders, dedupes by `Message-ID`, sends acknowledgment.
- **HEIC handling:** `pre_save` signal on `ItemImage` converts HEIC→JPEG using pillow-heif. The same conversion must be applied to `StudentLostItemImage` (verify and extend if missing).
- **Admin Dashboard:** table of ALL items with serial #, date found, name, preview, status, claimed by, actions; rows with multiple claims highlighted yellow; "View All" claimants modal; delete confirmation modal; recent-claim notification banners (last 7 days, dismissible per session, persisted in session storage); fullscreen image modal.
- **Async email sending** in a background thread to avoid blocking; fails silently if email is not configured.
- **Mobile responsive** with hamburger slide-out sidebar at `xl` breakpoint.
- **Custom Super-User-only Django admin** (`SuperUserOnlyAdminSite`); User admin registered in `apps.py:ready()` to avoid `AlreadyRegistered`.

### 0.5.7 Existing Env Vars (keep all of these working)

`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `LF_EMAIL_ADDRESS`, `LF_EMAIL_PASSWORD`, `LF_IMAP_HOST`, `LF_IMAP_PORT`, `LF_IMAP_MAILBOX`, `LF_ALLOWED_SENDER_DOMAIN`, `GOOGLE_API_KEY`, `CREATE_SUPERUSER`, `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`, `RAILWAY_PUBLIC_DOMAIN`.

This iteration adds: `LF_EMAIL_DISPLAY_NAME`, `LF_BROADCAST_RECIPIENTS`, `MAGIC_LINK_SECRET`, `MAGIC_LINK_BASE_URL` (optional), `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_S3_CUSTOM_DOMAIN`, `MEDIA_BACKEND`, `MS_OAUTH_TENANT_ID`, `MS_OAUTH_CLIENT_ID`, `MS_OAUTH_CLIENT_SECRET`, `MS_OAUTH_SCOPES` (optional), `MS_OAUTH_REDIRECT_URI` (optional), `MS_OAUTH_AUTHORITY` (optional), `MS_OAUTH_TOKEN_ENCRYPTION_KEY`. See the relevant sections below.

### 0.5.8 Known Quirks (acknowledge, do not "fix" as a side quest)

- `templates/base.html` uses Bootstrap; all `inventory/` templates use Tailwind. The Bootstrap base is legacy; do not delete it, do not migrate it.
- `item_upload_confirm.html` and `ItemUploadConfirmView` exist but the confirmation flow is not clearly wired up in the main upload flow. Leave alone unless it directly conflicts with this iteration's work.
- No Procfile or Dockerfile is visible. Railway uses runtime detection. This iteration does not add one.
- No CI configuration is visible. Out of scope.

---

## 1. Student Email Submission Flow (Lost Items)

### 1.1 Mental Model

A student loses something. They send an email from their `@tisb.ac.in` address to the configured inbox. The system polls the inbox, parses the email, creates a `StudentLostItem` in `PENDING` status, sends them an acknowledgment, and shows it to Super Users in the existing approval queue. Super Users approve or reject. Approved items appear publicly on the "Students' Lost Items" tab and become eligible for the **Broadcast to School Body** action (see §2).

### 1.2 Email Account Configuration

- The inbox is configured via existing env vars: `LF_EMAIL_ADDRESS`, `LF_EMAIL_PASSWORD`, `LF_IMAP_HOST`, `LF_IMAP_PORT`, `LF_IMAP_MAILBOX`, `LF_ALLOWED_SENDER_DOMAIN`.
- For the initial deployment, `LF_EMAIL_ADDRESS=raadvait@tisb.ac.in` and `LF_ALLOWED_SENDER_DOMAIN=@tisb.ac.in`. `LF_IMAP_HOST=outlook.office365.com`, `LF_IMAP_PORT=993` (these are the Microsoft 365 defaults — see §1.9.1).
- **`LF_EMAIL_PASSWORD` is unused under OAuth2.** It can be set to an empty string or left unset. The mailbox is authenticated via OAuth2 (§1.9), not a password. The env var is retained only for backward compatibility with older code paths and for use against non-Microsoft test inboxes.
- Do **not** hardcode the address anywhere — always read from settings/env.
- Add a new optional env var `LF_EMAIL_DISPLAY_NAME` (default: `"TRACE Lost & Found"`). When set, all outgoing emails sent on behalf of the inbox must use `LF_EMAIL_DISPLAY_NAME <LF_EMAIL_ADDRESS>` as the `From` header. If `EMAIL_HOST_USER` is configured separately for SMTP, prefer `LF_EMAIL_ADDRESS` as the visible From, falling back to `DEFAULT_FROM_EMAIL`.
- **All authentication is via OAuth2 / XOAUTH2 — see §1.9 for the required setup.** Basic auth (`EMAIL_HOST_PASSWORD`-based) will not work against TISB's Microsoft 365 tenant and will fail at the SMTP `AUTH` step with `535 5.7.139 Authentication unsuccessful, basic authentication is disabled`. There is no workaround other than implementing §1.9.

### 1.3 Email Parsing Rules (extend `check_emails`)

The existing `inventory/management/commands/check_emails.py` already fetches unseen emails and creates `StudentLostItem` records. Audit it against the following rules and fix any gap.

#### 1.3.1 Sender Validation

- Only accept emails where the `From` email address ends with `LF_ALLOWED_SENDER_DOMAIN` (case-insensitive). If not, mark the email as seen and skip silently (no acknowledgment, no DB write). Log at `INFO` level: `"Skipped email from non-TISB sender: {addr}"`.
- Reject emails where the `From` header cannot be parsed — log at `WARNING`, do not write to DB, do not mark as seen (so a human can inspect later).

#### 1.3.2 Subject → Title

- The subject line, stripped of `Re:`, `Fwd:`, `FW:`, `RE:`, `FWD:` (case-insensitive, repeated) becomes `StudentLostItem.title`.
- If the stripped subject is empty, set the title to: `"Untitled lost item submission"` and add a flag (see §1.3.7) requesting a human edit before approval.
- Truncate the title at 200 characters. If truncated, append `…` and log at `INFO`.

#### 1.3.3 Body → Description

- Prefer `text/plain` parts. If none, fall back to `text/html` and strip tags (use `bleach` or a minimal regex — if adding a dependency, prefer `bleach`).
- Strip quoted reply history (lines starting with `>`, plus standard `"On <date>, <person> wrote:"` blocks) before storing.
- Strip the student's email signature when it is detectable (lines after `-- ` per RFC 3676; lines starting with `Sent from my iPhone` / `Sent from my Android`; common school-templated signatures). Be conservative: when in doubt, keep the content.
- Trim leading/trailing whitespace.
- If the body is empty after stripping, set description to: `"No description was provided by the student in the email body."` (verbatim, see §3 for the wording principle).
- Maximum stored length: 5000 characters. If exceeded, truncate and append `\n\n[Description truncated — original email body exceeded 5000 characters.]`.

#### 1.3.4 Attachments → Images

- Iterate all attachments. Accept files where the MIME type is `image/*` **or** the filename extension is in: `.jpg, .jpeg, .png, .gif, .webp, .heic, .heif, .bmp`.
- Run HEIC/HEIF attachments through the same conversion pipeline used by the existing `pre_save` signal on `ItemImage`. If conversion fails, log the failure and skip that attachment — do not abort the submission. Verify the signal also fires for `StudentLostItemImage`; if not, register it.
- Reject any single attachment larger than 15 MB (log + skip). Reject the entire submission if combined attachments exceed 40 MB (log, write the `StudentLostItem` with description note, send a special acknowledgment per §1.4.1).
- Maximum 8 images per submission. If more are attached, store the first 8 (by attachment order) and append to description: `\n\n[Note: this submission included {N} images; only the first 8 were attached.]`
- Save each image as a `StudentLostItemImage` linked to the new `StudentLostItem`.
- Strip EXIF GPS data from images before saving (privacy). Use Pillow to re-save without EXIF if GPS tags are present.

#### 1.3.5 Deduplication

- Continue using the `Message-ID` header as the dedup key (already implemented).
- Add a model field `StudentLostItem.source_message_id` (CharField, max 998, db_index=True, blank=True) if not already present. Migrate.
- If a message has no `Message-ID`, compute a fallback hash of `(from_address, subject, body[:500], earliest_attachment_filename)` and store in `source_message_id` prefixed with `hash:`.

#### 1.3.6 Email-from Storage

- Store the parsed sender email address in `StudentLostItem.email_from` (lowercase). This field already exists.
- Store the original `Subject` (untransformed) in `StudentLostItem.email_subject`. This field already exists.
- **Add** a new field `StudentLostItem.submitter_display_name` (CharField, max 200, blank=True) — parse the display name from the `From` header (e.g., `"Raadvait Bansal" <raadvait@tisb.ac.in>` → `"Raadvait Bansal"`). Migrate.

#### 1.3.7 Submission Quality Flags

- **Add** a new field `StudentLostItem.needs_review_reason` (CharField, max 500, blank=True). Populate it by joining one or more of the following **canonical reason strings** with `"; "` (semicolon-space). Use these exact strings — do not paraphrase, do not localize, do not invent new ones in this iteration. Define them as module-level constants (in `inventory/constants.py`, create if absent) so the approval queue template and the parser both reference one source of truth.

  ```python
  NEEDS_REVIEW_REASONS = {
      "TITLE_MISSING": "Title was missing from subject line",
      "BODY_EMPTY": "Email body was empty",
      "ATTACHMENT_OVERSIZED": "Some attachments exceeded the 15 MB per-image limit",
      "TOTAL_OVERSIZED": "Combined attachment size exceeded 40 MB — submission stored without images",
      "TOO_MANY_IMAGES": "More than 8 images attached — only the first 8 were retained",
      "HEIC_CONVERSION_FAILED": "One or more HEIC attachments could not be converted to JPEG",
      "EXIF_STRIP_FAILED": "EXIF metadata stripping failed on one or more images",
  }
  ```

  Multiple reasons are joined in the order listed above. The approval queue (§1.6) renders the joined string verbatim in the amber `Needs review:` pill. If the joined string exceeds 500 characters (it should not, but guard anyway), truncate at 497 and append `...`.

#### 1.3.8 Mark Email as Seen

- Only mark the IMAP message as `\Seen` **after** the DB record is committed successfully. If the DB write fails, leave the email unread so the next run retries.

### 1.4 Acknowledgment Email to Student

Send immediately after a successful `StudentLostItem` creation. Use the existing async-thread email sending pattern (do not block the command).

**From:** `LF_EMAIL_DISPLAY_NAME <LF_EMAIL_ADDRESS>`
**To:** the student's `From` address
**Subject:** `Received: your lost item report — "{title}"`

**Body (plaintext):**

```
Hi {first_name_or_there},

This is an automated confirmation that TRACE — the TISB Lost & Found system — has received your lost item report.

Submission summary
------------------
Title:        {title}
Submitted at: {submitted_at_in_IST}
Images:       {image_count} attached

What happens next
-----------------
1. Your report is now in the approval queue. A staff member will review it.
2. If approved, your report will appear on the "Students' Lost Items" page of TRACE, visible to the school community.
3. If a staff member or another student matches your report to a found item, you will be notified by email at this address.
4. To collect any matched item, you must come in person to the school reception. Items will not be released to anyone other than the rightful owner, in person.

You can view all reports you have submitted, and any claims you have made, by visiting:
{MAGIC_LINK_BASE_URL}/my-reports/

This is an automated message — do not reply to this email. If you need to follow up, contact your Head of Year or the school reception.

— TRACE, TISB Lost & Found
```

- `{first_name_or_there}` = the first word of `submitter_display_name` if available, else `"there"`.
- `{submitted_at_in_IST}` formatted as `21 June 2026, 4:32 PM IST`.
- `{MAGIC_LINK_BASE_URL}` falls back to the request's scheme+host if the env var is unset; see §4.

#### 1.4.1 Oversized Submission Acknowledgment

If the submission was rejected for combined-attachment-size, send a **different** acknowledgment with subject `Action needed: your lost item report could not be fully processed` explaining the size limit and asking them to resend with smaller images or a description-only email.

### 1.5 Failure Modes & Logging

- All IMAP/parsing/email-send failures must be caught and logged via `logging.getLogger("inventory.check_emails")`. Never crash the management command on a single bad email; continue to the next.
- Add a summary log line at the end of each run: `"check_emails run complete: {n_fetched} fetched, {n_created} created, {n_skipped} skipped, {n_failed} failed"`.

### 1.6 Approval Queue Integration

The existing `/staff/approval-queue/` already shows pending `StudentLostItem` records. Extend it:

- Show the `submitter_display_name` (or `email_from` if name absent) prominently next to the title.
- If `needs_review_reason` is non-empty, render a small amber pill in the row: `Needs review: {reason}`.
- The details modal must show: title, full description, all images (clickable to enlarge), submitter name, submitter email, submitted-at timestamp, message-ID, and the `needs_review_reason`.
- Approve / Reject buttons remain unchanged in behavior, but the **wording** of the approve/reject email is updated per §3.5.

### 1.7 Post-Approval State

- On approval: set `approval_status=APPROVED`, `approved_by=request.user`, `approved_at=now()`, send the approval email per §3.5, and make the item eligible for **Broadcast to School Body** (§2).
- On rejection: set `approval_status=REJECTED`, store rejection — **add a new field** `StudentLostItem.rejection_reason` (CharField, max 500, blank=True). The reject button must open a small modal asking for an optional reason (max 500 chars). The reason is sent verbatim in the rejection email when present.

### 1.8 Scheduling

- Document in the project README (create or update `README.md` at repo root with a `## Email polling` section) that `python manage.py check_emails` must be run periodically. Recommend Railway cron at every 2 minutes.
- Add a command-line flag `--once` (default behavior, current) and `--loop SECONDS` (runs forever with sleep between cycles) for environments without a scheduler. The loop mode must handle `SIGTERM` cleanly.

### 1.9 Microsoft 365 OAuth2 Authentication (Modern Auth) — REQUIRED for BOTH IMAP and SMTP

This section is **critical** and **non-optional**. TISB uses Microsoft 365 (Exchange Online) for email. Microsoft has **fully deprecated basic authentication** (username + password) for IMAP, POP, and SMTP in Exchange Online. Every IMAP poll in `check_emails` and every outbound SMTP send (acknowledgments, claim confirmations, approve/reject emails, broadcasts, magic-link emails) **must** authenticate using OAuth2 with the `XOAUTH2` SASL mechanism, or the connection will fail with errors like `AUTHENTICATE failed` (IMAP) or `535 5.7.139 Authentication unsuccessful, basic authentication is disabled` (SMTP).

This is not a future hardening — it is the only way the app can send or receive email at all against a TISB mailbox.

#### 1.9.1 Canonical Server Settings (per Microsoft, August 2025)

| Direction | Server | Port | Encryption | Auth |
|---|---|---|---|---|
| IMAP (inbound) | `outlook.office365.com` | `993` | SSL/TLS | OAuth2 / XOAUTH2 |
| SMTP (outbound) | `smtp-mail.outlook.com` | `587` | STARTTLS | OAuth2 / XOAUTH2 |

These values are the defaults to bake into `settings.py` when the tenant is Microsoft. Override via the existing `EMAIL_HOST`, `EMAIL_PORT`, `LF_IMAP_HOST`, `LF_IMAP_PORT` env vars if a different tenant is ever used.

**Prerequisite (one-time, manual, done by the mailbox owner):** in the Outlook.com web UI, open **Settings → Mail → Forwarding and IMAP**, toggle `Let devices and apps use IMAP` to ON, save. Without this toggle the IMAP server will reject the OAuth2 connection with "IMAP access is disabled". Document this step in the README setup section verbatim. Do **not** try to automate it.

#### 1.9.2 Architecture Decision: Authorization Code Flow with Refresh Tokens

Two OAuth flows are available for Microsoft 365 mailbox access:

1. **Authorization Code Flow + refresh tokens (delegated user access)** — a one-time interactive sign-in (the mailbox owner clicks "yes, this app may access my mailbox" in a browser) yields a refresh token. The app stores the refresh token, and uses it to mint short-lived access tokens (1 hour) every time it needs to connect. Refresh tokens are valid for ~90 days of activity (each successful refresh resets the clock). **No tenant admin consent required** beyond the mailbox owner's individual consent. **This is what we will use.**

2. **Client Credentials Flow (app-only access)** — the app has its own identity in Azure AD and accesses the mailbox without any user sign-in. Requires a tenant admin to grant `IMAP.AccessAsApp` and `SMTP.SendAsApp` permissions and to run PowerShell commands granting the app access to the specific mailbox. **More robust long-term but requires school IT involvement.** Document as a future option in the README; do not implement in this iteration.

The choice is driven by feasibility: option 1 only needs Advait (or whoever owns `LF_EMAIL_ADDRESS`) to click through a sign-in once. Option 2 needs the IT head to run PowerShell. Start with option 1.

#### 1.9.3 Azure AD App Registration (one-time setup, done by a human, documented in README)

Document these exact steps in `README.md` under `## Microsoft 365 OAuth setup`. Claude Code does not perform these — they must be done in a browser by the deployer.

1. Sign in to <https://portal.azure.com> using the same Microsoft account that owns `LF_EMAIL_ADDRESS` (or a tenant admin account if available).
2. Navigate to **Microsoft Entra ID → App registrations → New registration**.
3. Name: `TRACE Lost and Found`. Supported account types: **Accounts in any organizational directory (Any Microsoft Entra ID tenant — Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)**. Redirect URI: select **Web** and enter `http://localhost:8765/oauth/callback` (for the one-time interactive setup run from a local machine). Click Register.
4. On the new app's overview page, copy the **Application (client) ID** → this is `MS_OAUTH_CLIENT_ID`.
5. Copy the **Directory (tenant) ID** → this is `MS_OAUTH_TENANT_ID`. If the app supports any tenant, you can also use the literal string `"common"` here.
6. Go to **Certificates & secrets → Client secrets → New client secret**. Description: `TRACE production`. Expires: 24 months. Click Add. **Immediately copy the `Value` column** (not the Secret ID) — this is `MS_OAUTH_CLIENT_SECRET`. It will never be shown again.
7. Go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions** and add:
   - `IMAP.AccessAsUser.All`
   - `SMTP.Send`
   - `offline_access`
   - `User.Read` (default)
   - `openid`, `profile`, `email`
8. Click **Grant admin consent for ...** only if you are a tenant admin. If you are not, the consent will happen interactively the first time the mailbox owner signs in (Step §1.9.5).
9. Save the three values (`MS_OAUTH_TENANT_ID`, `MS_OAUTH_CLIENT_ID`, `MS_OAUTH_CLIENT_SECRET`) into the Railway environment **and** the local `.env`.

#### 1.9.4 New Env Vars

| Var | Purpose | Required when |
|---|---|---|
| `MS_OAUTH_TENANT_ID` | Azure AD tenant ID, or `"common"` for multi-tenant | Always (if doing real email) |
| `MS_OAUTH_CLIENT_ID` | Azure AD app registration ID | Always |
| `MS_OAUTH_CLIENT_SECRET` | Azure AD client secret value | Always |
| `MS_OAUTH_SCOPES` | Space-separated scopes | Optional. Default: `"https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access"` |
| `MS_OAUTH_REDIRECT_URI` | Loopback URI for the one-time interactive setup | Optional. Default: `"http://localhost:8765/oauth/callback"` |
| `MS_OAUTH_AUTHORITY` | Authority URL | Optional. Default: `f"https://login.microsoftonline.com/{MS_OAUTH_TENANT_ID}"` |
| `MS_OAUTH_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting the refresh token at rest in the DB | Required. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Add the `msal` and `cryptography` libraries to `requirements.txt`:

```
msal>=1.28.0
cryptography>=42.0.0
```

#### 1.9.5 One-Time Interactive Setup Command

Create a new management command `inventory/management/commands/microsoft_oauth_setup.py`. This is run **once** by a human at the local machine to capture the initial refresh token.

Behavior:

1. Reads `MS_OAUTH_TENANT_ID`, `MS_OAUTH_CLIENT_ID`, `MS_OAUTH_CLIENT_SECRET`, `MS_OAUTH_SCOPES` from env. Hard-fails with a clear message if any required var is missing.
2. Spins up a tiny local HTTP server on `127.0.0.1:8765` to receive the OAuth redirect.
3. Builds the authorization URL using `msal.ConfidentialClientApplication.get_authorization_request_url(...)` with `state` (random nonce) and the configured scopes.
4. Opens the URL in the user's default browser (`webbrowser.open(...)`). Also prints the URL to stdout in case the browser doesn't open.
5. The user signs in with the mailbox owner's account (`LF_EMAIL_ADDRESS`), consents to the requested permissions.
6. Microsoft redirects back to `http://localhost:8765/oauth/callback?code=...&state=...`.
7. The local server validates `state`, exchanges the `code` for tokens via `msal.ConfidentialClientApplication.acquire_token_by_authorization_code(...)`.
8. On success: encrypt the `refresh_token` using `MS_OAUTH_TOKEN_ENCRYPTION_KEY` (Fernet) and store it in the new `MicrosoftOAuthToken` model (§1.9.6). Print `OAuth setup complete. Refresh token stored for {email}. The app can now send and receive email.` and exit 0.
9. On failure: print the error, exit non-zero.

The local HTTP server must time out after 5 minutes if no redirect comes back.

#### 1.9.6 New Model: `MicrosoftOAuthToken`

Single-row table (enforce singleton in `save()`).

```python
class MicrosoftOAuthToken(models.Model):
    account_email = models.EmailField(help_text="The mailbox the token authorizes access to.")
    encrypted_refresh_token = models.BinaryField(help_text="Fernet-encrypted refresh token.")
    cached_access_token = models.TextField(blank=True, help_text="Last access token in cleartext, valid until cached_access_token_expires_at.")
    cached_access_token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(help_text="Space-separated scopes the token grants.")
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Microsoft OAuth Token"
        verbose_name_plural = "Microsoft OAuth Tokens"

    def save(self, *args, **kwargs):
        # Singleton enforcement: only one row allowed.
        if not self.pk and MicrosoftOAuthToken.objects.exists():
            raise ValidationError("Only one MicrosoftOAuthToken row may exist. Delete the existing one first.")
        super().save(*args, **kwargs)
```

- Cleartext access tokens in the DB are acceptable: they expire in 1 hour and are only useful with the client secret anyway. The refresh token is the long-lived secret and **must** be encrypted.
- Expose in Django admin (Super User only), but **never** display the encrypted refresh token value in the admin UI — show only `account_email`, `last_refreshed_at`, `cached_access_token_expires_at`, `scopes`. Add a custom admin action `Revoke and clear token` that deletes the row (for re-setup).

Migration: `0014_microsoftoauthtoken.py` (or whatever next number is appropriate).

#### 1.9.7 Token Helper Module

Create `inventory/ms_oauth.py` exposing:

```python
def get_access_token() -> str:
    """
    Returns a valid access token, refreshing if necessary.
    Raises MicrosoftOAuthNotConfigured if no token row exists.
    Raises MicrosoftOAuthRefreshFailed if the refresh call fails terminally.
    """

def force_refresh() -> str:
    """Force a refresh even if the cached token is still valid. Returns the new access token."""

def is_configured() -> bool:
    """Returns True if MicrosoftOAuthToken row exists and env is present."""
```

Behavior of `get_access_token()`:

1. Load the singleton `MicrosoftOAuthToken` row. If absent: raise `MicrosoftOAuthNotConfigured`.
2. If `cached_access_token` is set and `cached_access_token_expires_at` is more than 60 seconds in the future: return the cached token.
3. Otherwise: decrypt the refresh token with `MS_OAUTH_TOKEN_ENCRYPTION_KEY`. Call `msal.ConfidentialClientApplication.acquire_token_by_refresh_token(refresh_token, scopes=...)`.
4. On success: store the new access token, its expiry (current time + `expires_in` seconds), update `last_refreshed_at`. If the response includes a new `refresh_token` (Microsoft rotates them sometimes), re-encrypt and store it. Return the access token.
5. On failure with `invalid_grant` (refresh token expired/revoked): raise `MicrosoftOAuthRefreshFailed` with a clear message instructing the deployer to re-run `microsoft_oauth_setup`. Also send a one-time alert email to `LF_BROADCAST_RECIPIENTS_LIST[0]` (if SMTP works at all — fall back to logging only).
6. On transient network failures: retry up to 3 times with exponential backoff (1s, 3s, 9s).

Thread-safe: wrap the refresh logic in a row-level lock (`MicrosoftOAuthToken.objects.select_for_update()` inside a transaction) to prevent two concurrent workers from each calling the refresh endpoint and racing on the rotated refresh token.

#### 1.9.8 Custom Django Email Backend (SMTP via XOAUTH2)

Django's built-in `django.core.mail.backends.smtp.EmailBackend` only supports basic auth. Subclass it.

Create `inventory/email_backends.py`:

```python
import base64
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
from inventory.ms_oauth import get_access_token

class MicrosoftOAuth2EmailBackend(DjangoSMTPBackend):
    """
    SMTP backend that authenticates via XOAUTH2 against Microsoft 365.
    Replaces the username/password login with an OAuth2 access token.
    """

    def open(self):
        if self.connection:
            return False

        # Establish the connection exactly like the parent does, but skip its login().
        connection_class = self.connection_class
        connection_params = {"local_hostname": DjangoSMTPBackend.local_hostname_from_settings() if hasattr(DjangoSMTPBackend, "local_hostname_from_settings") else None}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params.update({"keyfile": self.ssl_keyfile, "certfile": self.ssl_certfile})
        self.connection = connection_class(self.host, self.port, **connection_params)
        if not self.use_ssl and self.use_tls:
            self.connection.starttls(keyfile=self.ssl_keyfile, certfile=self.ssl_certfile)

        # XOAUTH2 SASL: user=<email>\x01auth=Bearer <token>\x01\x01, then base64.
        access_token = get_access_token()
        auth_string = f"user={self.username}\x01auth=Bearer {access_token}\x01\x01"
        auth_b64 = base64.b64encode(auth_string.encode()).decode()
        code, response = self.connection.docmd("AUTH", "XOAUTH2 " + auth_b64)
        if code != 235:
            # 235 = Authentication succeeded. Anything else is failure.
            raise Exception(f"XOAUTH2 SMTP authentication failed: {code} {response}")
        return True
```

In `settings.py`:

```python
if os.environ.get("MS_OAUTH_CLIENT_ID"):
    EMAIL_BACKEND = "inventory.email_backends.MicrosoftOAuth2EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp-mail.outlook.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_HOST_USER = os.environ["LF_EMAIL_ADDRESS"]
    EMAIL_HOST_PASSWORD = ""  # Unused with XOAUTH2; required to be set (empty is fine).
else:
    # Fallback: legacy basic auth (dev/test only — will fail against real Microsoft mailboxes).
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    # existing settings unchanged
```

Every existing piece of code that sends mail via `django.core.mail.send_mail` / `EmailMessage().send()` now transparently uses XOAUTH2. **No caller-side changes needed.**

#### 1.9.9 IMAP via XOAUTH2 in `check_emails`

The existing `check_emails` command uses `imaplib.IMAP4_SSL`. Replace its login with XOAUTH2.

In the command:

```python
import imaplib, base64
from inventory.ms_oauth import get_access_token

imap = imaplib.IMAP4_SSL(settings.LF_IMAP_HOST, int(settings.LF_IMAP_PORT))
access_token = get_access_token()
auth_string = f"user={settings.LF_EMAIL_ADDRESS}\x01auth=Bearer {access_token}\x01\x01"
imap.authenticate("XOAUTH2", lambda _: auth_string.encode())
imap.select(settings.LF_IMAP_MAILBOX)
# ... rest of the existing command
```

Handle the specific failure case where the IMAP server replies with an `AUTHENTICATIONFAILED` capability response: catch `imaplib.IMAP4.error`, call `force_refresh()` once, and retry. If the second attempt also fails, raise — the management command exits non-zero and logs loudly.

#### 1.9.10 Refresh Token Lifecycle & Failure Recovery

- Microsoft refresh tokens expire after ~90 days of inactivity. As long as the app uses the token at least once every 90 days, it stays valid indefinitely. Since `check_emails` runs every 2 minutes, this is not a practical concern.
- If the token is ever revoked (mailbox owner changes password, IT revokes app permissions, secret rotates), the next refresh attempt returns `invalid_grant`. The token helper raises `MicrosoftOAuthRefreshFailed` and the deployer must re-run `microsoft_oauth_setup`.
- Add a Django system check (`inventory/checks.py`) that warns at startup if `MS_OAUTH_CLIENT_ID` is set but no `MicrosoftOAuthToken` row exists. Message: `"Microsoft OAuth is configured in env but no token has been captured. Run 'python manage.py microsoft_oauth_setup' to authorize the app."` Severity: `WARNING`, not `ERROR` (so dev environments without real email still work).
- Add a Django admin status indicator: on the `MicrosoftOAuthToken` change page, show a colored badge: green if `last_refreshed_at` is within 24 hours, amber if within 7 days, red otherwise.

#### 1.9.11 Local Development Behavior

- For local dev, OAuth is optional. If `MS_OAUTH_CLIENT_ID` is not set, the app falls back to Django's built-in console email backend (`django.core.mail.backends.console.EmailBackend`) — emails are printed to stdout instead of sent. Add this fallback in `settings.py` when `DEBUG=True` and OAuth is unconfigured.
- `check_emails` requires real IMAP credentials and cannot run in dev without OAuth. Document this — devs who need to test email parsing should use the test fixtures in `test_check_emails.py` (synthetic `EmailMessage` objects fed directly to the parser), not a real IMAP connection.

#### 1.9.12 Tests

`test_ms_oauth.py`:

- `get_access_token()` returns the cached token when not expired.
- `get_access_token()` calls MSAL refresh when cached token is expired; verifies the new token is stored.
- `get_access_token()` raises `MicrosoftOAuthNotConfigured` when no row exists.
- `get_access_token()` raises `MicrosoftOAuthRefreshFailed` on `invalid_grant` response.
- Refresh token rotation: if MSAL returns a new refresh token, it is re-encrypted and stored.
- Encryption: `encrypted_refresh_token` cannot be read without `MS_OAUTH_TOKEN_ENCRYPTION_KEY`.
- Singleton: creating a second `MicrosoftOAuthToken` row raises `ValidationError`.

`test_email_backend.py`:

- Custom SMTP backend builds the correct XOAUTH2 string format (`user=...\x01auth=Bearer ...\x01\x01`, base64-encoded).
- Backend raises on non-235 response.
- Mock `get_access_token` and assert it is called exactly once per `open()`.

Do **not** make real network calls in tests. Mock everything (`unittest.mock.patch` on `msal.ConfidentialClientApplication`, `smtplib.SMTP`, `imaplib.IMAP4_SSL`).

#### 1.9.13 Deployment Checklist (add to README and §7 implementation list)

1. Register the Azure AD app per §1.9.3. Capture client ID, tenant ID, client secret.
2. Generate a Fernet encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
3. Set all `MS_OAUTH_*` env vars on Railway and locally.
4. Enable IMAP in the mailbox owner's Outlook.com settings (one-time toggle).
5. On a local machine with the same env vars set, run `python manage.py microsoft_oauth_setup`. Complete the browser sign-in.
6. Verify the `MicrosoftOAuthToken` row exists: `python manage.py shell -c "from inventory.models import MicrosoftOAuthToken; print(MicrosoftOAuthToken.objects.first())"`.
7. Dump the production DB row and import to Railway, **OR** re-run `microsoft_oauth_setup` from a machine with access to Railway's DB via `railway run`. (Document both approaches.)
8. Trigger a test email: `python manage.py shell -c "from django.core.mail import send_mail; send_mail('TRACE OAuth test', 'success', None, ['raadvait@tisb.ac.in'])"`.
9. Trigger a test IMAP poll: `python manage.py check_emails --once`.

If any step fails, the troubleshooting section in README must list the common errors (`invalid_grant`, `IMAP access is disabled`, `535 5.7.139`) and their fixes.

---

## 2. Broadcast to School Body

### 2.1 Overview

A Super User, viewing an approved `StudentLostItem` (and **optionally** an approved found `Item` — see §2.7), can click a **Broadcast to school** button that sends a formatted email to a configured list of recipients. The system tracks who broadcast, when, and to whom, and prevents accidental double-sending.

### 2.2 Recipient Configuration

- New env var `LF_BROADCAST_RECIPIENTS` (comma-separated email list). Default for now: `raadvait@tisb.ac.in,nsiddharth@tisb.ac.in`.
- Parsed once in `settings.py` into a Python list `LF_BROADCAST_RECIPIENTS_LIST`. Strip whitespace, lowercase, dedupe.
- Validate at startup: log a `WARNING` if the list is empty or any entry is malformed. Do not crash.
- Future-proofing: the model fields and view code must treat the recipient list as a runtime value, never inline the addresses anywhere in templates or views.

### 2.3 New Model: `BroadcastLog`

Add a new model in `inventory/models.py`:

```python
class BroadcastLog(models.Model):
    BROADCAST_KIND_CHOICES = [
        ("STUDENT_LOST", "Student lost item"),
        ("FOUND_ITEM", "Found item"),
    ]
    kind = models.CharField(max_length=20, choices=BROADCAST_KIND_CHOICES)
    student_lost_item = models.ForeignKey(StudentLostItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="broadcasts")
    found_item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="broadcasts")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="broadcasts_sent")
    sent_at = models.DateTimeField(auto_now_add=True)
    recipients = models.TextField(help_text="Comma-separated recipient addresses at time of send.")
    subject = models.CharField(max_length=255)
    body_preview = models.TextField(help_text="First 1000 chars of the body sent, for audit.")
    succeeded = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["kind", "-sent_at"])]
```

Add a `clean()` enforcing that **exactly one** of `student_lost_item` / `found_item` is non-null (matching `kind`).

Generate and run a migration `0011_broadcastlog_and_studentlostitem_fields.py` (or split into two migrations if cleaner).

### 2.4 Broadcast View

- New URL: `path("staff/broadcast/<str:kind>/<int:pk>/", BroadcastItemView.as_view(), name="broadcast_item")` where `<kind>` is `student-lost` or `found`.
- View class `BroadcastItemView(SuperUserRequiredMixin, View)` with `GET` (renders confirmation page) and `POST` (sends).
- The view must:
  1. Look up the item, 404 if not found or not `APPROVED`.
  2. On GET: render a confirmation page (`templates/inventory/broadcast_confirm.html`) showing the full email exactly as it will be sent (subject, recipients, body, attached image thumbnails), with a **Send broadcast** button and a **Cancel** button. Include a checkbox `I have reviewed this email and confirm it is appropriate to send to the recipient list.` that must be ticked before the Send button enables.
  3. On POST: re-fetch the item, recompose the email (do not trust client-submitted body), send to `LF_BROADCAST_RECIPIENTS_LIST`, create a `BroadcastLog` with `succeeded=True/False` and `error_message`, then redirect back to the item's detail page (for found items) or the approval queue / student lost items list (for student lost items) with a success/failure message.
- Sending uses the same async thread pattern as existing email code. Wait briefly (≤ 2s) for the result, then redirect; if not done, optimistically assume success and let the log be updated by the thread.

### 2.5 Broadcast Button UI

- **Approval Queue page (`approval_queue.html`):** for approved-but-never-broadcast `StudentLostItem`, show a **Broadcast** button. Add a tab toggle: `Pending` (default) | `Approved — not yet broadcast` | `All broadcasts`. Implement as querystring `?view=pending|to_broadcast|broadcasts`.
- **Students' Lost Items list (`student_lost_items_list.html`):** Super Users only — small Broadcast button on each card.
- **Student lost item detail (`student_lost_item_detail.html`):** Super Users only — prominent Broadcast button in a Super-User-only action bar at the top.
- **Item detail (`item_detail.html`) for found items:** Super Users only — Broadcast button in a Super-User-only action bar. (See §2.7 for the found-item broadcast wording.)

Button visual: cyan→purple gradient pill, white text, label `Broadcast to school`, with a small megaphone icon (lucide or inline SVG). If the item has already been broadcast, replace the button with a muted slate pill showing `Broadcast sent {n} time(s) — last sent {timestamp}` and a small `Resend` link that opens the same confirmation flow with an extra warning `This item has already been broadcast {n} time(s). Are you sure you want to send it again?` at the top.

### 2.6 Broadcast Email Content — Student Lost Item

**From:** `LF_EMAIL_DISPLAY_NAME <LF_EMAIL_ADDRESS>`
**To:** `LF_EMAIL_ADDRESS` itself (so the message has a valid `To`)
**Bcc:** `LF_BROADCAST_RECIPIENTS_LIST`
**Reply-To:** `LF_EMAIL_ADDRESS`
**Subject:** `TISB Lost & Found — Lost item reported: "{title}"`

**Body (plaintext):**

```
A student has reported the following item as lost. If you have seen this item, or if you have it in your possession, please bring it to the school reception in person.

Item: {title}

Description:
{description}

Reported by: {submitter_display_name_or_email}
Date reported: {submitted_at_in_IST}

Photographs of the item are attached to this email and can also be viewed in full resolution on TRACE:
{absolute_url_to_student_lost_item_detail}

If this item is yours and has been found, you must collect it in person from the school reception. The Lost & Found system does not release items to anyone other than the rightful owner, in person.

This email was sent by the TISB Lost & Found staff via TRACE.
— TRACE, TISB Lost & Found
```

**Image attachment is mandatory** when the `StudentLostItem` has any associated `StudentLostItemImage` rows. Every image must be attached inline as a regular MIME attachment (not just linked) so that recipients who don't click through to TRACE can still see the photos in their mail client. Apply the 20 MB total cap from below; if cap is hit, attach as many as fit (newest-first by `created_at`) and add the `[Note: ...]` line.

Attach all `StudentLostItemImage` files (limit total attached size to 20 MB; if exceeded, include only as many as fit and append: `[Note: {N} images were attached to the original report; {M} are included here. The remaining images are visible on TRACE at the link above.]`).

`{absolute_url_to_student_lost_item_detail}` is built from `MAGIC_LINK_BASE_URL` (or request scheme+host fallback) + `reverse("inventory:student_lost_item_detail", args=[item.pk])`. The URL must be a full absolute URL including scheme.

**HTML version:** clean HTML version of the same content in a new template `templates/inventory/email/broadcast_student_lost.html` (inline CSS only).

### 2.7 Broadcast Email Content — Found Item

Same flow for an approved `Item`. Subject: `TISB Lost & Found — Item found: "{title}"`. Body explains an item was found, gives category, location found, date found, and instructs anyone who recognizes it to come to reception in person to claim. Reuse the same precise collection wording.

The body must include the same `Photographs of the item are attached to this email and can also be viewed in full resolution on TRACE: {absolute_url}` line, where `{absolute_url}` is built from `reverse("inventory:item_detail", args=[item.pk])`.

**Image attachment is mandatory** when the `Item` has any associated `ItemImage` rows. Attach every image inline (not just linked), subject to the same 20 MB total cap and overflow `[Note: ...]` line as §2.6.

### 2.8 Audit & History

- New URL: `path("staff/broadcasts/", BroadcastHistoryView.as_view(), name="broadcast_history")`, Super User only, lists all `BroadcastLog` entries (paginated 50/page), filterable by `kind`, sortable by `sent_at`. Show: sent_at, kind, item title (link to item detail), sent_by, recipients, succeeded badge, error_message preview. Add a link to it from the Approval Queue page header.

### 2.9 Rate Limit & Safety

- Hard limit: a single item cannot be broadcast more than 3 times in any 24-hour window. Enforced in the POST view; on violation, render an error page explaining the limit and showing existing broadcasts for that item.
- Add a Django log entry at `INFO` level for every successful broadcast: `"Broadcast sent: kind={kind} item_id={id} sent_by={user} recipients_count={n}"`.

### 2.10 Symmetric Audit Fields on `Item`

The existing `StudentLostItem` model already records `approved_by` (FK User) and `approved_at`. The `Item` model does **not** — currently when a Super User approves an admin-uploaded found item there is no record of who or when. Fix this for parity and to support the audit story that the precise wording in §3 promises.

- Add two new fields to `Item`:
  - `approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="items_approved")`
  - `approved_at = models.DateTimeField(null=True, blank=True)`
- Also add a third field for symmetry with §1.7:
  - `rejection_reason = models.CharField(max_length=500, blank=True)`
- Update `ApproveItemView` and `RejectItemView` to set these fields when approving/rejecting an `Item` (the same view already handles both `Item` and `StudentLostItem` per `<type>` URL kwarg — confirm the logic forks correctly and writes the right model's fields).
- For items that were auto-approved because the uploader was a Super User, set `approved_by = uploader` and `approved_at = created_at` at the moment of upload, not lazily.
- Backfill via a data migration: for existing `Item` rows with `approval_status = APPROVED` where `approved_by` is null, set `approved_by = created_by` and `approved_at = created_at` (best-effort historical reconstruction).
- Expose both fields read-only in the `ItemAdmin` (Django admin).
- Display `Approved by {name} on {date_in_IST}` as a subtle slate-500 line at the bottom of the staff-only action bar on `item_detail.html` (Super User view only).
- Add the same line to the Admin Dashboard table as a tooltip on the status pill.

This is in addition to (not a replacement for) the existing `created_by` field.

---

## 3. Precise Wording Overhaul

The principle: **every user-facing string must be specific, attestational, and non-exploitable.** No vague phrases ("come collect it", "your stuff", "let us know"). Replace with concrete actions, named locations, and where appropriate, first-person attestations the student is putting their name to.

### 3.1 Claim Flow Wording

#### 3.1.1 On the Item Detail page (`item_detail.html`)

Above the claim form, replace any current heading with:

> **Claim this item**
>
> By submitting this form you are formally claiming that this specific item belongs to you. False claims, claims on behalf of someone else, and claims intended to deprive the rightful owner of their property are violations of the TISB Code of Conduct and will be referred to the relevant Head of Year.

#### 3.1.2 The Claim Form

Two required fields:

- `Full name (as it appears on your TISB record)` — text, required, min 2 chars, max 100.
- `TISB email address` — email, required, must end with `@tisb.ac.in` (server-side validation; inline error if not).

Below the fields, **a required checkbox** that must be ticked to enable Submit:

```
☐ I, the person named above, attest that this item is my personal property, that I am submitting this claim on my own behalf, and that I will collect this item in person from the school reception. I understand that submitting a false claim is a disciplinary matter.
```

The checkbox label must render the name typed into the form dynamically (JavaScript): once a name is entered, the label updates in real time to read `I, {name typed}, attest that …`. If the name field is empty, render `I, [enter your name above], attest that …` and keep the Submit button disabled.

Submit button label: `Submit claim`.

#### 3.1.3 Pre-Submit Confirmation Modal

On Submit click, before POSTing, open a modal:

> **Confirm your claim**
>
> You are about to submit a formal claim for the following item:
>
> **{item title}**
> Found at: {location_found}
> Found on: {date_found}
>
> You declared:
> Name: {name}
> Email: {email}
>
> By clicking "Confirm and submit", you are formally stating that this item belongs to you. A record of this claim, including your name, email, and the time of submission, will be stored and visible to TRACE staff.
>
> [ Cancel ]   [ Confirm and submit ]

The form only POSTs after the user clicks **Confirm and submit**.

#### 3.1.4 Success / Post-Claim Banner

After a successful claim, redirect to the item detail page with a green banner:

> **Your claim has been recorded.**
>
> A confirmation has been sent to {email}. To take possession of this item you must come in person to the school reception during school hours and present a valid form of TISB identification. Items will not be handed over to any person other than the named claimant.

Remove any existing wording like "come collect it" / "pick it up".

#### 3.1.5 Claim Confirmation Email

**Subject:** `Your claim has been recorded — "{item title}"`

**Body:**

```
Hi {name},

This email confirms that you have submitted a claim for the following item through TRACE, the TISB Lost & Found system.

Item:           {title}
Category:       {category}
Found at:       {location_found}
Found on:       {date_found_in_IST}
Claim submitted: {claimed_at_in_IST}

To take possession of this item you must come in person to the school reception during school hours. Please bring a valid form of TISB identification. The item will only be released to you in person — it will not be released to any other student, sibling, parent, or staff member acting on your behalf.

You can view all your claims and lost-item reports at:
{MAGIC_LINK_BASE_URL}/my-reports/

If you did not submit this claim, reply to this email immediately so that staff can investigate.

— TRACE, TISB Lost & Found
```

### 3.2 Claimed-State Display

- Replace badges like "Claimed" / "Taken" with: `Claim submitted — awaiting collection`. Tooltip: `One or more students have submitted claims for this item. The item is still in the possession of the school until collected in person from reception.`
- For multi-claim items: `{n} claims submitted` with the same tooltip.

### 3.3 Browse / Landing / Empty States

Audit and replace any of the following patterns:

| Old / vague wording | Replacement |
|---|---|
| "Lost something?" | "Have you lost an item at school?" |
| "Found something?" | "Have you found an item belonging to another student?" |
| "Get it back" | "Submit a formal claim to recover your item" |
| "We'll let you know" | "TRACE will send a confirmation to your TISB email address" |
| "Come collect it" / "Pick it up" | "Collect it in person from the school reception during school hours" |
| "Contact us" | "Contact the school reception or your Head of Year" |
| "Your stuff" / "your things" | "your personal property" |
| Empty list: "No items found." | "No items are currently listed in this view. New items appear here once they have been logged by staff and approved." |
| Empty student-lost list: "Nothing here." | "No student-submitted lost item reports are currently approved for display." |

Claude Code should grep the templates for vague verbs (`get`, `grab`, `take`, `find`, `pick`) and review every match against the principle above.

### 3.4 Submission-by-Email Instructions Page

Add `/how-to-report-lost/` → `HowToReportLostView(TemplateView)` → `templates/inventory/how_to_report.html`. Link from the Students' Lost Items list page header as `How to report a lost item`.

Page content (verbatim):

> **How to report a lost item to TRACE**
>
> If you have lost a personal item at school, you may submit a report by email. Reports are reviewed by TRACE staff before they appear publicly.
>
> **Send an email to:** `{LF_EMAIL_ADDRESS}`
>
> Your email must follow this exact format:
>
> 1. **Subject line** — the name of the item (for example: "Black water bottle with name sticker").
> 2. **Body** — a clear description of the item, where you last had it, and approximately when you lost it. Do not include personal details beyond what is necessary to identify the item.
> 3. **Attachments** — up to 8 images of the item (or of an identical item, if you do not have a photo of yours). Accepted formats: JPG, PNG, HEIC, WEBP, GIF, BMP. Maximum 15 MB per image, 40 MB total.
>
> **You must send the email from your TISB email address** (`...@tisb.ac.in`). Emails from any other address will be ignored.
>
> **What happens next:**
> 1. You will receive an automated confirmation within a few minutes.
> 2. A staff member will review your report. If approved, it will appear on the Students' Lost Items page.
> 3. Staff may choose to broadcast your report to a wider school audience.
> 4. If the item is found, you will be contacted at your TISB email. Items are released only in person at the school reception.
>
> **Do not** use this system to:
> - Report items lost outside school premises.
> - Make speculative or joke submissions.
> - Submit on behalf of another student — they must submit from their own TISB email.
>
> Misuse of this system will be referred to the relevant Head of Year.

### 3.5 Approval / Rejection Email Wording (sent to the submitting student)

#### 3.5.1 Approved

**Subject:** `Your lost item report has been approved — "{title}"`

```
Hi {first_name_or_there},

Your lost item report has been reviewed and approved by TRACE staff. It is now visible on the Students' Lost Items page of TRACE.

Item: {title}

If this item is found, you will be contacted at this email address. To take possession of the item you must come in person to the school reception during school hours and present a valid form of TISB identification.

You can view your reports at: {MAGIC_LINK_BASE_URL}/my-reports/

— TRACE, TISB Lost & Found
```

#### 3.5.2 Rejected

**Subject:** `Your lost item report was not approved — "{title}"`

```
Hi {first_name_or_there},

Your lost item report submitted on {submitted_at_in_IST} was reviewed by TRACE staff and was not approved for display.

{if rejection_reason: "Reason provided by staff: {rejection_reason}\n\n"}If you believe this decision was made in error, or if you would like to resubmit with additional information, you may send a new email to {LF_EMAIL_ADDRESS}. Please follow the submission format described on the "How to report a lost item" page of TRACE.

— TRACE, TISB Lost & Found
```

### 3.6 Staff Upload Flow Wording

On `item_upload.html`:

- Page heading: `Log a found item`
- Section heading above image inputs: `Photographs of the item (up to 3)`
- Section heading above title/description: `Item details — please be specific so the owner can identify it`
- Helper text under description: `Describe distinguishing features. For TISB notebooks, include color, name (if visible), class/section, and subject. Do not record any personal information beyond what is on the item itself.`
- Submit button label (Admin): `Submit for Super User approval`
- Submit button label (Super User): `Log item (will be published immediately)`

### 3.7 Footer / Global Disclaimer

Footer line on every page (sidebar bottom or main-area footer): `TRACE is operated by TISB. All claims and reports are logged. Misuse will be referred to the relevant Head of Year.`

### 3.8 Wording Audit Deliverable

Claude Code must produce `WORDING_AUDIT.md` at repo root listing every user-facing string change made:

```
File: templates/inventory/item_detail.html
  Before: "Come collect your item!"
  After:  "Collect it in person from the school reception during school hours."
```

---

## 4. Per-Student "My Reports" via Email Magic Link

### 4.1 Mental Model

A student visits `/my-reports/`, enters their `@tisb.ac.in` email, and clicks "Send me a sign-in link". The system emails them a single-use signed URL. Clicking it sets a session that lasts 24 hours and shows them their lost-item reports (matched by `email_from`) and their claims (matched by `claimant_email`). No password, no Django user account is created. This is entirely separate from staff login.

### 4.2 Configuration

- New env var `MAGIC_LINK_SECRET` (required if magic-link auth is enabled). If unset, the feature is disabled and the routes return 404. Generate a strong default for dev (e.g., derived from `DJANGO_SECRET_KEY` if `MAGIC_LINK_SECRET` is absent — but log a `WARNING` in that case).
- New env var `MAGIC_LINK_BASE_URL` (optional). When set, used to construct absolute URLs in emails. When unset, fall back to the request's scheme+host (production: Railway public domain).
- Token lifetime: **24 hours**.
- Token is implemented using `django.core.signing.TimestampSigner` (no extra DB model needed for the token itself; signed payload + timestamp + max-age check on verify).

### 4.3 New Model: `MagicLinkRequest` (for rate limiting and audit only)

```python
class MagicLinkRequest(models.Model):
    email = models.EmailField(db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    # consumed_at is set when the user successfully clicks the link.

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["email", "-requested_at"]),
        ]
```

Migration: `0012_magiclinkrequest.py` (or merge with 0011 if cleaner).

The token itself does **not** need DB storage — `TimestampSigner` makes the signed payload self-verifying. `MagicLinkRequest` is only for rate limiting and audit.

### 4.4 URL Routes (added to `inventory/urls.py`)

| URL | View | Access |
|---|---|---|
| `/my-reports/` | `MyReportsView` | Public — shows sign-in form OR the dashboard depending on session |
| `/my-reports/request-link/` | `RequestMagicLinkView` (POST) | Public — accepts email, sends link |
| `/my-reports/sign-in/<str:token>/` | `MagicLinkSignInView` (GET) | Public — verifies token, sets session, redirects to `/my-reports/` |
| `/my-reports/sign-out/` | `MyReportsSignOutView` (POST) | Public — clears the magic-link session |

### 4.5 Magic Link Flow

#### 4.5.1 Sign-in Request (GET `/my-reports/`)

If the session does not contain a valid `magic_link_email` key (or it has expired):

- Render `templates/inventory/my_reports_signin.html` — a Tailwind page consistent with the rest of the site, dark sidebar, centered card with:
  - Heading: `Sign in to view your reports`
  - Subhead: `Enter your TISB email address. We will send you a one-time sign-in link that is valid for 24 hours.`
  - Email input (required, must end with `@tisb.ac.in`)
  - Submit button: `Send me a sign-in link`
  - Below the form, a small paragraph: `This page lets you view the lost-item reports you have submitted by email and the claims you have made through TRACE. It does not give access to staff features.`

#### 4.5.2 Sending the Link (POST `/my-reports/request-link/`)

- Server-side validate that the email ends with `@tisb.ac.in` (case-insensitive). If not, re-render the form with an error: `Only @tisb.ac.in email addresses are accepted.`
- **Rate limit:** count `MagicLinkRequest` rows for this email in the last hour. If ≥ 3, render an error page: `You have requested too many sign-in links recently. Please wait an hour and try again.` Log at `WARNING`.
- Create a `MagicLinkRequest` row (with IP and User-Agent).
- Generate a signed token: `signer.sign_object({"email": email_lowercase, "req_id": magic_link_request.id})` using `TimestampSigner` (Django built-in). Wrap with URL-safe encoding.
- Build the absolute URL: `{base}/my-reports/sign-in/{token}/`.
- Send the email asynchronously using the existing async-thread sender:

  **Subject:** `Your TRACE sign-in link`

  **Body:**
  ```
  Hi,

  You requested a sign-in link to view your TRACE Lost & Found reports.

  Click the link below to sign in. The link is valid for 24 hours and can be used once.

  {sign_in_url}

  If you did not request this link, ignore this email. No action is needed.

  — TRACE, TISB Lost & Found
  ```
- Redirect to a confirmation page: `templates/inventory/my_reports_link_sent.html` with the message `A sign-in link has been sent to {email}. Check your inbox. If you do not see it within a few minutes, check your spam folder.` Do **not** confirm whether the email exists in any system — the message is identical for any well-formed `@tisb.ac.in` address (this matters less here than for general auth, but follow the principle).

#### 4.5.3 Clicking the Link (GET `/my-reports/sign-in/<token>/`)

- Verify the token with `signer.unsign_object(token, max_age=86400)` (24 hours).
- If invalid or expired: render `templates/inventory/my_reports_link_invalid.html` with `This sign-in link is invalid or has expired. Please request a new one.` and a link back to `/my-reports/`.
- Look up the `MagicLinkRequest` by `req_id`. If `consumed_at` is already set, render the same invalid page with a slightly different message: `This sign-in link has already been used. Please request a new one if you need to sign in again.` (Yes, this makes the link single-use within its 24-hour window.)
- Set `consumed_at = now()` on the `MagicLinkRequest`.
- Set `request.session["magic_link_email"] = email_lowercase`.
- Set `request.session["magic_link_signed_in_at"] = now().isoformat()`.
- Set the Django session expiry to 24 hours: `request.session.set_expiry(86400)`.
- Redirect to `/my-reports/`.

#### 4.5.4 The Dashboard (GET `/my-reports/` when signed in)

Render `templates/inventory/my_reports_dashboard.html`, consistent with the site's sidebar layout:

- Header: `Reports and claims for {email}`
- Sign-out button (POST to `/my-reports/sign-out/`)
- **Section 1: My lost item reports** — `StudentLostItem.objects.filter(email_from__iexact=email).order_by("-submitted_at")`. Show as cards: title, status badge (Pending / Approved / Rejected), submitted_at, image thumbnails, rejection_reason if rejected, link to the public detail page if approved, broadcast indicator (`Broadcast {n} time(s)` if there are broadcasts).
- **Section 2: My claims** — `Claim.objects.filter(claimant_email__iexact=email).select_related("item").order_by("-claimed_at")`. Show as cards: item title, claim submitted at, item status, link to item detail. For each claim, include the collection reminder line: `To take possession of this item, come in person to the school reception during school hours.`
- Empty states use the same precise wording style:
  - `You have not submitted any lost item reports from this email address.`
  - `You have not submitted any claims from this email address.`

#### 4.5.5 Sign Out (POST `/my-reports/sign-out/`)

- Clear `magic_link_email` and `magic_link_signed_in_at` from the session.
- Redirect to `/my-reports/`.

### 4.6 Security Notes

- The token contains the email — but it is signed, not encrypted. That is fine; the email is not secret. The signature prevents tampering.
- Magic-link sessions must **never** grant staff permissions. The dashboard view checks only `session["magic_link_email"]`; it does not log the user into Django auth.
- If a staff member is already logged in (Django session), the magic-link session is independent — both can coexist in the same browser. **However**, when rendering `/my-reports/`, the page must always use the **public/minimal sidebar layout** (the same one shown to logged-out users on the public browse pages), regardless of whether the user is also a staff member. This is non-negotiable: `/my-reports/` has a single visual identity — it is the "student-self-service" surface — and showing the staff sidebar (Upload Item, Admin Dashboard, Approval Queue, etc.) on this page would be confusing and would blur the line between the two trust contexts. Create a separate sidebar partial `templates/inventory/_sidebar_public.html` if needed, or pass a flag to the shared `_sidebar.html` to force the public variant.
- A staff member viewing `/my-reports/` therefore sees exactly what a regular student sees, with their own data populated. There is no "staff badge" indicator, no shortcuts to staff pages, and no Django admin link. They can navigate back to staff pages via direct URL or by signing in through `/accounts/login/` as usual.
- CSRF protection: the request-link form and sign-out form must use Django's CSRF token.
- Do **not** log the full token in any log. Log only the `req_id`.

### 4.7 Linking from Existing Emails

- Update the acknowledgment email (§1.4), claim confirmation email (§3.1.5), and approval email (§3.5.1) to include a link to `/my-reports/` (already done in those sections).

### 4.8 Tests

- `test_magic_link.py`:
  - Non-TISB email is rejected.
  - Rate limit kicks in at 4th request within an hour.
  - Token is invalid after 24 hours (mock time).
  - Token is single-use (`consumed_at` blocks reuse).
  - Dashboard shows only reports/claims matching the signed-in email.
  - Sign-out clears the session.
  - Magic-link session does not grant staff access (try hitting `/staff/dashboard/` — must redirect to login).

---

## 5. Object Storage for Media (S3 / Cloudflare R2)

### 5.1 Why

Railway's filesystem is ephemeral. Every redeploy wipes `media/`. All uploaded item images and student-submitted images currently live there. This iteration moves media to an S3-compatible bucket (Cloudflare R2 recommended for cost; the implementation is endpoint-agnostic).

### 5.2 Strategy

- Use **`django-storages[boto3]`**. Add to `requirements.txt`: `django-storages[boto3]>=1.14.0`.
- Implement a **backend switch** controlled by env var `MEDIA_BACKEND`:
  - `MEDIA_BACKEND=local` (default): Django's default `FileSystemStorage`. No change from current behavior. Used in dev.
  - `MEDIA_BACKEND=s3`: `storages.backends.s3boto3.S3Boto3Storage`. Used in production.
- All references to `MEDIA_URL` and `MEDIA_ROOT` continue to work in dev; in S3 mode they are replaced by the bucket's public URL.

### 5.3 Configuration

In `settings.py`:

```python
MEDIA_BACKEND = os.environ.get("MEDIA_BACKEND", "local").lower()

if MEDIA_BACKEND == "s3":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")  # e.g. https://<account>.r2.cloudflarestorage.com
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto")
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN")  # e.g. media.tisb-trace.example
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None  # R2 doesn't support ACLs the same way; rely on bucket policy
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=31536000, immutable"}
    AWS_QUERYSTRING_AUTH = False  # public-read URLs, no signing in URL
    # MEDIA_URL is derived by django-storages from the bucket/custom domain
else:
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
```

- WhiteNoise continues to serve **static** files; **media** is fully on S3 in prod.
- Validate at startup: if `MEDIA_BACKEND=s3` and any required `AWS_*` var is missing, fail loudly with a clear error message in stderr.

### 5.4 Bucket Setup Documentation

In `README.md`, add a `## Media storage (S3 / R2)` section documenting:

- Recommended provider: Cloudflare R2 (zero egress).
- Required bucket settings: public-read access for the `item_images/` and `student_item_images/` prefixes; CORS allowing the Railway domain for GET/HEAD; lifecycle rules (none required initially).
- The IAM/API token scope: `Object Read & Write` on the specific bucket only.
- Example R2 setup steps (create bucket, create API token, create custom domain, populate env vars).
- Verifying: upload a test image through the staff upload flow; confirm the URL starts with the custom domain or R2 endpoint.

### 5.5 Migration of Existing Local Files

Add a management command `inventory/management/commands/migrate_media_to_s3.py`:

- Iterates every `ItemImage.image` and `StudentLostItemImage.image`.
- For each, if the file exists locally and the storage backend is S3, opens the local file and saves it through the configured storage. Preserves the relative path (`item_images/...`, `student_item_images/...`).
- Idempotent: skips files that already exist in the bucket (use `storage.exists(name)`).
- Supports `--dry-run` (lists what would be uploaded) and `--verbose`.
- Logs a summary at the end: `{n_uploaded} uploaded, {n_skipped} already present, {n_failed} failed`.

This command is **only** intended to be run once during the migration cutover. Document it in README.

### 5.6 Compatibility With Existing Pipeline

- The HEIC→JPEG `pre_save` signal must continue to work. It operates on the `InMemoryUploadedFile` before the storage backend writes the file, so it is storage-agnostic. **Verify** with a test that uploads a HEIC and confirms a JPEG ends up in the bucket.
- EXIF GPS stripping (§1.3.4) operates similarly and must continue to work.
- The Gemini Vision API call in `analyze_images_ajax` reads from the in-memory uploaded files (not from storage), so it is unaffected. Confirm by reading the existing implementation.
- Image-display in templates uses `{{ image.image.url }}`. This will automatically return S3 URLs when the backend is S3. Verify by spot-checking the carousel and detail gallery.

### 5.7 Local Development Continues to Work

- Without `MEDIA_BACKEND=s3` in `.env`, everything behaves exactly as today: files in `media/`, served by Django dev server. No regression for local devs.
- Document this clearly in README.

### 5.8 Tests

- `test_storage.py`:
  - With `MEDIA_BACKEND=local` (default test settings), `ItemImage.image.storage` is `FileSystemStorage`.
  - When `MEDIA_BACKEND=s3` is forced via `override_settings`, `DEFAULT_FILE_STORAGE` resolves to S3 backend.
  - HEIC signal runs in either mode.
  - Do **not** require a real S3 bucket for tests; use `moto` (add as a dev dependency) to mock S3.
  - Add `moto` to `requirements-dev.txt` (create if absent) — do not put it in production `requirements.txt`.

### 5.9 Rollout Plan (document in README)

1. Provision the R2 bucket and credentials.
2. Set the new env vars in Railway.
3. Set `MEDIA_BACKEND=s3` in Railway env.
4. Deploy.
5. SSH into the Railway environment (or use Railway's exec) and run `python manage.py migrate_media_to_s3` to upload existing media.
6. Verify the site renders images correctly.
7. Mark migration done; the local `media/` directory in Railway's volume can be ignored from then on (it will continue to exist but is unused after migration).

---

## 6. Staff User Management UI (Super-User only)

### 6.1 Why This Exists

Currently Super Users manage other staff members by going into `/admin/` (the Django admin), opening the auth `User` model, and toggling `is_staff` / `is_superuser` checkboxes among ~15 unrelated fields (permissions, groups, last_login, date_joined, password hash, etc.). The Django admin User edit page is cluttered, exposes irrelevant Django internals, has no Tailwind styling consistent with the rest of TRACE, and offers no audit log of role changes.

This section replaces that workflow with a **dedicated, purpose-built user management UI** accessible from the staff navigation. The Django admin remains available as a fallback for emergencies, but the **official path** for granting and revoking staff access is now this new UI.

### 6.2 Mental Model

A Super User clicks **Manage users** in the staff sidebar. They land on `/staff/users/` — a clean table of every Django `User` row showing only the fields that matter for TRACE: username, full name, email, role, last sign-in, status. From there they can:

- Create a new staff user (admin or super user) with a starting password.
- Edit an existing user (change name, email, role, active status, reset password).
- Promote / demote users with one click (Make Admin, Make Super User, Demote to Admin, Revoke staff access).
- Deactivate a user without deleting their record.
- Delete a user entirely (with hard safeguards against locking out the system).

Every role change is logged in a new `UserRoleChangeLog` model for audit. The affected user receives an email notification about the change.

### 6.3 Roles & Permissions Recap (for clarity)

TRACE has three Django-auth states that map to three TRACE roles:

| `is_active` | `is_staff` | `is_superuser` | TRACE role | Can do |
|---|---|---|---|---|
| True | False | False | (None — locked out of staff features but row exists) | Cannot sign in to staff areas. |
| True | True | False | **Admin** | Upload items (PENDING), see Admin Dashboard. |
| True | True | True | **Super User** | Everything Admin can + approvals, broadcasts, user management, Django admin. |
| False | * | * | **Deactivated** | Cannot sign in at all. |

A user whose `is_active=False` cannot sign in regardless of staff/superuser flags. The UI must surface deactivation as a top-level state, not bury it.

### 6.4 URL Routes (added to `inventory/urls.py`)

| URL | View | Access | Purpose |
|---|---|---|---|
| `/staff/users/` | `UserManagementListView` | Super User | Table of all users + filters + search |
| `/staff/users/new/` | `UserManagementCreateView` | Super User | Create a new staff user |
| `/staff/users/<int:pk>/` | `UserManagementDetailView` | Super User | View one user's details and role-change history |
| `/staff/users/<int:pk>/edit/` | `UserManagementEditView` | Super User | Edit name, email, active flag, role |
| `/staff/users/<int:pk>/set-password/` | `UserManagementSetPasswordView` | Super User | Set a new password (or generate one) |
| `/staff/users/<int:pk>/delete/` | `UserManagementDeleteView` | Super User | Delete the user (confirmation required) |

All views use `SuperUserRequiredMixin`. Non-super-users hitting these URLs get a 403, not a redirect to login — they are authenticated but not authorized.

### 6.5 New Model: `UserRoleChangeLog`

Audit log of every role change. Add to `inventory/models.py`:

```python
class UserRoleChangeLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "User created"),
        ("PROMOTE_ADMIN", "Granted Admin access"),
        ("PROMOTE_SUPERUSER", "Granted Super User access"),
        ("DEMOTE_TO_ADMIN", "Demoted from Super User to Admin"),
        ("REVOKE_STAFF", "Revoked staff access"),
        ("DEACTIVATE", "Deactivated"),
        ("REACTIVATE", "Reactivated"),
        ("DELETE", "Deleted"),
        ("EDIT_PROFILE", "Profile edited (name/email)"),
        ("PASSWORD_RESET", "Password reset by Super User"),
    ]
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="role_changes_received",
        help_text="The user whose role was changed. SET_NULL so the log survives user deletion.",
    )
    target_username_snapshot = models.CharField(max_length=150, help_text="Username at time of change (in case the user is later deleted).")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="role_changes_performed",
    )
    performed_by_username_snapshot = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    details = models.TextField(blank=True, help_text="Free-text details, e.g. 'is_staff: False → True; is_superuser: False → True'.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_user", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
```

Migration: `0015_userrolechangelog.py` (or whatever next number).

Every action in the management UI must create a `UserRoleChangeLog` row inside the same DB transaction as the change itself (use `transaction.atomic()`). If the role change rolls back, the log row also rolls back.

### 6.6 Safeguards (HARD RULES — must be enforced server-side, not just in JS)

These rules exist to prevent a Super User from accidentally (or deliberately) locking the system out. Enforce in views; render disabled UI controls and explanatory tooltips on the client to mirror.

1. **A Super User cannot demote themselves.** The action buttons for "Revoke Super User", "Revoke Admin", "Deactivate", and "Delete" are disabled on their own row, with tooltip `You cannot change your own role or status. Ask another Super User to do this.`
2. **A Super User cannot delete themselves.** Same enforcement.
3. **The last remaining active Super User cannot be demoted, deactivated, or deleted.** Compute `User.objects.filter(is_superuser=True, is_active=True).count()` before allowing any of these actions. If the target is the last one and the action would result in zero active Super Users, refuse with a clear error page: `This action would leave the system without any active Super Users. At least one active Super User must remain at all times. Promote another user to Super User first.`
4. **Promoting a user to Super User automatically sets `is_staff=True`.** A Super User who is not also `is_staff=True` is a Django-auth anomaly that causes weird permission edge cases. Always pair them.
5. **Demoting from Super User to Admin sets `is_superuser=False` and leaves `is_staff=True`.** The "Revoke staff access" action (which sets `is_staff=False`) is a separate action.
6. **Email addresses must end with `@tisb.ac.in`** when creating or editing a staff user. Server-side validation; show inline error if violated. (Justification: staff are TISB employees; non-TISB emails are out of scope.)
7. **Usernames are case-insensitive and unique.** Enforce in form `clean_username()` using `User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk).exists()`.
8. **Passwords must meet Django's default validators** (`AUTH_PASSWORD_VALIDATORS` — already configured by default). Show the standard error messages on failure.
9. **A user with `is_active=False` is hidden from approval-queue dropdowns and other "select a staff member" UI** but still shown in the user management list (with a deactivated badge).

### 6.7 List Page (`/staff/users/`)

**Template:** `templates/inventory/user_management_list.html`. Sidebar layout consistent with other staff pages.

**Layout:**

- Header: `Staff user management`
- Subheader: `Manage who has Admin and Super User access to TRACE. Changes are logged.`
- Primary action button (top right, cyan→purple gradient): `+ Add new staff user` → `/staff/users/new/`
- Secondary action: `View role change history` → opens the full role-change log (§6.12).
- Filter bar:
  - Role filter dropdown: `All / Super Users / Admins / Deactivated / No staff access`
  - Search box: matches against username, first_name, last_name, email (case-insensitive, partial)
  - Sort dropdown: `Username (A-Z) / Last sign-in (recent first) / Date joined (recent first) / Role`
- Table with columns:
  1. **User** — avatar circle (first letter of username on slate-700 background) + username (large) + full name (small, slate-400)
  2. **Email** — clickable mailto link
  3. **Role** — color-coded badge: purple for Super User, cyan for Admin, amber for Deactivated, slate for No staff access
  4. **Last sign-in** — relative (`3 hours ago`, `2 days ago`, `Never`)
  5. **Date joined** — `21 June 2026`
  6. **Actions** — kebab menu (⋮) opening: Edit, Set password, Promote/Demote (context-aware), Deactivate/Reactivate, Delete

- Row highlight: the current viewer's own row has a subtle slate-800 background and a `(you)` tag next to the username. Their action menu omits self-destructive actions per §6.6.
- Pagination: 25 rows per page. If there are 26+ users (unlikely in this context), paginate.
- Empty state: `No staff users found matching your filters.` (with a Clear filters link if filters are applied).

**Context-aware promote/demote menu items:**

| Current state | Menu items shown |
|---|---|
| Super User + active | Demote to Admin, Revoke staff access, Deactivate, Edit, Set password, Delete |
| Admin + active | Promote to Super User, Revoke staff access, Deactivate, Edit, Set password, Delete |
| No staff access + active | Make Admin, Make Super User, Deactivate, Edit, Set password, Delete |
| Deactivated (any role) | Reactivate, Edit, Set password, Delete |

Each destructive action (`Revoke staff access`, `Deactivate`, `Delete`, `Demote to Admin`) opens a confirmation modal — see §6.9.

### 6.8 Create User Page (`/staff/users/new/`)

**Template:** `templates/inventory/user_management_create.html`.

Form fields (all required unless noted):

- **Username** — text, max 150, validators: Django's `UnicodeUsernameValidator`, plus case-insensitive uniqueness check.
- **First name** — text, max 150.
- **Last name** — text, max 150.
- **Email** — must end with `@tisb.ac.in`.
- **Role** — radio buttons, exactly one of:
  - `Admin` — sets `is_staff=True, is_superuser=False`
  - `Super User` — sets `is_staff=True, is_superuser=True`
- **Active** — checkbox, defaults checked.
- **Initial password** — password field with a `Generate strong password` button next to it. Clicking the button fills the field with a 16-char random password (alphanumeric + symbols) and reveals it in plaintext for the Super User to copy. **Required to be filled** before submit.
- **Send welcome email** — checkbox, defaults checked. When checked, after creation, send the user an email per §6.10 with their username and (if applicable) the password.

**Submit button label:** `Create user`.
**Cancel button:** returns to `/staff/users/`.

On successful creation:
1. Create the `User` row inside a `transaction.atomic()`.
2. Create the `UserProfile` row (the existing code creates this for super users; do it here too for all created users).
3. Create a `UserRoleChangeLog` with action `CREATE` and `details = f"Created with role={role}; is_active={is_active}"`.
4. If "Send welcome email" was checked, send the email asynchronously.
5. Redirect to `/staff/users/` with a green success banner: `User "{username}" created and granted {role} access.`

### 6.9 Edit / Action Confirmation Flows

#### 6.9.1 Edit Page (`/staff/users/<pk>/edit/`)

Same form layout as Create except:
- Username is **read-only** (changing usernames is a hassle that breaks audit trails; if a username really needs to change, the Super User should delete and recreate).
- The password section is hidden (set-password is a separate page).
- The Role radio includes a fourth option: `No staff access` — sets `is_staff=False, is_superuser=False`.
- Submitting compares old vs new field values; logs only the fields that actually changed.

If the role changes, `UserRoleChangeLog` records the specific transition (`PROMOTE_SUPERUSER`, `DEMOTE_TO_ADMIN`, `REVOKE_STAFF`, etc.). The `details` field stores `"is_staff: False → True; is_superuser: False → True"` style transitions.

#### 6.9.2 Set Password Page (`/staff/users/<pk>/set-password/`)

Small focused page with just:
- The target user's username and email (read-only).
- New password field.
- `Generate strong password` button.
- `Send the new password to the user by email` checkbox (defaults checked).
- Submit button: `Set password`.

On submit: hash the password using Django's `set_password()`, save, log a `PASSWORD_RESET` row. If the checkbox is checked, email the user (§6.10).

#### 6.9.3 Confirmation Modals (for destructive actions)

Use a consistent modal pattern. The modal shows:

```
{Action title — e.g. "Revoke staff access"}

You are about to {action description, e.g. "remove staff access for"} {full_name} ({username}, {email}).

{Consequences in plain English, e.g. "After this change, this user will no longer be able to upload items, see the Admin Dashboard, or access any staff feature. They will still have a TRACE login but it will only show public pages."}

This change will be logged.

[ Cancel ]   [ Confirm: {action verb, e.g. "Revoke access"} ]
```

The Confirm button text uses the precise verb (`Revoke access`, `Demote to Admin`, `Deactivate user`, `Delete user permanently`). The Confirm button color follows severity: amber for reversible changes (demote, deactivate), red for irreversible (delete).

Specific consequence texts (verbatim):

- **Demote to Admin:** `After this change, {name} will keep Admin access (uploading items, Admin Dashboard) but will lose Super User powers: they will no longer be able to approve items, broadcast, manage other users, or access the Django admin.`
- **Revoke staff access:** `After this change, {name} will no longer be able to upload items, see the Admin Dashboard, or access any staff feature. Their account will still exist but they will only see public pages when they sign in.`
- **Deactivate:** `After this change, {name} will no longer be able to sign in at all. Their account row is preserved and can be reactivated later.`
- **Delete user permanently:** `This will permanently delete the account for {name}. This cannot be undone. Any items, claims, broadcasts, or approvals performed by this user will remain in the system but will show "Deleted user" instead of their name. The role-change log for this user will be preserved for audit purposes.`

The Delete modal additionally requires the Super User to **type the target username** into a confirmation input before the Confirm button enables — same pattern as GitHub's repo deletion. This prevents accidental clicks.

### 6.10 Email Notifications

All notifications use the existing async-thread sender and the precise-wording style established in §3.

#### 6.10.1 Welcome email (on user creation, if "Send welcome email" was checked)

**Subject:** `Your TRACE staff account has been created`

```
Hi {first_name_or_username},

A TRACE staff account has been created for you by {creator_full_name} ({creator_email}).

Account details
---------------
Username: {username}
Role:     {Admin or Super User}
Sign-in:  {site_base_url}/accounts/login/

{if password_provided:
"Your initial password is: {password}

You should sign in and change your password as soon as possible."}

If you were not expecting this email, reply to {creator_email} immediately.

— TRACE, TISB Lost & Found
```

#### 6.10.2 Role-change notification

Sent on `PROMOTE_ADMIN`, `PROMOTE_SUPERUSER`, `DEMOTE_TO_ADMIN`, `REVOKE_STAFF`, `DEACTIVATE`, `REACTIVATE`.

**Subject:** `Your TRACE access has changed` (use this generic subject for all change types)

Body (variant by action):

- **Promote to Admin:** `Hi {name}, you have been granted Admin access to TRACE by {performer_name}. You can now upload found items and access the Admin Dashboard. Sign in at {site_base_url}/accounts/login/.`
- **Promote to Super User:** `Hi {name}, you have been granted Super User access to TRACE by {performer_name}. You can now approve items, broadcast to the school, manage other users, and access the Django admin. Sign in at {site_base_url}/accounts/login/.`
- **Demote to Admin:** `Hi {name}, your access level on TRACE has been changed from Super User to Admin by {performer_name}. You still have access to upload items and the Admin Dashboard, but you no longer have Super User powers (approvals, broadcasts, user management, Django admin). If you have questions, contact {performer_email}.`
- **Revoke staff access:** `Hi {name}, your staff access to TRACE has been revoked by {performer_name}. You can no longer upload items or access staff features. Your account still exists but you will only see public pages when you sign in. If you have questions, contact {performer_email}.`
- **Deactivate:** `Hi {name}, your TRACE account has been deactivated by {performer_name}. You can no longer sign in. If this is unexpected, contact {performer_email}.`
- **Reactivate:** `Hi {name}, your TRACE account has been reactivated by {performer_name}. You can now sign in again at {site_base_url}/accounts/login/.`

#### 6.10.3 Password reset notification

**Subject:** `Your TRACE password has been reset`

```
Hi {name},

Your TRACE password has been reset by {performer_name}.

{if password_provided:
"Your new password is: {password}

You should sign in and change this password as soon as possible."
else:
"Contact {performer_email} for your new password."}

If you did not request this, contact {performer_email} immediately.

— TRACE, TISB Lost & Found
```

### 6.11 Navigation Integration

- Add a **Manage users** link to the staff sidebar, **Super-User-only** (hidden for Admins). Place it directly below the existing `Approval Queue` link.
- Icon: a small SVG of two stylized user silhouettes (or use lucide-style `users`).
- The existing `promote_superuser` management command stays — it is a CLI fallback for emergencies (e.g. when there are zero active Super Users and the UI is inaccessible). Document this in the README under `## Emergency recovery`.

### 6.12 Role Change History Page (`/staff/users/role-changes/`)

A read-only audit log page for Super Users:

- New URL: `/staff/users/role-changes/` → `UserRoleChangeHistoryView` (SuperUserRequiredMixin).
- Template: `templates/inventory/user_role_change_history.html`.
- Lists all `UserRoleChangeLog` rows, paginated (50/page), most recent first.
- Filterable by `action` (dropdown), `target_user`, `performed_by`, and date range.
- Columns: Timestamp (IST), Action (colored pill), Target user (link to their detail page if still exists, else just the snapshot username), Performed by, Details.
- Linked from the user management list page header (`View role change history` button).

### 6.13 Django Admin Coexistence

- The Django admin (`/admin/`) remains accessible to Super Users and continues to show the `User` model.
- However: add a banner at the top of the Django admin User list page (via `SuperUserOnlyAdminSite.index_template` or similar override) saying: `For staff role management, prefer the dedicated TRACE user management UI at /staff/users/. The Django admin is retained for emergency access only.`
- Do **not** remove or hide the User entry from Django admin — it remains as the fallback.

### 6.14 Tests

`test_user_management.py`:

- Only Super Users can access any `/staff/users/*` URL; Admins and anonymous users get 403 or redirect.
- Creating a user with a non-TISB email is rejected server-side.
- Creating a user with a duplicate (case-insensitive) username is rejected.
- Promoting to Super User auto-sets `is_staff=True`.
- A Super User cannot demote themselves (assertion on view + form).
- A Super User cannot delete themselves.
- When only one active Super User exists, demote/deactivate/delete on that user is refused with the documented error.
- Every action creates exactly one `UserRoleChangeLog` row inside the same transaction.
- Each role change triggers exactly one email notification (verify with `django.core.mail.outbox`).
- Deletion preserves the `UserRoleChangeLog` rows (target_user becomes NULL, snapshot username remains).
- Password set: hashed password is stored (assert `user.check_password(new_pw)` is True; assert `new_pw` is not stored in plaintext anywhere).
- The user management sidebar link is hidden for Admins (template-render assertion) and visible for Super Users.

---

## 7. Implementation Task List (in suggested execution order)

1. **Branch & baseline**
   1. Create branch `feature/iteration-email-broadcast-myreports-storage`.
   2. Run existing tests; record baseline.

2. **Model & migration changes**
   1. Add fields to `StudentLostItem`: `submitter_display_name`, `needs_review_reason`, `rejection_reason`, `source_message_id` (if absent).
   2. Add fields to `Item`: `approved_by`, `approved_at`, `rejection_reason` (§2.10).
   3. Add `BroadcastLog` model (§2.3).
   4. Add `MagicLinkRequest` model (§4.3).
   5. Add `MicrosoftOAuthToken` model (§1.9.6).
   6. Add `UserRoleChangeLog` model (§6.5).
   7. Generate and run migrations (`0011_*` through `0015_*` as needed).
   8. Add a **data migration** that backfills `Item.approved_by = created_by` and `Item.approved_at = created_at` for all existing rows where `approval_status = APPROVED` and `approved_by IS NULL` (§2.10).
   9. Update `inventory/admin.py` to register new models and expose new fields read-only. Add a banner to the Django admin User list page pointing to `/staff/users/` (§6.13).

3. **Microsoft 365 OAuth foundation (§1.9) — MUST PRECEDE ALL EMAIL WORK**
   1. Add `msal>=1.28.0` and `cryptography>=42.0.0` to `requirements.txt`.
   2. Add OAuth env vars to `settings.py` with proper defaults and validation.
   3. Implement `inventory/ms_oauth.py` (token helper module per §1.9.7).
   4. Implement `inventory/email_backends.py` with `MicrosoftOAuth2EmailBackend` (§1.9.8).
   5. Implement `inventory/management/commands/microsoft_oauth_setup.py` (one-time interactive setup per §1.9.5).
   6. Add the Django system check that warns when OAuth env is configured but no token row exists (§1.9.10).
   7. Document the Azure AD app registration steps in README (§1.9.3) including the IMAP-enable toggle and the deployment checklist (§1.9.13).
   8. Tests: `test_ms_oauth.py`, `test_email_backend.py` (§1.9.12). No real network calls.

4. **`check_emails` hardening (§1.3) + XOAUTH2 IMAP**
   1. Replace basic-auth login with XOAUTH2 per §1.9.9. Wire `get_access_token()` + retry-on-`AUTHENTICATIONFAILED`.
   2. Implement all of §1.3 — subject/body/attachment rules, dedup, quality flags, EXIF stripping, size limits.
   3. Implement canonical `NEEDS_REVIEW_REASONS` constants in `inventory/constants.py` (§1.3.7).
   4. Add `--loop` flag.
   5. Tests: `inventory/tests/test_check_emails.py` for every parser branch.

5. **Acknowledgment email (§1.4)**
   1. Implement normal and oversized variants.
   2. Tests via `django.core.mail.outbox`.

6. **Approval queue updates (§1.6, §1.7)**
   1. Show new fields and amber pill for `needs_review_reason`.
   2. Add rejection-reason modal.
   3. Update approve/reject email wording per §3.5.
   4. Add tab toggle (Pending / Approved-not-broadcast / All broadcasts) per §2.5.

7. **Broadcast feature (§2)**
   1. `BroadcastItemView`, `BroadcastHistoryView`, URLs.
   2. Templates: `broadcast_confirm.html`, `broadcast_history.html`, `email/broadcast_student_lost.html`, `email/broadcast_found_item.html`.
   3. Broadcast buttons on the four UI surfaces (§2.5).
   4. Rate limit (§2.9).
   5. Tests: permission, gate on APPROVED, rate limit, log creation, email composition, attachment size cap, View on TRACE link presence, mandatory image attachment.

8. **Magic-link "My Reports" (§4)**
   1. URLs and views.
   2. Templates: `my_reports_signin.html`, `my_reports_link_sent.html`, `my_reports_link_invalid.html`, `my_reports_dashboard.html`.
   3. Token signing helper in `inventory/magic_links.py` (new module).
   4. Public sidebar partial enforcement (§4.6).
   5. Rate limit (3/hour per email).
   6. Tests: §4.8.

9. **Staff User Management UI (§6)**
   1. URLs and views (`UserManagementListView`, `UserManagementCreateView`, `UserManagementDetailView`, `UserManagementEditView`, `UserManagementSetPasswordView`, `UserManagementDeleteView`, `UserRoleChangeHistoryView`).
   2. Templates under `templates/inventory/user_management/`: `list.html`, `create.html`, `detail.html`, `edit.html`, `set_password.html`, `role_change_history.html`, plus shared `_confirm_modal.html`.
   3. Forms in `inventory/forms.py`: `UserCreateForm`, `UserEditForm`, `UserSetPasswordForm` — all enforcing the §6.6 safeguards in `clean()`.
   4. View-level safeguards (§6.6): self-action prevention, last-active-superuser protection, role coupling (`is_superuser=True` implies `is_staff=True`).
   5. Email notification templates and dispatch (§6.10): welcome, role-change, password-reset.
   6. Add **Manage users** link to the staff sidebar partial (Super-User-only).
   7. Add deprecation banner to the Django admin User list page (§6.13).
   8. Tests: `test_user_management.py` per §6.14.

10. **Claim flow wording + UX (§3.1, §3.2)**
    1. Update `item_detail.html` — heading, claim form, dynamic attestation checkbox label, modal.
    2. JavaScript: checkbox-required gate, dynamic name in label.
    3. Server-side: form must reject claims without the attestation flag.
    4. Update post-claim banner and claim confirmation email.
    5. Update claimed-state badges.
    6. Tests: `test_claim_wording.py`.

11. **How-to-report page (§3.4)**
    1. View, URL, template.
    2. Link from `student_lost_items_list.html` header.

12. **Wording sweep (§3.3, §3.6, §3.7)**
    1. Apply across every template.
    2. Produce `WORDING_AUDIT.md`.
    3. Add `test_wording_audit.py` regression guard with regex word boundaries and AST string-literal scan (§8.1).

13. **Object storage (§5)**
    1. Add `django-storages[boto3]` to `requirements.txt`; add `moto` to `requirements-dev.txt`.
    2. Update `settings.py` with the `MEDIA_BACKEND` switch (§5.3).
    3. Add `migrate_media_to_s3` management command (§5.5).
    4. Tests in `test_storage.py` (§5.8).
    5. Document setup in README (§5.4) and rollout in README (§5.9).

14. **Settings & env**
    1. Add all new env vars to `settings.py` with safe defaults.
    2. Update `README.md` with the full env var table, `## Microsoft 365 OAuth setup`, `## Email polling`, `## Media storage`, `## Magic-link sign-in`, `## Staff user management`, `## Emergency recovery`, and `## Roadmap` sections.

15. **Final pass**
    1. `python manage.py check`.
    2. Run all tests.
    3. `python manage.py makemigrations --check --dry-run`.
    4. `python manage.py collectstatic --noinput --dry-run`.
    5. Manual smoke test checklist (record in `MANUAL_TESTS.md`):
       - [ ] Run `microsoft_oauth_setup`; complete the browser sign-in; verify the `MicrosoftOAuthToken` row exists.
       - [ ] Trigger a test outbound email; verify it arrives at the target inbox.
       - [ ] Send a real test email from a `@tisb.ac.in` address to `LF_EMAIL_ADDRESS`; verify it appears in the approval queue with images.
       - [ ] Approve it; verify approval email arrives.
       - [ ] Click Broadcast; verify confirmation page renders; verify email arrives at all recipients with images attached AND a working "View on TRACE" link.
       - [ ] `BroadcastLog` row created.
       - [ ] Broadcast 4 times in 24h → rate limit fires.
       - [ ] Submit a claim; checkbox required, modal shows, confirmation email arrives, banner updates.
       - [ ] Non-TISB email rejected on claim form.
       - [ ] Visit `/my-reports/`, request a link, click it, see your reports and claims.
       - [ ] Verify `/my-reports/` shows the public sidebar even when signed in as a staff user.
       - [ ] Try the link twice → second use shows "already used".
       - [ ] Magic-link session does not grant `/staff/dashboard/` access.
       - [ ] With `MEDIA_BACKEND=s3`, upload an item image and verify URL points to the bucket / custom domain.
       - [ ] Run `migrate_media_to_s3 --dry-run` and verify the planned uploads list looks correct.
       - [ ] Force-expire the cached access token (set `cached_access_token_expires_at` to the past in admin); trigger an email; verify the helper refreshes silently and the email still sends.
       - [ ] Visit `/staff/users/` as a Super User; create a new Admin user; verify they receive the welcome email; sign in as the new user and verify they have Admin-only navigation.
       - [ ] Promote the new Admin to Super User via the UI; verify the role-change email arrives and a `UserRoleChangeLog` row was created.
       - [ ] Try to demote yourself in `/staff/users/`; verify the action button is disabled.
       - [ ] Create a second Super User, then attempt to demote/deactivate/delete the first one while logged in as the second; verify it works. Then attempt to do the same when only one active Super User remains; verify the documented refusal banner appears.
       - [ ] Delete a user via `/staff/users/<id>/delete/`; verify the username-typing confirmation gate works.
       - [ ] Verify the `Manage users` sidebar link does not appear for an Admin (non-Super-User) account.

---

## 8. Testing Requirements

### 8.1 Mandatory Unit Tests

- `test_ms_oauth.py` — token caching, refresh on expiry, refresh token rotation, `invalid_grant` handling, singleton enforcement, encryption (§1.9.12).
- `test_email_backend.py` — XOAUTH2 string format, base64 encoding, error on non-235 response (§1.9.12).
- `test_check_emails.py` — every parser branch in §1.3, plus the XOAUTH2 IMAP login path with a retry-on-failure mock.
- `test_broadcast.py` — view permissions, rate limit, log creation, recipient parsing, attachment size cap, mandatory image attachment, View on TRACE link present in body.
- `test_claim_wording.py` — checkbox required, attestation rendered with name, modal confirmation, post-submit banner content.
- `test_magic_link.py` — per §4.8.
- `test_user_management.py` — per §6.14 (permissions, safeguards, role-change log creation, email dispatch, last-superuser protection, self-action prevention).
- `test_storage.py` — per §5.8 (uses `moto`).
- `test_wording_audit.py` — per §8.1 (regex word boundaries, AST literal scan, per-file allowlist).
- `test_wording_audit.py` — opens every file matching `templates/inventory/**/*.html` (recursive glob) and asserts that none of a list of **banned phrase patterns** match. The list is defined as compiled regexes with `\b` word boundaries and case-insensitive flag, **not** raw substring containment. This avoids false positives like `"come collect"` matching innocent text containing `"become collected"` or similar. The banned patterns are:

  ```python
  BANNED_PATTERNS = [
      re.compile(r"\bcome\s+collect\b",      re.IGNORECASE),
      re.compile(r"\bcome\s+(get|grab|pick)\b", re.IGNORECASE),
      re.compile(r"\bpick\s+(it|them|your\s+\w+)\s+up\b", re.IGNORECASE),
      re.compile(r"\bgrab\s+(it|them|your\s+\w+)\b", re.IGNORECASE),
      re.compile(r"\byour\s+stuff\b",        re.IGNORECASE),
      re.compile(r"\byour\s+things\b",       re.IGNORECASE),
      re.compile(r"\bcontact\s+us\b",        re.IGNORECASE),
      re.compile(r"\bwe['']ll\s+let\s+you\s+know\b", re.IGNORECASE),
      re.compile(r"\blost\s+something\??\b", re.IGNORECASE),
      re.compile(r"\bfound\s+something\??\b", re.IGNORECASE),
  ]
  ```

  **Scoping rules:**
  - Only scan files under `templates/inventory/` and `templates/registration/`. Do **not** scan `templates/base.html` (legacy Bootstrap, out of scope).
  - Do **not** scan static asset bodies (JS/CSS in `staticfiles/`) — too many false positives from third-party libraries.
  - The test must also walk text strings in `inventory/views.py`, `inventory/forms.py`, and `inventory/models.py` for the same patterns (string literals only, parsed via `ast` — do not regex against the raw source, since variable names and comments can contain matches that are not user-facing).
  - The test must run in **under 2 seconds**. Walk efficiently, cache compiled regexes.

  **Per-file allowlist:** maintain a module-level dict `ALLOWED_EXCEPTIONS = {filename: [pattern_strings]}` that whitelists specific known-good phrasings on a per-file basis. Start empty; entries are added only when a legitimate use case requires a banned phrase (extremely rare). Each entry must include a comment explaining why.

  **On failure:** the test must report the **file path, line number, the matched substring, and the surrounding 80 characters of context** so the next contributor can find and fix the issue immediately. Do not just report "banned phrase found in templates/" — that is unhelpful.

  This test is a regression guard. The point is that the next contributor cannot accidentally reintroduce vague wording without the test failing loudly and informatively.

### 8.2 Coverage

No formal threshold required, but every new view, model method, parsing branch, and storage code path must have at least one test.

### 8.3 Manual Test Script

Document the manual checklist (from §7 step 15) in `MANUAL_TESTS.md` at repo root.

---

## 9. Acceptance Criteria

This iteration is complete when **all** of the following are true:

1. The Microsoft 365 OAuth2 flow is fully working: `microsoft_oauth_setup` captures a refresh token, the `MicrosoftOAuthToken` row exists with an encrypted refresh token, and outbound emails sent via Django's email API arrive successfully at a TISB inbox using XOAUTH2 (no basic-auth fallback in production).
2. The `check_emails` command authenticates to IMAP via XOAUTH2 and successfully polls the configured mailbox; transient `AUTHENTICATIONFAILED` triggers a single `force_refresh()` retry before raising.
3. A student emailing `LF_EMAIL_ADDRESS` from a `@tisb.ac.in` address with a subject, body, and attachments produces an approval-queue entry within one `check_emails` cycle.
4. The student receives an automated acknowledgment email within the same cycle.
5. A Super User can approve the entry; the student receives an approval email with the exact wording in §3.5.1.
6. A Super User can click Broadcast, sees a confirmation page rendering the exact email, ticks the confirmation checkbox, sends, and recipients in `LF_BROADCAST_RECIPIENTS_LIST` receive the email with attachments formatted per §2.6, including a working absolute "View on TRACE" URL in the body.
7. `BroadcastLog` records every broadcast attempt, success or failure.
8. A student attempting to claim an item without ticking the attestation checkbox cannot submit (server-side validation too, not just JS).
9. The attestation checkbox label dynamically reflects the typed name.
10. Every page on the site is free of the banned phrase patterns listed in §8.1, verified by `test_wording_audit.py` which scans `templates/inventory/`, `templates/registration/`, and string literals in `inventory/views.py`, `inventory/forms.py`, `inventory/models.py`.
11. `WORDING_AUDIT.md` exists and lists every string change.
12. A student visiting `/my-reports/`, entering their TISB email, and clicking the emailed link is signed in for 24 hours and sees only their own reports and claims.
13. The `/my-reports/` page renders with the public/minimal sidebar regardless of whether the viewer is also signed in as a staff user (§4.6).
14. Magic-link tokens are single-use within their 24-hour window and rate-limited to 3 requests per email per hour.
15. With `MEDIA_BACKEND=s3` and required AWS vars set, uploaded item and student-lost-item images are stored in the configured bucket and rendered via the bucket's public URL or `AWS_S3_CUSTOM_DOMAIN`.
16. With `MEDIA_BACKEND=local` (or unset), everything works exactly as before — no regression for local development.
17. `migrate_media_to_s3` successfully uploads existing local files to the bucket (verified in `--dry-run` and a real run).
18. `Item.approved_by` and `Item.approved_at` are populated for all newly approved items, and existing approved items have been backfilled with `created_by` / `created_at` via the data migration (§2.10).
19. A Super User can visit `/staff/users/`, see a clean Tailwind table of all users with role badges, and perform all of: create a new staff user, edit profile, promote/demote between Admin and Super User, deactivate/reactivate, set a new password, and delete a user — all from within the new UI without ever opening Django admin.
20. Every action in the user management UI creates a corresponding `UserRoleChangeLog` row inside the same transaction, with accurate `target_user`, `performed_by`, `action`, and `details` (including before/after flag transitions).
21. All §6.6 safeguards are enforced server-side: self-action prevention, last-active-Super-User protection, `is_superuser=True` always pairs with `is_staff=True`, `@tisb.ac.in` email validation on create/edit, case-insensitive username uniqueness, Django password validators on set-password.
22. The affected user receives the correct email notification (§6.10) on creation, every role change, deactivation/reactivation, and password reset; emails are dispatched asynchronously and match the verbatim wording in §6.10.
23. The Django admin User list page displays a banner pointing users to `/staff/users/` (§6.13).
24. The `Manage users` sidebar link is visible to Super Users only.
25. All tests pass.
26. README has updated env-var table, `## Microsoft 365 OAuth setup`, `## Email polling`, `## Media storage (S3 / R2)`, `## Magic-link sign-in`, `## Staff user management`, `## Emergency recovery`, and `## Roadmap` sections.
27. No regression in existing functionality: item upload, AI analysis, claim flow, approval, primary years list, admin dashboard, login, Django admin restriction all still work.

---

## 10. Non-Goals (Explicitly Out of Scope for This Iteration)

- Password reset / SSO integration for staff.
- REST API.
- WebSockets / real-time notifications.
- Replacing Tailwind CDN with a compiled build.
- Replacing `base.html` (Bootstrap legacy).
- Adding new categories or changing the category list.
- Migrating from Google Gemini to another vision model.
- A student-facing "I think this is mine" matching workflow between found items and student lost items. (Flagged in §11 below.)
- Migrating static files to S3 (WhiteNoise stays for static).
- Procfile / Dockerfile creation.

---

## 11. Future Iterations (Document, Do Not Build)

Add a `## Roadmap` section to `README.md` listing:

- **Match suggestions:** for each new approved student lost item, run a similarity check against approved found items (image + text embedding) and surface suggested matches in the approval queue.
- **Two-way email threading:** allow staff replies from within TRACE that thread back to the original student email.
- **Reception kiosk / collection log:** separate `Collected` state from `Claimed`. Staff marks an item as collected at reception, recording who collected, who released, when. Closes the audit loop that the precise wording in §3 promises.
- **Bulk broadcast digest:** opt-in weekly digest instead of one broadcast per item.
- **Audit log export:** CSV export of `BroadcastLog`, `Claim`, `MagicLinkRequest`, and approval actions for end-of-term review.
- **Image deduplication:** perceptual hash on upload to flag possible duplicates.
- **Public claim rate limiting:** `django-ratelimit` on the claim endpoint, keyed on IP + email.
- **Analytics dashboard:** items logged per week, claim rate by category, average time-to-claim, hotspot locations.
- **CI:** GitHub Actions running tests on every PR.

---

## 12. Conventions & House Rules for Claude Code

- **New dependencies allowed in this iteration:** `bleach` (HTML stripping in `check_emails`, if needed), `django-storages[boto3]` (object storage), `moto` (dev only), `msal>=1.28.0` (Microsoft OAuth2), `cryptography>=42.0.0` (Fernet encryption for refresh tokens). No others without explicit instruction.
- **Do not** modify `inventory/services.py` (Gemini integration) in this iteration.
- **Do not** change the Tailwind CDN setup.
- **Do not** touch `templates/base.html` (legacy Bootstrap).
- **Match existing code style**: CBVs where the module uses CBVs, FBVs where it uses FBVs.
- **Reuse existing helpers**: `is_super_user`, `is_admin`, `SuperUserRequiredMixin`, `AdminOrSuperUserRequiredMixin`, `StaffRequiredMixin`, the async email thread sender. Extend in place rather than forking.
- **All new templates** use Tailwind + Inter + dark sidebar layout consistent with existing pages. Extract a `_sidebar.html` partial from `item_list.html` as part of this iteration if one does not already exist (in scope).
- **Timezone**: store everything in UTC (Django default); render in IST (`Asia/Kolkata`) wherever a human sees a timestamp. Add a `to_ist` template filter in `inventory/templatetags/inventory_extras.py` if absent.
- **All new user-facing strings** must live in templates or in views as constants — do not hard-code them inside JavaScript.
- **Commits**: small, focused, conventional-commits style (`feat(broadcast): add BroadcastLog model`, `fix(check_emails): handle empty subject`, `feat(my-reports): add magic-link sign-in`, `feat(storage): add S3 backend switch`, `chore(wording): rewrite claim flow strings`).
- **Logging**: use `logging.getLogger("inventory.<module>")` consistently. Do not introduce `print()` in production code paths.
- **Migrations**: each logical model change in its own migration where possible. Always provide a default for new non-nullable fields so existing rows do not break.

---

## 13. Quick Reference: All New / Changed Files Expected

### New files
- `inventory/constants.py` — `NEEDS_REVIEW_REASONS` and other shared constants (§1.3.7).
- `inventory/ms_oauth.py` — Microsoft OAuth2 token helper (§1.9.7).
- `inventory/email_backends.py` — `MicrosoftOAuth2EmailBackend` (§1.9.8).
- `inventory/checks.py` — Django system checks for OAuth configuration (§1.9.10).
- `inventory/magic_links.py` — token signing/verifying helpers.
- `inventory/management/commands/microsoft_oauth_setup.py` — one-time interactive OAuth setup (§1.9.5).
- `inventory/management/commands/migrate_media_to_s3.py`
- `inventory/tests/test_ms_oauth.py`
- `inventory/tests/test_email_backend.py`
- `inventory/tests/test_check_emails.py`
- `inventory/tests/test_broadcast.py`
- `inventory/tests/test_claim_wording.py`
- `inventory/tests/test_magic_link.py`
- `inventory/tests/test_user_management.py`
- `inventory/tests/test_storage.py`
- `inventory/tests/test_wording_audit.py`
- `inventory/templatetags/inventory_extras.py` (if absent)
- `templates/inventory/_sidebar.html` (extracted partial)
- `templates/inventory/_sidebar_public.html` (always-public variant for `/my-reports/`, §4.6)
- `templates/inventory/broadcast_confirm.html`
- `templates/inventory/broadcast_history.html`
- `templates/inventory/how_to_report.html`
- `templates/inventory/my_reports_signin.html`
- `templates/inventory/my_reports_link_sent.html`
- `templates/inventory/my_reports_link_invalid.html`
- `templates/inventory/my_reports_dashboard.html`
- `templates/inventory/user_management/list.html`
- `templates/inventory/user_management/create.html`
- `templates/inventory/user_management/detail.html`
- `templates/inventory/user_management/edit.html`
- `templates/inventory/user_management/set_password.html`
- `templates/inventory/user_management/role_change_history.html`
- `templates/inventory/user_management/_confirm_modal.html`
- `templates/inventory/email/broadcast_student_lost.html`
- `templates/inventory/email/broadcast_found_item.html`
- `templates/inventory/email/user_welcome.html`
- `templates/inventory/email/user_role_change.html`
- `templates/inventory/email/user_password_reset.html`
- `WORDING_AUDIT.md`
- `MANUAL_TESTS.md`
- `README.md` (create or update)
- `requirements-dev.txt` (create if absent — for `moto`)
- Migrations `0011_*.py` through `0015_*.py` as needed.

### Changed files
- `inventory/models.py` — new fields on `StudentLostItem` and `Item`, new `BroadcastLog`, new `MagicLinkRequest`, new `MicrosoftOAuthToken`, new `UserRoleChangeLog`.
- `inventory/views.py` — new views; updated claim view (server-side attestation validation); updated approve/reject views to set `Item.approved_by`/`approved_at`/`rejection_reason`; new `UserManagement*` views (§6.4).
- `inventory/urls.py` — new routes (broadcast, my-reports, how-to-report, staff/users).
- `inventory/admin.py` — register new models, expose new fields read-only, custom display for `MicrosoftOAuthToken` (never show encrypted refresh token; add "Revoke and clear token" action), add deprecation banner on User admin pointing to `/staff/users/`.
- `inventory/forms.py` — claim form: attestation checkbox, server-side validation; new `UserCreateForm`, `UserEditForm`, `UserSetPasswordForm` enforcing §6.6.
- `inventory/signals.py` — verify HEIC conversion fires for `StudentLostItemImage`; extend if not.
- `inventory/apps.py` — register the new Django system check from `inventory/checks.py`.
- `inventory/management/commands/check_emails.py` — full hardening per §1.3, plus XOAUTH2 IMAP login per §1.9.9.
- `lost_and_found_project/settings.py` — new env vars, `MEDIA_BACKEND` switch, OAuth-aware `EMAIL_BACKEND` selection.
- Every template under `templates/inventory/` — wording sweep; sidebar partial gets a Super-User-only `Manage users` link.
- `requirements.txt` — add `bleach` (if used), `django-storages[boto3]`, `msal>=1.28.0`, `cryptography>=42.0.0`.

---

**End of project_goals.md**
