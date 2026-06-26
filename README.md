# TRACE -- TISB Lost & Found

TRACE is a lost-and-found management system built for The International School Bangalore (TISB). Staff photograph found items, the system uses Gemini Vision AI to auto-describe them, and students can report lost items via email. The platform handles matching, claiming, broadcasting, and archival of items across primary and secondary school divisions.

**Stack:** Django 4.2, Tailwind CSS, Google Gemini Vision AI, SQLite (dev), PostgreSQL (prod/Railway).

---

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The app will be available at `http://localhost:8000`.

---

## Environment Variables

### Core Django

| Variable | Purpose | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Secret key | `dev-secret-key-change-me` |
| `DJANGO_DEBUG` | Debug mode (`1` or `0`) | `1` |
| `DATABASE_URL` | PostgreSQL URL (prod) | SQLite in dev |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated CSRF trusted origins | -- |
| `RAILWAY_PUBLIC_DOMAIN` | Railway domain (auto-detected) | -- |

### Email (SMTP Outbound)

| Variable | Purpose | Default |
|---|---|---|
| `EMAIL_HOST` | SMTP server | `smtp-mail.outlook.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_HOST_USER` | SMTP user | -- |
| `EMAIL_HOST_PASSWORD` | Unused under OAuth2 | -- |
| `EMAIL_USE_TLS` | Use TLS | `True` |
| `DEFAULT_FROM_EMAIL` | Fallback from address | -- |

### Email (IMAP Inbound)

| Variable | Purpose | Default |
|---|---|---|
| `LF_EMAIL_ADDRESS` | Mailbox address | -- |
| `LF_EMAIL_PASSWORD` | Unused under OAuth2 | -- |
| `LF_IMAP_HOST` | IMAP server | `outlook.office365.com` |
| `LF_IMAP_PORT` | IMAP port | `993` |
| `LF_IMAP_MAILBOX` | IMAP folder | `INBOX` |
| `LF_ALLOWED_SENDER_DOMAIN` | Allowed sender domain | `@tisb.ac.in` |
| `LF_EMAIL_DISPLAY_NAME` | Display name for outgoing emails | `TRACE Lost & Found` |
| `LF_BROADCAST_RECIPIENTS` | Comma-separated broadcast recipients | -- |

### Microsoft 365 OAuth2

| Variable | Purpose | Default |
|---|---|---|
| `MS_OAUTH_TENANT_ID` | Azure AD tenant ID or `common` | -- |
| `MS_OAUTH_CLIENT_ID` | Azure AD app client ID | -- |
| `MS_OAUTH_CLIENT_SECRET` | Azure AD client secret | -- |
| `MS_OAUTH_SCOPES` | Space-separated scopes | default scopes |
| `MS_OAUTH_REDIRECT_URI` | OAuth redirect URI | `http://localhost:8765/oauth/callback` |
| `MS_OAUTH_AUTHORITY` | Authority URL | derived from tenant |
| `MS_OAUTH_TOKEN_ENCRYPTION_KEY` | Fernet key for refresh token encryption | -- |

### Magic Link

| Variable | Purpose | Default |
|---|---|---|
| `MAGIC_LINK_SECRET` | Signing secret for magic links | Django `SECRET_KEY` |
| `MAGIC_LINK_BASE_URL` | Base URL for links in emails | derived from request |

### Media Storage (S3 / R2)

| Variable | Purpose | Default |
|---|---|---|
| `MEDIA_BACKEND` | `local` or `s3` | `local` |
| `AWS_ACCESS_KEY_ID` | S3 access key | required if s3 |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key | required if s3 |
| `AWS_STORAGE_BUCKET_NAME` | Bucket name | required if s3 |
| `AWS_S3_ENDPOINT_URL` | S3 endpoint (for R2) | -- |
| `AWS_S3_REGION_NAME` | Region | `auto` |
| `AWS_S3_CUSTOM_DOMAIN` | Custom domain for media URLs | -- |

### AI

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini Vision API key | -- |

### Auto Superuser (Railway)

| Variable | Purpose | Default |
|---|---|---|
| `CREATE_SUPERUSER` | Auto-create superuser on deploy (`true`) | -- |
| `DJANGO_SUPERUSER_USERNAME` | Superuser username | -- |
| `DJANGO_SUPERUSER_EMAIL` | Superuser email | -- |
| `DJANGO_SUPERUSER_PASSWORD` | Superuser password | -- |

