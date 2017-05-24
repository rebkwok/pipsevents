[![Build Status](https://travis-ci.org/rebkwok/pipsevents.svg?branch=master)](https://travis-ci.org/rebkwok/pipsevents)
[![Coverage Status](https://coveralls.io/repos/rebkwok/pipsevents/badge.svg)](https://coveralls.io/r/rebkwok/pipsevents)

## Event bookings website for Watermelon Studio

# Required settings

- SECRET_KEY: app secret key
- DATABASE_URL: database settings
- EMAIL_HOST_PASSWORD: password for emails sent from the app
- DEFAULT_PAYPAL_EMAIL: the email address paypal payments made through the app will be sent to
- LOG_FOLDER: path to folder containing the app's log files
- SIMPLECRYPT_PASSWORD: password to encrypt/decrypt exported data
- DEFAULT_PAYPAL_EMAIL: default receiver email for paypal payments

# Optional
- DEBUG (default False)
- SEND_ALL_STUDIO_EMAILS (default False)
- AUTO_BOOK_EMAILS (comma separated list of email addresses to auto book if on waiting list; default [])
- LOCAL (default False)


# For dev add the following additional settings to .env
- DEBUG=True
- USE_MAILCATCHER=True
- LOCAL=True
- PAYPAL_TEST=True
- SHOW_DEBUG_TOOLBAR=True
- HEROKU: set to True if using Heroku to use different log settings

