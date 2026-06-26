import os
from pathlib import Path
import importlib.util
from urllib.parse import urlparse
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
HAS_WHITENOISE = importlib.util.find_spec("whitenoise") is not None

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if os.environ.get("DJANGO_DEBUG", "1") == "1":
        SECRET_KEY = "dev-secret-key-DO-NOT-USE-IN-PRODUCTION"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# ALLOWED_HOSTS configuration
# Default hosts for local development
allowed_hosts_list = ["localhost", "127.0.0.1"]

# Add Railway domain if in production (when DATABASE_URL is set, we're likely on Railway)
if os.environ.get("DATABASE_URL"):
    # Railway uses *.up.railway.app domains
    # Add common Railway domain patterns
    allowed_hosts_list.append("lostnfound-production.up.railway.app")
    # Also allow any Railway domain via environment variable
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain and railway_domain not in allowed_hosts_list:
        allowed_hosts_list.append(railway_domain)

# Allow additional hosts via DJANGO_ALLOWED_HOSTS environment variable
env_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
if env_hosts:
    for host in env_hosts.split(","):
        host = host.strip()
        if host and host not in allowed_hosts_list:
            allowed_hosts_list.append(host)

ALLOWED_HOSTS: list[str] = allowed_hosts_list

# CSRF_TRUSTED_ORIGINS configuration
# Default origins for local development
csrf_trusted_origins_list = ["http://localhost:8000", "http://127.0.0.1:8000"]

# Check if we're on Railway (multiple indicators)
is_railway = (
    os.environ.get("DATABASE_URL") or 
    os.environ.get("RAILWAY_ENVIRONMENT") or
    os.environ.get("RAILWAY_PUBLIC_DOMAIN")
)

if is_railway:
    # Always add the specific production domain
    railway_prod_domain = "https://lostnfound-production.up.railway.app"
    if railway_prod_domain not in csrf_trusted_origins_list:
        csrf_trusted_origins_list.append(railway_prod_domain)
    
    # Also allow any Railway domain via environment variable
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        # Remove any trailing slashes and ensure it starts with https://
        railway_domain = railway_domain.strip().rstrip("/")
        railway_origin = railway_domain if railway_domain.startswith("http") else f"https://{railway_domain}"
        # Remove trailing slash if present
        railway_origin = railway_origin.rstrip("/")
        if railway_origin not in csrf_trusted_origins_list:
            csrf_trusted_origins_list.append(railway_origin)
    
    # Also check RAILWAY_STATIC_URL which might contain the domain
    railway_static = os.environ.get("RAILWAY_STATIC_URL", "")
    if railway_static:
        # Extract domain from static URL if it's a full URL
        if railway_static.startswith("http"):
            parsed = urlparse(railway_static)
            railway_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if railway_origin not in csrf_trusted_origins_list:
                csrf_trusted_origins_list.append(railway_origin)

# Allow additional origins via DJANGO_CSRF_TRUSTED_ORIGINS environment variable
env_origins = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if env_origins:
    for origin in env_origins.split(","):
        origin = origin.strip().rstrip("/")
        if origin:
            # Ensure it has a protocol
            if not origin.startswith("http"):
                origin = f"https://{origin}"
            if origin not in csrf_trusted_origins_list:
                csrf_trusted_origins_list.append(origin)

CSRF_TRUSTED_ORIGINS: list[str] = csrf_trusted_origins_list

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
]

if HAS_WHITENOISE:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")

MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lost_and_found_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "inventory.context_processors.user_permissions",
            ],
        },
    },
]

WSGI_APPLICATION = "lost_and_found_project.wsgi.application"

# Database configuration
# Use Railway PostgreSQL if DATABASE_URL is set, otherwise fall back to SQLite for local development
database_url = os.environ.get("DATABASE_URL")
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


if HAS_WHITENOISE:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media storage (§5)
MEDIA_BACKEND = os.environ.get("MEDIA_BACKEND", "local").lower()

if MEDIA_BACKEND == "s3":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto")
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=31536000, immutable"}
    AWS_QUERYSTRING_AUTH = False
else:
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

