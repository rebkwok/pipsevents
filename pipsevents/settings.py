"""
Django settings for pipsevents project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""

import environ

root = environ.Path(__file__) - 2 # two folders back (/a/b/ - 3 = /)
env = environ.Env(DEBUG=(bool, False),) # set default values and casting
environ.Env.read_env(root('pipsevents/.env')) # reading .env file

BASE_DIR = root()
#
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY') # Raises ImproperlyConfigured exception if SECRET_KEY not in os.environ
if SECRET_KEY is None:
    print("No secret key!")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG') # False if not in os.environ
# when env variable is changed it will be a string, not bool
if str(DEBUG).lower() in ['true', 'on']:
    DEBUG = True
else:
    DEBUG = False

TEMPLATE_DEBUG = DEBUG

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = (
    'suit',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.facebook',
    'django_extensions',
    'crispy_forms',
    'debug_toolbar',
    'accounts',
    'booking',
)

SITE_ID = 1

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    # Required by allauth template tags
    "django.core.context_processors.request",
    # allauth specific context processors
    "allauth.account.context_processors.account",
    "allauth.socialaccount.context_processors.socialaccount",
)


AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",

    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

SOCIALACCOUNT_PROVIDERS = \
    {'facebook':
       {'SCOPE': ['email'],
        # 'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'METHOD': 'oauth2',
        'VERIFIED_EMAIL': False,
        'VERSION': 'v2.2'}}


ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[watermelon studio bookings]"
ACCOUNT_PASSWORD_MIN_LENGTH = 6
ACCOUNT_SIGNUP_FORM_CLASS = 'booking.forms.SignupForm'

SOCIALACCOUNT_QUERY_EMAIL = True

TEMPLATE_DIRS = (root('templates'),)

ROOT_URLCONF = 'pipsevents.urls'

WSGI_APPLICATION = 'pipsevents.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': env.db(), # Raises ImproperlyConfigured exception if DATABASE_URL not in os.environ
}

if env('TRAVIS'):
    DATABASES = {
        'default': {
            'ENGINE':   'django.db.backends.postgresql_psycopg2',
            'NAME':     'travis_ci_test',
            'USER':     'postgres',
            'PASSWORD': '',
            'HOST':     'localhost',
            'PORT':     '',
        }
    }

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-gb'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

# STATIC_URL = '/static/'
# STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_URL = '/media/'
MEDIA_ROOT = root('media')

# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

EMAIL_USE_TLS = True
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'watermelon.bookings@gmail.com'
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
if EMAIL_HOST_PASSWORD is None:
    print("No email host password provided!")
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = 'watermelon.bookings@gmail.com'


#####HEROKU#######

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow all host headers
ALLOWED_HOSTS = ['*']

# Static asset configuration
import os

STATIC_ROOT = 'staticfiles'
STATIC_URL = '/static/'

STATICFILES_DIRS = (root('static'),)

# DJANGO-SUIT
SUIT_CONFIG = {
    'ADMIN_NAME': "Watermelon Pips Events",
    }

INTERNAL_IPS = '127.0.0.1'