import os
from pathlib import Path
import importlib.util
from urllib.parse import urlparse
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
HAS_WHITENOISE = importlib.util.find_spec("whitenoise") is not None

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-secret-key-change-me",
)

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

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Google Gemini API Key (currently in use)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# OpenAI API Key (commented out - kept for reference if switching back)
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Authentication
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inventory:item_list"
LOGOUT_REDIRECT_URL = "inventory:item_list"

import os
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


