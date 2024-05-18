
import logging

from django.db import models

from django.utils import timezone
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger(__name__)


class Banner(models.Model):
    banner_type = models.CharField(
        max_length=10, 
        choices=(("banner_all", "all users banner"), ("banner_new", "new users banner")),
        default="banner_all"
    )
    content = models.TextField()
    start_datetime = models.DateTimeField(default=timezone.now)
    end_datetime = models.DateTimeField(null=True, blank=True)
    colour = models.CharField(
        max_length=10, 
        choices=(
            ("info", "light blue"),
            ("primary", "blue"), 
            ("success", "green"), 
            ("warning", "yellow"), 
            ("danger", "red"),
            ("secondary", "light grey"),
            ("dark", "dark grey")
        ),
        default="info"
    )

    def __str__(self) -> str:
        return f"{self.banner_type}"
