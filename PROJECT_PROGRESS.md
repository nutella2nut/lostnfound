# PROJECT_PROGRESS.md

## Completed

### Base System (pre-iteration — already working)
- [x] Django project structure and config
- [x] Item model with full fields, categories, approval workflow
- [x] Claim model with multi-claim support
- [x] StudentLostItem and StudentLostItemImage models
- [x] Item upload with multi-image + AI auto-fill (Gemini Vision)
- [x] Browse views: Landing, Senior Years, Primary Years, Students' Lost Items
- [x] Item detail with image carousel/gallery
- [x] Claim flow (name + email)
- [x] Approval queue for pending items
- [x] Admin Dashboard with claim notifications
- [x] HEIC-to-JPEG conversion (pre_save signal on ItemImage)
- [x] Email submissions via `check_emails` IMAP command (basic implementation)
- [x] Async email sending (background thread)
- [x] Mobile responsive dark sidebar layout
- [x] SuperUserOnlyAdminSite
- [x] Railway deployment support
- [x] 10 migrations (0001–0010)
- [x] Basic tests: test_models (1), test_forms (2), test_views (5), test_vision (2)
- [x] Logging infrastructure added

### This Iteration — Completed Items

#### Models & Migrations (all pillars)
- [x] Add `Item.approved_by`, `Item.approved_at`, `Item.rejection_reason` fields (§2.10)
- [x] Add `StudentLostItem.submitter_display_name`, `needs_review_reason`, `rejection_reason`, `source_message_id` (§1.3)
- [x] Create `MicrosoftOAuthToken` model (§1.9.6)
- [x] Create `BroadcastLog` model (§2.3)
- [x] Create `MagicLinkRequest` model (§4.3)
- [x] Create `UserRoleChangeLog` model (§6.5)
- [x] Migration `0011_add_item_audit_fields.py`
- [x] Data migration `0012_backfill_item_approval_fields.py` (backfills approved_by/approved_at)
- [x] Register all new models in admin.py
- [x] HEIC signal registered for `StudentLostItemImage` (was missing)

#### Pillar 1 prerequisite: Microsoft 365 OAuth2 (§1.9) — DONE
- [x] Add `msal` and `cryptography` to requirements.txt
- [x] `MicrosoftOAuthToken` model + migration
- [x] `inventory/ms_oauth.py` token helper
- [x] `inventory/email_backends.py` — `MicrosoftOAuth2EmailBackend`
- [x] `microsoft_oauth_setup` management command
- [x] Django system check for OAuth config (`inventory/checks.py`)
- [x] Settings.py: OAuth env vars, EMAIL_BACKEND switch
- [x] Tests: `test_ms_oauth.py` (8 tests), `test_email_backend.py` (3 tests)

#### Pillar 1: check_emails Hardening (§1.3) — DONE (backend logic)
- [x] XOAUTH2 IMAP login in `check_emails` with retry on AUTHENTICATIONFAILED
- [x] Harden `check_emails` parser (subject/body/attachment rules per §1.3)
- [x] Create `inventory/constants.py` with `NEEDS_REVIEW_REASONS`
- [x] EXIF GPS stripping on images
- [x] Deduplication via `source_message_id` (with hash fallback)
- [x] Acknowledgment email (normal + oversized variants, §1.4)
- [x] `--loop` flag for continuous polling (§1.8)
- [x] Tests: `test_check_emails.py` (18 tests)

#### Pillar 1: Approval Queue UI (§1.6) — DONE
- [x] Tab toggle: Pending | Approved — not yet broadcast | All broadcasts
- [x] Submitter name display for student items
- [x] Amber pill for `needs_review_reason`
- [x] Enhanced details modal (title, description, images, submitter name/email, submitted-at, message-ID, needs_review_reason)
- [x] Rejection modal with optional reason textarea (max 500 chars)

#### Views & Forms — DONE (backend logic)
- [x] Update `ItemUploadView` — auto-set `approved_by`/`approved_at` for Super User uploads
- [x] Update `ApproveItemView` — set `approved_by`/`approved_at`, updated email wording (§3.5.1)
- [x] Update `RejectItemView` — store `rejection_reason`, updated email wording (§3.5.2)
- [x] Update `ClaimItemView` — attestation validation, precise claim email (§3.1.5), precise banner (§3.1.4)
- [x] Update `ClaimItemForm` — attestation checkbox, updated labels (§3.1.2)
- [x] All broadcast views (BroadcastItemView, BroadcastHistoryView)
- [x] HowToReportLostView
- [x] All magic link views (MyReportsView, RequestMagicLinkView, MagicLinkSignInView, MyReportsSignOutView)
- [x] All user management views (List, Create, Detail, Edit, SetPassword, Delete, RoleChangeHistory)
- [x] UserCreateForm, UserEditForm, UserSetPasswordForm
- [x] All new URL routes in urls.py

