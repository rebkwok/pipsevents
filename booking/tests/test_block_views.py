from datetime import timedelta
from model_mommy import mommy

from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase, RequestFactory
from django.test.client import Client
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.forms import BlockCreateForm
from booking.models import Event, Booking, Block
from booking.views import BlockCreateView, BlockListView
from booking.tests.helpers import set_up_fb, _create_session, setup_view


class BlockCreateViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()
        self.user = mommy.make_recipe('booking.user')

    def _set_session(self, user, request):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

    def _get_response(self, user):
        url = reverse('booking:add_block')
        request = self.factory.get(url)
        self._set_session(user, request)
        view = BlockCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data):
        url = reverse('booking:add_block')
        request = self.factory.post(url, form_data)
        self._set_session(user, request)
        view = BlockCreateView.as_view()
        return view(request)

    def test_create_block(self):
        """
        Test creating a block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        form_data={'block_type': block_type}
        resp = self._post_response(self.user, form_data)
        self.assertEqual(resp.status_code, 200)

    def test_create_block_if_no_blocktypes_available(self):
        """
        Test that the create block page redirects if there are no blocktypes
        available to book
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type
        )
        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 302)

    def test_create_block_redirects_if_no_blocktypes_available(self):
        """
        Test that create block form redirects if trying to create a
        block with an event type that the user already has
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block_type_pc10 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            paid=True
        )
        # create form with a different blocktype, but one with the same event
        # type as the user's booked block
        form_data = {'block_type': block_type_pc10}

        url = reverse('booking:add_block')
        request = self.factory.post(url, form_data)
        self._set_session(self.user, request)

        form_data = {'block_type': block_type_pc10.id}
        form = BlockCreateForm(data=form_data)
        form.full_clean()
        view = setup_view(BlockCreateView, request)
        resp = view.form_valid(view, form)

        self.assertEqual(resp.status_code, 302)

    def test_create_block_with_available_blocktypes(self):
        """
        Test that only user does not have the option to book a blocktype
        for which they already have an active block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)

    def test_cannot_create_block_with_same_event_type_as_active_block(self):
        """
        Test that only user does not have the option to book a blocktype
        if they already have a block for the same event type
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        block_type_pc10 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)

    def test_can_create_block_if_has_expired_block(self):
        """
        Test user has the option to create a block with the same event type as
        an expired block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        # this user has a block of this blocktype that has expired
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            start_date=timezone.now() - timedelta(weeks=52)
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], block_type_pc5)

    def test_can_create_block_if_has_full_block(self):
        """
        Test user has the option to create a block with the same event type as
        a full block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        # this user has a block of this blocktype
        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5
        )
        # fill block
        mommy.make_recipe(
            'booking.booking', user=self.user, block=block, _quantity=5
        )

        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], block_type_pc5)

    def test_cannot_create_block_if_has_unpaid_block_with_same_event_type(self):
        """
        Test user does not have the option to create a block with the same
        event type as an unpaid block
        """
        event_type = mommy.make_recipe('booking.event_type_PC')
        block_type_pc5 = mommy.make_recipe(
            'booking.blocktype5', event_type=event_type
        )
        other_block_type = mommy.make_recipe('booking.blocktype_other')
        # this user has a block of this blocktype
        block = mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            paid=False
        )

        resp = self._get_response(self.user)
        # only the "other" blocktype is available
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)


class BlockListViewTests(TestCase):
    def setUp(self):
        set_up_fb()
        self.factory = RequestFactory()

    def _set_session(self, user, request):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages

    def _get_response(self, user):
        url = reverse('booking:block_list')
        request = self.factory.get(url)
        self._set_session(user, request)
        view = BlockListView.as_view()
        return view(request)

    def test_only_list_users_blocks(self):
        users = mommy.make_recipe('booking.user', _quantity=4)
        for user in users:
            mommy.make_recipe('booking.block_5', user=user)
        user = users[0]

        resp = self._get_response(user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Block.objects.all().count(), 4)
        self.assertEqual(resp.context_data['blocks'].count(), 1)
