from django.db import models
from django.utils import timezone

class ActivityLog(models.Model):

    timestamp = models.DateTimeField(default=timezone.now)
    log = models.TextField()