#### Pillar 2: Broadcast Buttons on All 4 Surfaces (§2.5) — DONE
- [x] Approval queue: broadcast buttons in "Approved — not yet broadcast" tab
- [x] Student lost items list: broadcast button on each card (Super Users only)
- [x] Student lost item detail: Super User action bar with broadcast button
- [x] Item detail (found items): Super User action bar with broadcast button

#### Pillar 2: Broadcast Email HTML Templates (§2.6) — DONE
- [x] `templates/inventory/email/broadcast_student_lost.html` (inline CSS)
- [x] `templates/inventory/email/broadcast_found_item.html` (inline CSS)
- [x] `BroadcastItemView.post()` sends HTML alternative via `EmailMultiAlternatives`

#### Pillar 3: Claim Flow Wording (§3.1, §3.2) — DONE
- [x] Claim form heading with attestation warning (§3.1.1)
- [x] Dynamic attestation checkbox with JS name insertion (§3.1.2)
- [x] Pre-submit confirmation modal (§3.1.3)
- [x] Submit button disabled until name + attestation valid
- [x] Claimed-state badges: "Claim submitted — awaiting collection" / "{n} claims submitted" (§3.2)
- [x] Claims section now staff-only with email shown

#### Pillar 3: Wording Sweep (Session 5) — DONE
- [x] Browse/landing/empty state wording sweep (§3.3)
- [x] Staff upload flow wording (§3.6) — all headings, labels, submit button updated
- [x] Footer disclaimer on every page (§3.7) — all templates
- [x] `WORDING_AUDIT.md` produced (§3.8)
- [x] `test_wording_audit.py` regression guard (§8.1) — 3 tests

#### Pillar 4: Magic Link "My Reports" — DONE
- [x] All views and templates
- [x] Public sidebar enforcement (§4.6) — My Reports pages use `_sidebar_public.html`
- [x] Tests: `test_magic_link.py` (12 tests)

#### Pillar 5: Object Storage for Media (S3/R2) — DONE
- [x] S3 MEDIA_BACKEND switch in settings.py (§5.3)
- [x] `migrate_media_to_s3` management command (§5.5)
- [x] `requirements-dev.txt` with moto
- [x] Tests: `test_storage.py` (2 tests)

#### Pillar 6: Staff User Management UI — DONE
- [x] All views, forms, templates
- [x] "Manage Users" sidebar link in ALL staff templates (Super User only)
- [x] Django admin deprecation banner on User list page (§6.13)
- [x] Tests: `test_user_management.py` (18 tests)

#### Templates — DONE
- [x] `broadcast_confirm.html`, `broadcast_history.html`
- [x] `how_to_report.html`
- [x] `my_reports_signin.html`, `my_reports_link_sent.html`, `my_reports_link_invalid.html`, `my_reports_dashboard.html`
- [x] `user_management/` (list, create, detail, edit, set_password, delete, role_change_history)
- [x] Email templates: `email/broadcast_student_lost.html`, `email/broadcast_found_item.html`

#### Cross-cutting (Sessions 5-6)
- [x] `inventory/templatetags/inventory_extras.py` — `to_ist` filter
- [x] `templates/inventory/_sidebar.html` — extracted staff sidebar partial
- [x] `templates/inventory/_sidebar_public.html` — public sidebar for My Reports (§4.6)
- [x] Sidebar replaced in 15+ staff templates with `{% include %}`
- [x] My Reports pages converted to dark sidebar layout with public sidebar

#### Dependencies
- [x] Added `bleach`, `django-storages[boto3]` to requirements.txt
- [x] S3 MEDIA_BACKEND switch in settings.py (§5.3)
- [x] New env vars in settings.py: LF_EMAIL_DISPLAY_NAME, LF_BROADCAST_RECIPIENTS_LIST, MAGIC_LINK_SECRET, MAGIC_LINK_BASE_URL

#### Documentation
- [x] `README.md` — full env var table + all sections
- [x] `MANUAL_TESTS.md` — manual smoke test checklist
- [x] `WORDING_AUDIT.md` — comprehensive wording audit

#### Tests — ALL PASSING (83/83)
- [x] test_wording_audit.py (3 tests) — passing
- [x] test_storage.py (2 tests) — passing
- [x] All prior tests (78) — passing

#### Final Pass
- [x] `manage.py check` — no issues
- [x] `makemigrations --check --dry-run` — no changes detected
- [x] All 83 tests pass

## In Progress

Nothing — all tasks complete.

## Remaining

Nothing — all 6 pillars and cross-cutting tasks complete.

## Known Issues

- `base.html` uses Bootstrap while all inventory templates use Tailwind — known quirk, do not fix
- No Procfile/Dockerfile — Railway uses runtime detection
- No CI configuration

## Technical Debt

- `item_list.html`, `primary_years_list.html`, `student_lost_items_list.html` still have inline sidebar HTML (not extracted to partial) because their sidebars have unique category/content layouts different from the staff sidebar partial
- Media files on ephemeral Railway filesystem until S3 switch is activated in production

## Recent Decisions

See DECISIONS.md for all recorded decisions.
