from model_mommy import mommy
from django.contrib.sites.models import Site


def set_up_fb():
    fbapp = mommy.make_recipe('booking.fb_app')
    site = Site.objects.get_current()
    fbapp.sites.add(site.id)