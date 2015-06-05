from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from accounts.forms import SignupForm
from accounts.views import ProfileUpdateView, profile
from booking.tests.helpers import set_up_fb
from model_mommy import mommy

class SignUpFormTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

    def test_signup_form(self):
        form_data = {'first_name': 'Test',
                     'last_name': 'User'}
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_signup_form_with_invalid_data(self):
        # first_name must have 30 characters or fewer
        form_data = {'first_name': 'abcdefghijklmnopqrstuvwxyz12345',
                     'last_name': 'User'}
        form = SignupForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_assigned_from_request(self):
        user = mommy.make(User)
        url = reverse('account_signup')
        request = self.factory.get(url)
        request.user = user
        form_data = {'first_name': 'New',
                     'last_name': 'Name'}
        form = SignupForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.signup(request, user)
        self.assertEquals('New', user.first_name)
        self.assertEquals('Name', user.last_name)


class ProfileUpdateViewTests(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

    def test_updating_user_data(self):
        """
        Test custom view to allow users to update their details
        """
        user = mommy.make(User, username="test_user",
                          first_name="Test",
                          last_name="User",
                          )
        url = reverse('profile:update_profile')
        request = self.factory.post(
            url, {'username': user.username,
                  'first_name': 'Fred', 'last_name': user.last_name}
        )
        request.user = user
        view = ProfileUpdateView.as_view()
        resp = view(request)
        updated_user = User.objects.get(username="test_user")
        self.assertEquals(updated_user.first_name, "Fred")


class ProfileTest(TestCase):

    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

    def test_profile_view(self):
        user = mommy.make(User)
        url = reverse('profile:profile')
        request = self.factory.get(url)
        request.user = user
        resp = profile(request)

        self.assertEquals(resp.status_code, 200)
