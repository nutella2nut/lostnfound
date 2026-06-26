# PROJECT_CONTEXT.md

## What Is This Project?

TRACE is a Lost & Found web application for TISB (The International School Bangalore). It is a Django 4.2 application that allows staff to log found items with AI-assisted image analysis (Google Gemini Vision), and students to browse, claim, and report lost items.

## Tech Stack

- **Backend:** Django 4.2, Python 3.9, Gunicorn (prod)
- **Database:** SQLite (dev), PostgreSQL via `dj-database-url` (prod/Railway)
- **Frontend:** Django templates + Tailwind CSS (CDN) + vanilla JS + Inter font
- **AI:** Google Gemini 2.5 Flash Vision API for image analysis (`inventory/services.py`)
- **Image Processing:** Pillow + pillow-heif for HEIC-to-JPEG conversion
- **Email:** Django SMTP (outbound), IMAP (inbound via `check_emails` management command)
- **Static Files:** WhiteNoise compressed manifest storage
- **Deployment:** Railway (auto-detected via env vars)

## Repository Layout

```
LostAndFoundSystem/
├── manage.py
├── requirements.txt
├── db.sqlite3
├── lost_and_found_project/       # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── inventory/                    # The single Django app
│   ├── models.py                 # UserProfile, Item, Claim, ItemImage, StudentLostItem, StudentLostItemImage
│   ├── views.py                  # All views (CBV + FBV mix)
│   ├── urls.py                   # namespace="inventory"
│   ├── forms.py
│   ├── admin.py                  # SuperUserOnlyAdminSite
│   ├── services.py               # Gemini Vision (DO NOT MODIFY)
│   ├── signals.py                # HEIC→JPEG pre_save
│   ├── apps.py
│   ├── context_processors.py     # is_super_user context
│   ├── management/commands/
│   │   ├── check_emails.py       # IMAP email poller
│   │   └── promote_superuser.py
│   ├── tests/                    # test_models, test_views, test_forms, test_vision
│   └── migrations/               # 0001–0010
├── templates/
│   ├── base.html                 # Legacy Bootstrap (DO NOT TOUCH)
│   └── inventory/                # All Tailwind templates (10 files)
├── automation/                   # Discord bot + agent integration
├── staticfiles/
├── media/
└── venv/
```

## Existing Models

| Model | Purpose |
|---|---|
| `UserProfile` | OneToOne to User. Minimal — roles use Django's `is_staff`/`is_superuser`. |
| `Item` | Found items logged by staff. Fields: title, description, location_found, date_found, status (FOUND/CLAIMED), category (7 choices), approval_status, item_type (SENIOR/PY), created_by, claimed_by_name, claimed_at. |
| `Claim` | Claims on items. Multiple per item. Fields: item (FK), claimant_name, claimant_email, claimed_at. |
| `ItemImage` | Images for found items. HEIC pre_save signal. |
| `StudentLostItem` | Email-sourced lost item reports. Fields: title, description, email_subject, email_from, submitted_at, approval_status, approved_by, approved_at. |
| `StudentLostItemImage` | Images for student-submitted lost items. |

## Roles & Permissions

- **Public:** Browse, view details, claim items
- **Admin** (`is_staff=True`, `is_superuser=False`): Upload items (PENDING), Admin Dashboard
- **Super User** (`is_superuser=True`): Everything + approvals + Django admin

## Existing URL Routes (namespace `inventory`)

Public: `/`, `/browse/`, `/primary-years/`, `/students-lost-items/`, `/items/<pk>/`, `/items/<pk>/claim/`, `/student-items/<pk>/`
Staff: `/staff/items/upload/`, `/staff/items/analyze/`, `/staff/dashboard/`, `/staff/approval-queue/`, `/staff/approve/<type>/<id>/`, `/staff/reject/<type>/<id>/`
Admin: `/admin/`, `/accounts/...`

## Key Existing Features

- Multi-image upload (up to 3) with AI auto-fill (Gemini Vision)
- Multi-image carousel on cards and galleries on detail pages
- Multi-claim system with category-specific auto-hide windows
- Approval workflow (Admin uploads = PENDING, Super User uploads = AUTO-APPROVED)
- Email submissions via IMAP poller (`check_emails`)
- HEIC-to-JPEG conversion via pre_save signal
- Admin Dashboard with claim notifications, modals, fullscreen image viewer
- Async email sending in background threads
- Mobile responsive with hamburger sidebar at xl breakpoint

## Existing Dependencies (requirements.txt)

django, pillow, pillow-heif, requests, dj-database-url, psycopg2-binary, gunicorn, whitenoise

## Constraints

- `templates/base.html` is legacy Bootstrap — DO NOT TOUCH
- `inventory/services.py` (Gemini Vision) — DO NOT MODIFY this iteration
- Tailwind CDN setup — DO NOT CHANGE
- Match existing code style (CBVs where CBVs, FBVs where FBVs)
- All new templates use Tailwind + Inter + dark sidebar layout
- Timestamps stored UTC, rendered IST (`Asia/Kolkata`)
