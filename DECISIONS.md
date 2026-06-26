# Business Decisions

<!-- Decisions about product scope, priorities, stakeholder requirements, and business rules. -->

## Iteration scope: six pillars
- **Decision:** This iteration includes exactly 6 pillars: (1) Email Submission hardening, (2) Broadcast to School Body, (3) Precise Wording Overhaul, (4) Magic Link My Reports, (5) Object Storage S3/R2, (6) Staff User Management UI. All are mandatory.
- **Date:** 2026-06-24
- **Reasoning:** Defined in PROJECT_GOALS.md §0
- **Source:** PROJECT_GOALS.md

## Target school and email domain
- **Decision:** TISB (The International School Bangalore). All student/staff emails must be `@tisb.ac.in`. The initial mailbox is `raadvait@tisb.ac.in`.
- **Date:** 2026-06-24
- **Reasoning:** School-specific deployment
- **Source:** PROJECT_GOALS.md

## Broadcast recipients (initial)
- **Decision:** `raadvait@tisb.ac.in`, `nsiddharth@tisb.ac.in`
- **Date:** 2026-06-24
- **Reasoning:** Initial test recipients
- **Source:** PROJECT_GOALS.md §2.2

# Product Decisions

<!-- Decisions about features, user flows, wording, and behavior visible to end users. -->

## Claim attestation checkbox is mandatory
- **Decision:** Claims require a checked attestation checkbox with dynamic name insertion. Server-side validation required, not just JS.
- **Date:** 2026-06-24
- **Reasoning:** Prevents false claims and exploitation per §3.1
- **Source:** PROJECT_GOALS.md §3.1

## Magic link is single-use within 24h window
- **Decision:** Each magic link token can be used exactly once. After use, requesting the same link shows "already used" message.
- **Date:** 2026-06-24
- **Reasoning:** Security — prevents link sharing/forwarding abuse
- **Source:** PROJECT_GOALS.md §4.5.3

## My Reports page always shows public sidebar
- **Decision:** `/my-reports/` renders with public/minimal sidebar regardless of whether viewer is also a staff user.
- **Date:** 2026-06-24
- **Reasoning:** Prevents confusion between student self-service and staff trust contexts
- **Source:** PROJECT_GOALS.md §4.6

# Technical Decisions

<!-- Decisions about architecture, libraries, patterns, data models, and implementation approach. -->

## Is the Discord HITL system online and operational?
- **Decision:** Option A: Yes
- **Date:** 2026-06-23
- **Reasoning:** Decided via Discord
- **Source:** user (djhamburger) via Discord

## OAuth2 flow: Authorization Code with refresh tokens (not Client Credentials)
- **Decision:** Use Authorization Code Flow + refresh tokens (delegated user access) for Microsoft 365 OAuth2. Client Credentials Flow documented as future option.
- **Date:** 2026-06-24
- **Reasoning:** Only requires mailbox owner consent (Advait clicking through a browser); does not require school IT admin involvement. Feasibility-driven.
- **Source:** PROJECT_GOALS.md §1.9.2

## OAuth must precede all email work
- **Decision:** Microsoft 365 OAuth2 foundation (§1.9) must be implemented before any email-sending or IMAP features.
- **Date:** 2026-06-24
- **Reasoning:** Basic auth is fully deprecated on Microsoft 365. Without OAuth2, no email functionality works against the TISB mailbox.
- **Source:** PROJECT_GOALS.md §1.9

## MicrosoftOAuthToken is a singleton model
- **Decision:** Only one `MicrosoftOAuthToken` row allowed in the database. Enforced in `save()`.
- **Date:** 2026-06-24
- **Reasoning:** Single mailbox architecture
- **Source:** PROJECT_GOALS.md §1.9.6

## Refresh token encrypted at rest with Fernet
- **Decision:** Refresh tokens stored encrypted via `MS_OAUTH_TOKEN_ENCRYPTION_KEY` (Fernet). Access tokens stored in cleartext (1h expiry, useless without client secret).
- **Date:** 2026-06-24
- **Reasoning:** Refresh token is the long-lived secret
- **Source:** PROJECT_GOALS.md §1.9.6

## Token signing for magic links uses Django TimestampSigner
- **Decision:** No extra DB model for the token itself. `django.core.signing.TimestampSigner` with `max_age=86400`.
- **Date:** 2026-06-24
- **Reasoning:** Simpler than DB-stored tokens; self-verifying signed payload
- **Source:** PROJECT_GOALS.md §4.2

## S3 backend via django-storages[boto3]
- **Decision:** Use `django-storages[boto3]` with `MEDIA_BACKEND` env var switch (local/s3). Cloudflare R2 recommended for zero egress cost.
- **Date:** 2026-06-24
- **Reasoning:** Endpoint-agnostic S3 implementation
- **Source:** PROJECT_GOALS.md §5.2

## New dependencies allowed
- **Decision:** `bleach`, `django-storages[boto3]`, `moto` (dev only), `msal>=1.28.0`, `cryptography>=42.0.0`. No others without explicit instruction.
- **Date:** 2026-06-24
- **Reasoning:** Scoped dependency additions per §12
- **Source:** PROJECT_GOALS.md §12

# UI/UX Decisions

<!-- Decisions about design, layout, styling, interaction patterns, and accessibility. -->

## Broadcast button style
- **Decision:** Cyan-to-purple gradient pill, white text, megaphone icon. Already-broadcast items show muted slate pill with resend link.
- **Date:** 2026-06-24
- **Reasoning:** Matches existing UI conventions
- **Source:** PROJECT_GOALS.md §2.5

## User management list: role-colored badges
- **Decision:** Purple = Super User, Cyan = Admin, Amber = Deactivated, Slate = No staff access
- **Date:** 2026-06-24
- **Reasoning:** Consistent with existing badge color conventions
- **Source:** PROJECT_GOALS.md §6.7

## Delete user requires username typing confirmation
- **Decision:** Same pattern as GitHub repo deletion — must type username before Confirm button enables.
- **Date:** 2026-06-24
- **Reasoning:** Prevents accidental deletion
- **Source:** PROJECT_GOALS.md §6.9.3

# Infrastructure Decisions

<!-- Decisions about deployment, hosting, storage, CI/CD, environment configuration, and ops. -->

## Email polling schedule
- **Decision:** `check_emails` recommended at every 2 minutes via Railway cron
- **Date:** 2026-06-24
- **Reasoning:** Balances responsiveness with API limits
- **Source:** PROJECT_GOALS.md §1.8

## No Procfile/Dockerfile this iteration
- **Decision:** Railway continues to use runtime detection. No containerization in scope.
- **Date:** 2026-06-24
- **Reasoning:** Out of scope
- **Source:** PROJECT_GOALS.md §0.5.8

# Future Decisions

<!-- Decisions deferred to a later iteration, recorded here so they are not re-asked. -->

## Client Credentials Flow for OAuth
- **Deferred to:** Future iteration
- **Reasoning:** Requires school IT admin involvement (PowerShell commands). Authorization Code Flow is sufficient for now.
- **Source:** PROJECT_GOALS.md §1.9.2

## Match suggestions (AI-powered item matching)
- **Deferred to:** Future iteration
- **Source:** PROJECT_GOALS.md §11

## Reception kiosk / collection log
- **Deferred to:** Future iteration
- **Source:** PROJECT_GOALS.md §11

## CI/CD (GitHub Actions)
- **Deferred to:** Future iteration
- **Source:** PROJECT_GOALS.md §11