#
# Microsoft 365 OAuth2 configuration (§1.9)
#
MS_OAUTH_TENANT_ID = os.environ.get("MS_OAUTH_TENANT_ID", "")
MS_OAUTH_CLIENT_ID = os.environ.get("MS_OAUTH_CLIENT_ID", "")
MS_OAUTH_CLIENT_SECRET = os.environ.get("MS_OAUTH_CLIENT_SECRET", "")
MS_OAUTH_SCOPES = os.environ.get(
    "MS_OAUTH_SCOPES",
    "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access",
)
MS_OAUTH_REDIRECT_URI = os.environ.get("MS_OAUTH_REDIRECT_URI", "http://localhost:8765/oauth/callback")
MS_OAUTH_AUTHORITY = os.environ.get(
    "MS_OAUTH_AUTHORITY",
    f"https://login.microsoftonline.com/{MS_OAUTH_TENANT_ID}" if MS_OAUTH_TENANT_ID else "https://login.microsoftonline.com/common",
)
MS_OAUTH_TOKEN_ENCRYPTION_KEY = os.environ.get("MS_OAUTH_TOKEN_ENCRYPTION_KEY", "")

#
# Outgoing email configuration (SMTP)
# Uses OAuth2 XOAUTH2 when MS_OAUTH_CLIENT_ID is set, falls back to basic auth otherwise.
# Set EMAIL_BACKEND env var to override auto-detection.
#
if MS_OAUTH_CLIENT_ID:
    EMAIL_BACKEND = "inventory.email_backends.MicrosoftOAuth2EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp-mail.outlook.com")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_HOST_USER = os.environ.get("LF_EMAIL_ADDRESS", "")
    EMAIL_HOST_PASSWORD = ""  # Unused with XOAUTH2
elif os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    raise RuntimeError(
        "Email is not configured. Set EMAIL_HOST (for SMTP) or MS_OAUTH_CLIENT_ID (for OAuth2). "
        "The console email backend has been removed to prevent silent failures."
    )

_default_from = os.environ.get("DEFAULT_FROM_EMAIL", os.environ.get("LF_EMAIL_ADDRESS", ""))
if not _default_from:
    raise RuntimeError("DEFAULT_FROM_EMAIL or LF_EMAIL_ADDRESS must be set.")
DEFAULT_FROM_EMAIL = _default_from

#
# Incoming email (IMAP) configuration for student submissions
# These are used by the check_emails management command.
#
LF_EMAIL_ADDRESS = os.environ.get("LF_EMAIL_ADDRESS", "")
LF_EMAIL_PASSWORD = os.environ.get("LF_EMAIL_PASSWORD", "")
LF_IMAP_HOST = os.environ.get("LF_IMAP_HOST", "outlook.office365.com")
LF_IMAP_PORT = int(os.environ.get("LF_IMAP_PORT", "993"))
LF_IMAP_MAILBOX = os.environ.get("LF_IMAP_MAILBOX", "INBOX")
LF_ALLOWED_SENDER_DOMAIN = os.environ.get("LF_ALLOWED_SENDER_DOMAIN", "@tisb.ac.in")
LF_EMAIL_DISPLAY_NAME = os.environ.get("LF_EMAIL_DISPLAY_NAME", "TRACE Lost & Found")

# Broadcast recipients (§2.2)
_broadcast_raw = os.environ.get("LF_BROADCAST_RECIPIENTS", "raadvait@tisb.ac.in,nsiddharth@tisb.ac.in")
LF_BROADCAST_RECIPIENTS_LIST = list(dict.fromkeys(
    addr.strip().lower() for addr in _broadcast_raw.split(",") if addr.strip()
))

# Magic link configuration (§4.2)
MAGIC_LINK_SECRET = os.environ.get("MAGIC_LINK_SECRET", "")
MAGIC_LINK_BASE_URL = os.environ.get("MAGIC_LINK_BASE_URL", "")

# Google Gemini API Key (currently in use for AI features)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# Authentication
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inventory:item_list"
LOGOUT_REDIRECT_URL = "inventory:item_list"

# Logging: send inventory (e.g. email) errors to stdout so they appear in Railway logs
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "inventory": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

from django.contrib.auth import get_user_model

if os.environ.get("CREATE_SUPERUSER") == "true":
    User = get_user_model()
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

    if username and password:
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            print("Superuser created.")


