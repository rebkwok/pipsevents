from importlib import import_module
from requests.auth import HTTPBasicAuth
from unittest.mock import Mock, patch

from model_bakery import baker

from django.contrib.auth.models import User, Group
from django.contrib.sites.models import Site
from django.conf import settings
from django.test import RequestFactory
from django.utils.html import strip_tags

from accounts.models import DisclaimerContent, PrintDisclaimer, \
    SignedDataPrivacy, DataPrivacyPolicy, has_active_data_privacy_agreement


def set_up_fb():
    fbapp = baker.make_recipe('booking.fb_app')
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


def make_data_privacy_agreement(user):
    if not has_active_data_privacy_agreement(user):
        if DataPrivacyPolicy.current_version() == 0:
            baker.make(
                DataPrivacyPolicy, content='Foo', version=1
            )
        baker.make(
            SignedDataPrivacy, user=user,
            version=DataPrivacyPolicy.current_version()
        )


class TestSetupMixin(object):

    @classmethod
    def setUpTestData(cls):
        set_up_fb()
        cls.factory = RequestFactory()

    def setUp(self):
        mockresponse = Mock()
        mockresponse.status_code = 200
        self.patcher = patch('requests.request', return_value = mockresponse)
        self.mock_request = self.patcher.start()
        self.user = create_configured_user(
            username='test', email='test@test.com', password='test'
        )
        # Make sure we have a current disclaimer content
        DisclaimerContent.objects.create(version=None)

    def tearDown(self):
        self.patcher.stop()


def create_configured_user(username, email, password, staff=False, instructor=False):
    user = User.objects.create_user(
        username=username, email=email, password=password
    )
    baker.make(PrintDisclaimer, user=user)
    make_data_privacy_agreement(user)

    if staff:
        user.is_staff = True
        user.save()

    if instructor:
        group, _ = Group.objects.get_or_create(name="instructors")
        user.groups.add(group)

    return user


class PatchRequestMixin(object):

    def setUp(self):
        mockresponse = Mock()
        mockresponse.status_code = 200
        self.patcher = patch('requests.request', return_value = mockresponse)
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()


def format_content(content):
    # strip tags, \n, \t and extra whitespace from content
    return ' '.join(
        strip_tags(content).replace('\n', '').replace('\t', '').split()
    )


def Any(cls):
    class Any(cls):
        def __eq__(self, other):
            return True
    return Any()


def assert_mailchimp_post_data(
        mock_request, user, mailing_list_status, email=None,
        list_id=settings.MAILCHIMP_LIST_ID
):
    if email is None:
        # allows for testing when changing emails
        email = user.email

    mock_request.assert_called_with(
        timeout=20,
        hooks={'response': []},
        method='POST',
        headers=Any(dict),
        url='https://us6.api.mailchimp.com/3.0/lists/{}'.format(list_id),
        auth=HTTPBasicAuth(
            settings.MAILCHIMP_USER, settings.MAILCHIMP_SECRET
        ),
        json={
            'update_existing': True,
            'members': [
                {
                    'email_address': email,
                    'status': mailing_list_status,
                    'status_if_new': mailing_list_status,
                    'merge_fields': {
                        'FNAME': user.first_name, 'LNAME': user.last_name
                    }
                }
            ]
        }
    )
