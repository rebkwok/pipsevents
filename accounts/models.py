import pytz

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Disclaimer(models.Model):
    user = models.OneToOneField(User, related_name='disclaimer')
    date = models.DateTimeField(default=timezone.now)
    terms_accepted = models.BooleanField()

    def __str__(self):
        return '{} - {}'.format(self.user.username, self.date.astimezone(
                pytz.timezone('Europe/London')
            ).strftime('%d %b %Y, %H:%M'))