---

## Microsoft 365 OAuth Setup

These instructions are for the deployer setting up the production email integration.

1. **Enable IMAP:** In the Outlook.com web UI, go to Settings > Mail > Forwarding and IMAP, toggle "Let devices and apps use IMAP" to ON.

2. **Register an Azure AD app:**
   - Sign in to https://portal.azure.com
   - Navigate to Microsoft Entra ID > App registrations > New registration
   - Name: `TRACE Lost and Found`
   - Supported account types: Accounts in any organizational directory and personal Microsoft accounts
   - Redirect URI: Web, `http://localhost:8765/oauth/callback`
   - Copy Application (client) ID -> `MS_OAUTH_CLIENT_ID`
   - Copy Directory (tenant) ID -> `MS_OAUTH_TENANT_ID`

3. **Create a client secret:**
   - Certificates & secrets > Client secrets > New client secret
   - Copy the Value -> `MS_OAUTH_CLIENT_SECRET`

4. **Add API permissions:**
   - API permissions > Add permission > Microsoft Graph > Delegated
   - Add: `IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access`, `User.Read`, `openid`, `profile`, `email`
   - Grant admin consent if you are a tenant admin

5. **Generate an encryption key:**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Set this as `MS_OAUTH_TOKEN_ENCRYPTION_KEY`.

6. **Run the setup command:**
   ```bash
   python manage.py microsoft_oauth_setup
   ```
   This opens a browser for one-time sign-in. The refresh token is stored encrypted in the database.

**Future option (Client Credentials Flow):** For more robust long-term access without refresh token expiry concerns, a tenant admin can set up Client Credentials Flow. This is not implemented in the current iteration.

---

## Email Polling

```bash
python manage.py check_emails          # Run once
python manage.py check_emails --loop   # Poll continuously (every 2 minutes)
```

Recommended: set up a Railway cron job to run `python manage.py check_emails` every 2 minutes.

The command polls the configured IMAP mailbox, parses student emails, creates `StudentLostItem` entries, and sends acknowledgment emails.

---

## Media Storage (S3 / R2)

By default, media files are stored locally in `media/`. For production, configure S3-compatible storage.

**Recommended provider:** Cloudflare R2 (zero egress cost).

1. Set up a bucket with public-read access for `item_images/` and `student_item_images/` prefixes
2. Create an API token with Object Read & Write on the bucket
3. Set environment variables: `MEDIA_BACKEND=s3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`
4. Deploy and verify image uploads work

**Migrating existing files:**

```bash
python manage.py migrate_media_to_s3 --dry-run   # Preview
python manage.py migrate_media_to_s3              # Upload
```

**Rollout plan:**

1. Provision R2 bucket and credentials
2. Set env vars in Railway
3. Set `MEDIA_BACKEND=s3`
4. Deploy
5. Run `python manage.py migrate_media_to_s3`
6. Verify images render correctly

---

## Magic-Link Sign-In

Students can view their reports and claims at `/my-reports/` using a passwordless email link.

- Student enters their `@tisb.ac.in` email
- System sends a one-time link valid for 24 hours
- Link is single-use; second click shows "already used"
- Magic-link sessions never grant staff permissions

---

## Staff User Management

Super Users can manage staff accounts at `/staff/users/`:

- Create, edit, deactivate staff users
- Promote/demote between Admin and Super User roles
- Reset passwords
- View role change audit log
- Safeguards prevent accidental lockout (can't demote yourself, can't remove the last Super User)

---

## Emergency Recovery

If all Super User accounts are locked out, use the CLI:

```bash
python manage.py promote_superuser <username>
```

---

## Running Tests

```bash
python manage.py test inventory.tests
```

For development dependencies (including moto for S3 mocking):

```bash
pip install -r requirements-dev.txt
```

---

## Roadmap

Future iterations (documented, not built):

- **Match suggestions:** AI-powered similarity check between lost and found items
- **Two-way email threading:** staff replies threading back to student emails
- **Reception kiosk / collection log:** separate "Collected" state from "Claimed"
- **Bulk broadcast digest:** weekly digest instead of per-item broadcasts
- **Audit log export:** CSV export of all logs for end-of-term review
- **Image deduplication:** perceptual hash on upload
- **Public claim rate limiting:** per IP + email rate limiting
- **Analytics dashboard:** items per week, claim rates, hotspot locations
- **CI:** GitHub Actions running tests on every PR
