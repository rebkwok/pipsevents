"""
Django settings for pipsevents project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""
import dj_database_url
import environ
import os

root = environ.Path(__file__) - 2  # two folders back (/a/b/ - 3 = /)

env = environ.Env(DEBUG=(bool, False),
                  PAYPAL_TEST=(bool, False),
                  USE_MAILCATCHER=(bool, False),
                  TRAVIS=(bool, False),
                  HEROKU=(bool, False),
                  SEND_ALL_STUDIO_EMAILS=(bool, False)
                  )

environ.Env.read_env(root('pipsevents/.env'))  # reading .env file

BASE_DIR = root()
#
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')
if SECRET_KEY is None:  # pragma: no cover
    print("No secret key!")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')
# when env variable is changed it will be a string, not bool
if str(DEBUG).lower() in ['true', 'on']:  # pragma: no cover
    DEBUG = True
else:
    DEBUG = False

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
    'timetable',
    'studioadmin',
    'ckeditor',
    'paypal.standard.ipn',
    'payments',
    'activitylog',
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
    'responsive.middleware.DeviceInfoMiddleware',
)

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",

    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

SOCIALACCOUNT_PROVIDERS = \
    {'facebook': {
        'SCOPE': ['email'],
        # 'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'METHOD': 'oauth2',
        'VERIFIED_EMAIL': False,
        'VERSION': 'v2.2'
        }}


ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[watermelon studio bookings]"
ACCOUNT_PASSWORD_MIN_LENGTH = 6
ACCOUNT_SIGNUP_FORM_CLASS = 'accounts.forms.SignupForm'

SOCIALACCOUNT_QUERY_EMAIL = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [root('templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': (
                'django.contrib.auth.context_processors.auth',
                # Required by allauth template tags
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                'responsive.context_processors.device_info',
            ),
            'debug': DEBUG,
        },
    },
]

ROOT_URLCONF = 'pipsevents.urls'

ABSOLUTE_URL_OVERRIDES = {
    'auth.user': lambda o: "/users/%s/" % o.username,
}

WSGI_APPLICATION = 'pipsevents.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': env.db(),
    # Raises ImproperlyConfigured exception if DATABASE_URL not in os.environ
}

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-gb'

TIME_ZONE = 'Europe/London'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/
STATICFILES_DIRS = (root('static'),)

STATIC_URL = '/static/'
STATIC_ROOT = root('collected-static')

MEDIA_URL = '/media/'
MEDIA_ROOT = root('media')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_USE_TLS = True
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'watermelon.bookings@gmail.com'
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', None)
if EMAIL_HOST_PASSWORD is None:  # pragma: no cover
    print("No email host password provided!")
EMAIL_PORT = 587
DEFAULT_FROM_EMAIL = 'watermelon.bookings@gmail.com'
DEFAULT_STUDIO_EMAIL = 'thewatermelonstudio@hotmail.com'
SUPPORT_EMAIL = 'rebkwok@gmail.com'
SEND_ALL_STUDIO_EMAILS = env('SEND_ALL_STUDIO_EMAILS')

# #####LOGGING######
if not env('HEROKU') and not env('TRAVIS'):  # pragma: no cover
    LOG_FOLDER = env('LOG_FOLDER')

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '[%(levelname)s] - %(asctime)s - %(name)s - '
                          '%(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            }
        },
        'handlers': {
            'file_app': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                # 'filename': '/var/log/pipsevents/pipsevents.log',
                'filename': os.path.join(LOG_FOLDER, 'pipsevents.log'),
                'maxBytes': 1024*1024*5,  # 5 MB
                'backupCount': 5,
                'formatter': 'verbose'
            },
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            }
        },
        'loggers': {
            '': {
                'handlers': ['console', 'file_app'],
                'level': 'WARNING',
                'propagate': True,
            },
            'booking': {
                'handlers': ['console', 'file_app'],
                'level': 'INFO',
                'propagate': True,
            },
            'payments': {
                'handlers': ['console', 'file_app'],
                'level': 'INFO',
                'propagate': True,
            },
            'studioadmin': {
                'handlers': ['console', 'file_app'],
                'level': 'INFO',
                'propagate': True,
            },
            'timetable': {
                'handlers': ['console', 'file_app'],
                'level': 'INFO',
                'propagate': True,
            },
        },
    }


# ####HEROKU#######

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow all host headers
ALLOWED_HOSTS = ['*']

# DJANGO-SUIT
SUIT_CONFIG = {
    'ADMIN_NAME': "Watermelon Pips Events",
    'MENU': (
        {
            'label': 'Events and Classes',
            'icon': 'icon-star',
            'models': ('booking.event', 'booking.eventtype')
        },
        {
            'label': 'Blocks',
            'icon': 'icon-star-empty',
            'models': ('booking.block', 'booking.blocktype')
        },
        {
            'label': 'Bookings',
            'icon': 'icon-heart',
            'models': ('booking.booking', 'booking.waitinglistuser')
        },
        {
            'label': 'Ticket Bookings',
            'icon': 'icon-heart',
            'models': (
                'booking.ticketedevent', 'booking.ticketbooking',
                'booking.ticket',
            )
        },
        {
            'app': 'timetable',
            'label': 'Weekly timetable',
            'icon': 'icon-calendar',
        },
        {
            'app': 'auth',
            'label': 'Users',
            'models': ('user',),
            'icon': 'icon-user',
        },
        {
            'label': 'Payments',
            'models': ('payments.paypalbookingtransaction',
                       'payments.paypalblocktransaction',
                       'payments.paypalticketbookingtransaction',
                       'ipn.paypalipn'),
            'icon': 'icon-asterisk',
        },
        {
            'label': 'Activity Log',
            'app': 'activitylog',
            'icon': 'icon-asterisk',
        },
        {
            'label': 'Go to main booking site',
            'url': '/',
            'icon': 'icon-map-marker',
        },
    )
}

INTERNAL_IPS = '127.0.0.1'


# CKEDITOR
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_IMAGE_BACKEND = 'pillow'
CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': [
         ['Source', '-', 'Bold', 'Italic', 'Underline',
          'TextColor', 'BGColor'],
         ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-',
          'JustifyLeft', 'JustifyCenter', 'JustifyRight', '-',
          'Table', 'HorizontalRule', 'Smiley', 'SpecialChar'],
         ['Format', 'Font', 'FontSize']
        ],
        # 'height': 300,
        'width': 350,
    },
    'studioadmin': {
        'toolbar': [
         ['Source', '-', 'Bold', 'Italic', 'Underline',
          'TextColor', 'BGColor'],
         ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-',
          'JustifyLeft', 'JustifyCenter', 'JustifyRight', '-',
          'Table', 'HorizontalRule', 'Smiley', 'SpecialChar'],
         ['Format', 'Font', 'FontSize', 'Link']
        ],
        'height': 200,
        'width': '100%',
        'max-width': 300,
    },
    'studioadmin_min': {
        'toolbar': [
            ['Bold', 'Italic', 'Underline', 'FontSize', 'Link']
        ],
        'height': 100,
        'width': '100%',
        'max-width': 300,
    },
}
CKEDITOR_JQUERY_URL = \
    '//ajax.googleapis.com/ajax/libs/jquery/2.1.1/jquery.min.js'

# MAILCATCHER
if env('USE_MAILCATCHER'):  # pragma: no cover
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = '127.0.0.1'
    EMAIL_HOST_USER = ''
    EMAIL_HOST_PASSWORD = ''
    EMAIL_PORT = 1025
    EMAIL_USE_TLS = False

# DJANGO-PAYPAL
PAYPAL_RECEIVER_EMAIL = env('PAYPAL_RECEIVER_EMAIL')
PAYPAL_TEST = env('PAYPAL_TEST')

# TRAVIS and HEROKU logging
if env('TRAVIS') or env('HEROKU'):
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
            }
        },
        'loggers': {
            'django.request': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
            'booking': {
                'handlers': ['console'],
                'level': 'INFO',
                'propogate': True,
            },
            'payments': {
                'handlers': ['console'],
                'level': 'INFO',
                'propogate': True,
            },
            'studioadmin': {
                'handlers': ['console'],
                'level': 'INFO',
                'propogate': True,
            },
            'timetable': {
                'handlers': ['console'],
                'level': 'INFO',
                'propogate': True,
            },
        },
    }

