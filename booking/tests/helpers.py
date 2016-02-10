from importlib import import_module
from model_mommy import mommy

from django.contrib.sites.models import Site
from django.conf import settings
from django.test import RequestFactory
from django.utils.html import strip_tags


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


def setup_view(view, request, *args, **kwargs):
    """
    Mimic as_view() returned callable, but returns view instance.
    args and kwargs are the same you would pass to ``reverse()``
    """
    view.request = request
    view.args = args
    view.kwargs = kwargs
    return view


class TestSetupMixin(object):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()
        cls.factory = RequestFactory()
        cls.user = mommy.make_recipe('booking.user')


def format_content(content):
    # strip tags, \n, \t and extra whitespace from content
    return ' '.join(
        strip_tags(content).replace('\n', '').replace('\t', '').split()
    )
