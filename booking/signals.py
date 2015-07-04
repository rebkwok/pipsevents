from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from activitylog.models import ActivityLog


@receiver(post_save, sender=User)
def event_post_save(sender, instance, created, *args, **kwargs):
    if created:
        ActivityLog.objects.create(
            log='New user registered: {} {}, username {}'.format(
                    instance.first_name, instance.last_name, instance.username
            )
        )
