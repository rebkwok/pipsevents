from django.db import models
from django.utils import timezone

class ActivityLog(models.Model):

    timestamp = models.DateTimeField(default=timezone.now)
    log = models.TextField()

    def __str__(self):
        return '{} - {}'.format(
            self.timestamp.strftime('%Y-%m-%d %H:%M %Z'), self.log[:100]
        )
