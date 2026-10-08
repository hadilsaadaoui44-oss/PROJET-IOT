"""
Django settings for energy_project project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# ==========================================================
# CHEMINS ET VARIABLES D'ENVIRONNEMENT
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """
    Convertit une variable d'environnement en booléen.
    Valeurs acceptées comme vraies : 1, true, yes, on.
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_list(name: str, default: str = "") -> list[str]:
    """
    Convertit une variable séparée par des virgules en liste.
    Exemple :
    ALLOWED_HOSTS=localhost,127.0.0.1
    """
    value = os.getenv(name, default)

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def env_int(name: str, default: int) -> int:
    """
    Lit une variable d'environnement entière.
    """
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ==========================================================
# SÉCURITÉ
# ==========================================================

DEBUG = env_bool(
    "DJANGO_DEBUG",
    default=True,
)

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-development-only-change-this-key",
)

# En production, la clé secrète doit obligatoirement être configurée.
if not DEBUG and SECRET_KEY.startswith("django-insecure"):
    raise RuntimeError(
        "DJANGO_SECRET_KEY doit être définie avec une clé sécurisée "
        "lorsque DJANGO_DEBUG=False."
    )

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1",
)

CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "",
)

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SESSION_COOKIE_SECURE = env_bool(
    "DJANGO_SESSION_COOKIE_SECURE",
    default=False,
)

CSRF_COOKIE_SECURE = env_bool(
    "DJANGO_CSRF_COOKIE_SECURE",
    default=False,
)

SECURE_SSL_REDIRECT = env_bool(
    "DJANGO_SECURE_SSL_REDIRECT",
    default=False,
)


# ==========================================================
# APPLICATIONS
# ==========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "analyzer",
]


# ==========================================================
# MIDDLEWARE
# ==========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "energy_project.urls"


# ==========================================================
# TEMPLATES
# ==========================================================

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends.django."
            "DjangoTemplates"
        ),
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template.context_processors."
                    "request"
                ),
                (
                    "django.contrib.auth.context_processors."
                    "auth"
                ),
                (
                    "django.contrib.messages.context_processors."
                    "messages"
                ),
            ],
        },
    },
]


WSGI_APPLICATION = "energy_project.wsgi.application"


# ==========================================================
# BASE DE DONNÉES
# ==========================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# ==========================================================
# VALIDATION DES MOTS DE PASSE
# ==========================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ==========================================================
# LANGUE ET FUSEAU HORAIRE
# ==========================================================

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "Africa/Tunis"

USE_I18N = True

USE_TZ = True


# ==========================================================
# FICHIERS STATIQUES
# ==========================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []

STATIC_SOURCE_DIRECTORY = BASE_DIR / "static"

if STATIC_SOURCE_DIRECTORY.exists():
    STATICFILES_DIRS.append(
        STATIC_SOURCE_DIRECTORY
    )


# ==========================================================
# FICHIERS MÉDIA
# ==========================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ==========================================================
# TAILLE MAXIMALE DES FICHIERS
# ==========================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = (
    50 * 1024 * 1024
)

FILE_UPLOAD_MAX_MEMORY_SIZE = (
    50 * 1024 * 1024
)


# ==========================================================
# AUTHENTIFICATION
# ==========================================================

AUTH_USER_MODEL = "analyzer.CustomUser"

LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "home"

LOGOUT_REDIRECT_URL = "home"


# ==========================================================
# CONFIGURATION E-MAIL BREVO
# ==========================================================

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = os.getenv(
    "EMAIL_HOST",
    "smtp-relay.brevo.com",
)

EMAIL_PORT = env_int(
    "EMAIL_PORT",
    587,
)

EMAIL_USE_TLS = env_bool(
    "EMAIL_USE_TLS",
    default=True,
)

EMAIL_USE_SSL = env_bool(
    "EMAIL_USE_SSL",
    default=False,
)

EMAIL_HOST_USER = os.getenv(
    "BREVO_SMTP_USER",
    "",
)

EMAIL_HOST_PASSWORD = os.getenv(
    "BREVO_SMTP_KEY",
    "",
)

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "Assistant Énergétique IoT <noreply@example.com>",
)

SERVER_EMAIL = DEFAULT_FROM_EMAIL

EMAIL_TIMEOUT = env_int(
    "EMAIL_TIMEOUT",
    30,
)


# ==========================================================
# CONFIGURATION OFFICIELLE N8N / AIDE-IOT
# ==========================================================

N8N_ENERGY_WEBHOOK_URL = os.getenv(
    "N8N_ENERGY_WEBHOOK_URL",
    "http://localhost:5678/webhook/energy-analysis",
).strip()

N8N_ENERGY_API_KEY = os.getenv(
    "N8N_ENERGY_API_KEY",
    "",
).strip()

N8N_ENERGY_TIMEOUT_SECONDS = env_int(
    "N8N_ENERGY_TIMEOUT_SECONDS",
    300,
)

if not N8N_ENERGY_WEBHOOK_URL:
    raise RuntimeError(
        "N8N_ENERGY_WEBHOOK_URL ne peut pas être vide."
    )

if "/webhook-test/" in N8N_ENERGY_WEBHOOK_URL:
    raise RuntimeError(
        "Utilisez l'URL n8n de production contenant "
        "'/webhook/' et non '/webhook-test/'."
    )


# ==========================================================
# JOURNALISATION
# ==========================================================

LOG_DIRECTORY = BASE_DIR / "logs"

LOG_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{levelname} {asctime} "
                "{name} {message}"
            ),
            "style": "{",
        },
        "simple": {
            "format": (
                "{levelname} {message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },

        "file": {
            "class": (
                "logging.handlers."
                "RotatingFileHandler"
            ),
            "filename": (
                LOG_DIRECTORY /
                "energy_project.log"
            ),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
    },

    "root": {
        "handlers": [
            "console",
            "file",
        ],
        "level": "INFO",
    },

    "loggers": {
        "django": {
            "handlers": [
                "console",
                "file",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "analyzer": {
            "handlers": [
                "console",
                "file",
            ],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# ==========================================================
# CLÉ PRIMAIRE PAR DÉFAUT
# ==========================================================

DEFAULT_AUTO_FIELD = (
    "django.db.models.BigAutoField"
)
