from model_mommy import mommy
from django.contrib.sites.models import Site
from django.conf import settings
from django.utils.importlib import import_module


def set_up_fb():
    fbapp = mommy.make_recipe('booking.fb_app')
    site = Site.objects.get_current()
    fbapp.sites.add(site.id)


def _create_session():
    # create session
    settings.SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    engine = import_module(settings.SESSION_ENGINE)
    store = engine.SessionStore()
    store.save()
    return store
