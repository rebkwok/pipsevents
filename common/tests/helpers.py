from importlib import import_module
from requests.auth import HTTPBasicAuth
from unittest.mock import patch

from model_mommy import mommy

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.conf import settings
from django.test import RequestFactory
from django.utils.html import strip_tags

from accounts.models import PrintDisclaimer


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


def _add_user_email_addresses(model):
    # populate foreign key user email addresses for model instances which have
    # FK to user
    for i, instance in enumerate(model.objects.all()):
        if not instance.user.email:
            instance.user.email = 'auto{}.test@test.com'.format(i)
            instance.user.save()


class TestSetupMixin(object):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()
        cls.factory = RequestFactory()

    def setUp(self):
        self.patcher = patch('requests.request')
        self.mock_request = self.patcher.start()
        self.user = User.objects.create_user(
            username='test', email='test@test.com', password='test'
        )
        mommy.make(PrintDisclaimer, user=self.user)

    def tearDown(self):
        self.patcher.stop()


class PatchRequestMixin(object):

    def setUp(self):
        self.patcher = patch('requests.request')
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()


def format_content(content):
    # strip tags, \n, \t and extra whitespace from content
    return ' '.join(
        strip_tags(content).replace('\n', '').replace('\t', '').split()
    )


def assert_mailchimp_post_data(mock_request, user, mailing_list_status):
    mock_request.assert_called_with(
        timeout=None,
        hooks={'response': []},
        method='POST',
        url='https://{}.api.mailchimp.com/3.0/lists/{}'.format(
            settings.MAILCHIMP_SECRET, settings.MAILCHIMP_LIST_ID
        ),
        auth=HTTPBasicAuth(
            settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
        ),
        json={
            'update_existing': True,
            'members': [
                {
                    'email_address': user.email,
                    'status': mailing_list_status,
                    'status_if_new': mailing_list_status,
                    'merge_fields': {'FNAME': user.first_name, 'LNAME': user.last_name}
                }
            ]
        }
    )
