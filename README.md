[![Build Status](https://travis-ci.org/rebkwok/pipsevents.svg?branch=master)](https://travis-ci.org/rebkwok/pipsevents)
[![Coverage Status](https://coveralls.io/repos/rebkwok/pipsevents/badge.svg)](https://coveralls.io/r/rebkwok/pipsevents)

## Event bookings website for Watermelon Studio

# Required settings

- SECRET_KEY: app secret key
- DATABASE_URL: database settings
- EMAIL_HOST_PASSWORD: password for emails sent from the app
- DEFAULT_PAYPAL_EMAIL: the email address paypal payments made through the app will be sent to
- LOG_FOLDER: path to folder containing the app's log files

# Optional for dev

- USE_MAILCATCHER: Boolean, set to True to send mail to mailcatcher
- HEROKU: set to True if using Heroku to use different log settings
- DEBUG: False for dev
- TRAVIS: Set to True in .travis.yml
