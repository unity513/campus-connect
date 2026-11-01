"""Django settings for the Campus Connect e-commerce platform.

Campus Connect is the customer-facing brand. LAVIDA is the technology
provider. Secrets are read from the environment; sensible dev defaults are
provided.

The relational database can be a hosted Supabase Postgres instance: set
``SAVANA_DATABASE_URL`` (or ``DATABASE_URL``) to the Supabase connection
string and Django will use it automatically.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security ---------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "SAVANA_SECRET_KEY",
    "dev-insecure-change-me-in-production-0123456789abcdef",
)
DEBUG = os.environ.get("SAVANA_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get(
    "SAVANA_ALLOWED_HOSTS", "127.0.0.1,localhost"
).split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("SAVANA_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# Harden cookies/headers when running outside DEBUG.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get("SAVANA_SSL_REDIRECT", "0") == "1"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # two weeks

# --- Applications -----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    # Local apps
    "accounts",
    "catalog",
    "orders",
    "store",
    "storefront",
    "backoffice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.SimpleRateLimitMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "storefront.context_processors.store_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---------------------------------------------------------------
# Relational DB resolution order:
#   1. A connection URL (Supabase / any Postgres) via SAVANA_DATABASE_URL or
#      the conventional DATABASE_URL.  e.g. Supabase gives you:
#      postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
#   2. Discrete SAVANA_POSTGRES_* variables.
#   3. SQLite (zero-config local development default).


def _database_from_url(url):
    """Parse a postgres:// connection URL into a Django DATABASES config."""
    parsed = urlparse(url)
    name = parsed.path.lstrip("/") or "postgres"
    options = {}
    # Supabase requires SSL; the pooler also benefits from it.
    sslmode = os.environ.get("SAVANA_DB_SSLMODE", "require")
    if sslmode:
        options["sslmode"] = sslmode
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or "postgres"),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "127.0.0.1",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": int(os.environ.get("SAVANA_DB_CONN_MAX_AGE", 0)),
    }
    if options:
        config["OPTIONS"] = options
    return config


_DB_URL = os.environ.get("SAVANA_DATABASE_URL") or os.environ.get("DATABASE_URL")
if _DB_URL:
    DATABASES = {"default": _database_from_url(_DB_URL)}
elif os.environ.get("SAVANA_POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["SAVANA_POSTGRES_DB"],
            "USER": os.environ.get("SAVANA_POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("SAVANA_POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("SAVANA_POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("SAVANA_POSTGRES_PORT", "5432"),
            "OPTIONS": {"sslmode": os.environ.get("SAVANA_DB_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / tz --------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("SAVANA_TZ", "Africa/Blantyre")
USE_I18N = True
USE_TZ = True

# --- Static & media ---------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media (product images are public; payment proofs are PRIVATE and served
# through an authorization-checked view, never a predictable public URL).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "storefront:home"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Upload limits for payment proofs / product images.
MAX_UPLOAD_BYTES = int(os.environ.get("SAVANA_MAX_UPLOAD_BYTES", 8 * 1024 * 1024))
ALLOWED_PROOF_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Notifications: pluggable provider. Console by default (configurable in admin).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("SAVANA_FROM_EMAIL", "orders@campusconnect.example")

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
