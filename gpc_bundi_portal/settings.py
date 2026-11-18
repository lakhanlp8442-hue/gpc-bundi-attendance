import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

IS_RENDER = bool(os.environ.get('RENDER'))

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-gpc-bundi-cse-2026-dev-secret-key-change-in-prod'
)

DEBUG = os.environ.get('DEBUG', 'False' if IS_RENDER else 'True').lower() == 'true'

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'gpc_bundi_portal.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'gpc_bundi_portal.wsgi.application'

# Database: Cloud PostgreSQL if valid DATABASE_URL is set, otherwise local SQLite
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL.startswith(('postgres://', 'postgresql://')):
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'core.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
]

# Internationalization (IST - Rajasthan, India)
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = False

# Static & Media Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==========================================
# GPC BUNDI CAMPUS GEOFENCING COORDINATES
# ==========================================
COLLEGE_LATITUDE = float(os.environ.get('COLLEGE_LATITUDE', 25.4358))
COLLEGE_LONGITUDE = float(os.environ.get('COLLEGE_LONGITUDE', 75.6499))
ALLOWED_RADIUS_METERS = int(os.environ.get('ALLOWED_RADIUS_METERS', 250))

# ==========================================
# SESSION HANDLING & SECURITY (LOCAL + RENDER)
# ==========================================
SESSION_COOKIE_AGE = 1800                # 30 minutes idle timeout
SESSION_SAVE_EVERY_REQUEST = True        # Reset timer on every active request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True   # Expire session when browser closes

SESSION_COOKIE_NAME = 'gpc_bundi_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False             # Required for JS fetch() X-CSRFToken header
CSRF_COOKIE_SAMESITE = 'Lax'

SESSION_COOKIE_SECURE = IS_RENDER        # True on Render HTTPS, False on local HTTP
CSRF_COOKIE_SECURE = IS_RENDER