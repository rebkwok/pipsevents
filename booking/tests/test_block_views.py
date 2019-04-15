from datetime import datetime, timedelta
from model_mommy import mommy

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from accounts.models import OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.forms import BlockCreateForm
from booking.models import Block, BlockVoucher, UsedBlockVoucher
from booking.views import BlockCreateView, BlockListView
from common.tests.helpers import _create_session, format_content, \
    setup_view, TestSetupMixin, make_data_privacy_agreement


class BlockCreateViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(BlockCreateViewTests, self).setUp()
        self.user_no_disclaimer = mommy.make_recipe('booking.user')
        make_data_privacy_agreement(self.user_no_disclaimer)

    def _set_session(self, user, request, session_data=None):
        request.session = _create_session()
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        if session_data:
            request.session.update(session_data)

    def _get_response(self, user, session_data=None):
        url = reverse('booking:add_block')
        request = self.factory.get(url)
        self._set_session(user, request, session_data)
        view = BlockCreateView.as_view()
        return view(request)

    def _post_response(self, user, form_data, session_data=None):
        url = reverse('booking:add_block')
        request = self.factory.post(url, form_data)
        self._set_session(user, request, session_data)
        view = BlockCreateView.as_view()
        return view(request)

    def test_cannot_create_block_if_no_disclaimer(self):
        block_type = mommy.make_recipe('booking.blocktype5')
        resp = self._get_response(self.user_no_disclaimer)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 200)

        form_data={'block_type': block_type}
        resp = self._post_response(self.user_no_disclaimer, form_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:disclaimer_required'))

    def test_create_block(self):
        """
        Test creating a block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        form_data={'block_type': block_type.id}
        self.assertEqual(Block.objects.count(), 0)
        resp = self._post_response(self.user, form_data)
        self.assertEqual(resp.status_code, 302)
        # redirects to shopping basket
        self.assertIn(resp.url, reverse('booking:shopping_basket'))
        self.assertEqual(Block.objects.count(), 1)

        # email sent to user only
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(
            email.subject, '{} Block created'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX
            )
        )

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
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type_pc5,
            paid=False
        )

        resp = self._get_response(self.user)
        # only the "other" blocktype is available
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], other_block_type)

    def test_only_active_blocktypes_available(self):
        block_type = mommy.make_recipe('booking.blocktype5')
        inactive_block_type = mommy.make_recipe(
            'booking.blocktype_other', active=False
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], block_type)

    def test_only_active_and_unbooked_blocktypes_available(self):
        """
        Test that only user does not have the option to book a blocktype
        for which they already have an active block
        """
        block_type = mommy.make_recipe('booking.blocktype5')
        active_block_type = mommy.make_recipe('booking.blocktype5')
        inactive_block_type = mommy.make_recipe(
            'booking.blocktype_other', active=False
        )
        mommy.make_recipe(
            'booking.block', user=self.user, block_type=block_type
        )
        resp = self._get_response(self.user)
        self.assertEqual(len(resp.context_data['block_types']), 1)
        self.assertEqual(resp.context_data['block_types'][0], active_block_type)

    def test_try_to_create_block_with_unavailable_blocktype(self):
        """
        when a block is created, and there are no more possible blocks to book,
        "no_available_block" flag is set on the session so that if the user
        clicks the back button they get returned to the block list page
        instead of the create block page
        """
        block_type1 = mommy.make_recipe('booking.blocktype5')
        block_type2 = mommy.make_recipe('booking.blocktype5')

        mommy.make_recipe(
            'booking.block', block_type=block_type1, user=self.user
        )
        # blocktypes are available, but the one we post with is not
        data = {'block_type': block_type1.id}
        resp = self._post_response(self.user, data)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:has_active_block'))

    def test_cart_items_deleted_from_session_on_get(self):
        self.client.login(username=self.user.username, password='test')
        session = self.client.session
        session['cart_items'] = 'block test'
        session.save()

        url = reverse('booking:add_block')
        self.assertIsNotNone(self.client.session.get('cart_items'))

        self.client.get(url)
        self.assertIsNone(self.client.session.get('cart_items'))

    def test_redirect_to_block_list_if_no_available_blocktype_to_add(self):
        self.client.login(username=self.user.username, password='test')

        # no blocktypes
        resp = self.client.get(reverse('booking:add_block'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:block_list'))

        # available blocktype
        block_type = mommy.make_recipe('booking.blocktype5')
        resp = self.client.get(reverse('booking:add_block'))
        self.assertEqual(resp.status_code, 200)

        # user has block for all available blocktypes
        mommy.make_recipe('booking.block', block_type=block_type, user=self.user)
        resp = self.client.get(reverse('booking:add_block'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:block_list'))


class BlockListViewTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super(BlockListViewTests, cls).setUpTestData()
        cls.block_type = mommy.make_recipe('booking.blocktype5', cost=30)
        cls.url = reverse('booking:block_list')

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
        make_data_privacy_agreement(user)

        resp = self._get_response(user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Block.objects.all().count(), 4)
        self.assertEqual(resp.context_data['blocks'].count(), 1)

    def test_disclaimer_messages(self):
        mommy.make_recipe('booking.blocktype5')
        user = User.objects.create_user(
            username='test_no_disc', email='test@test.com', password='test'
        )
        make_data_privacy_agreement(user)
        self.client.login(username=user.username, password='test')
        resp = self.client.get(reverse('booking:block_list'))
        self.assertNotIn(
            'Get a new block!', format_content(resp.rendered_content)
        )
        self.assertIn(
            'Please complete a disclaimer form before buying a block.',
            format_content(resp.rendered_content)
        )

        # self.user has a PrintDisclaimer
        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(reverse('booking:block_list'))
        self.assertIn(
            'Get a new block!', format_content(resp.rendered_content)
        )
        self.assertNotIn(
            'Please complete a disclaimer form before buying a block.',
            format_content(resp.rendered_content)
        )

        user_online_disclaimer = User.objects.create_user(
            username='test_online', email='test@test.com', password='test'
        )
        make_data_privacy_agreement(user_online_disclaimer)
        mommy.make(OnlineDisclaimer, user=user_online_disclaimer)
        self.client.login(
            username=user_online_disclaimer.username, password='test'
        )
        resp = self.client.get(reverse('booking:block_list'))
        self.assertIn(
            'Get a new block!', format_content(resp.rendered_content)
        )
        self.assertNotIn(
            'Please complete a disclaimer form before buying a block.',
            format_content(resp.rendered_content)
        )

        # expired disclaimer
        user_expired_disclaimer = User.objects.create_user(
            username='test_expired', email='test@test.com', password='test'
        )
        make_data_privacy_agreement(user_expired_disclaimer)
        self.client.login(
            username=user_expired_disclaimer.username, password='test'
        )
        disclaimer = mommy.make(OnlineDisclaimer,
            user=user_expired_disclaimer,
            date=datetime(2015, 2, 1, tzinfo=timezone.utc)
        )
        disclaimer.save()
        self.assertFalse(disclaimer.is_active)
        resp = self.client.get(reverse('booking:block_list'))
        self.assertNotIn(
            'Get a new block!', format_content(resp.rendered_content)
        )
        self.assertIn(
            'Your disclaimer has expired. Please review and confirm your '
            'information before buying a block.',
            format_content(resp.rendered_content)
        )

    def test_block_type_id_user_display(self):
        bt1 = mommy.make_recipe(
            'booking.blocktype5', event_type__subtype='Test1',
            identifier='transferred'
        )
        mommy.make_recipe('booking.block', block_type=bt1, user=self.user)
        bt2 = mommy.make_recipe(
            'booking.blocktype5', event_type__subtype='Test2',
            identifier='free class'
        )
        mommy.make_recipe('booking.block', block_type=bt2, user=self.user)

        bt3 = mommy.make_recipe(
            'booking.blocktype5', event_type__subtype='Test3',
            identifier='transferred'
        )
        booking = mommy.make_recipe(
            'booking.booking', event__name='Test event',
            event__date=datetime(
                year=2015, month=1, day=12, tzinfo=timezone.utc
            ), status='CANCELLED'
        )
        mommy.make_recipe(
            'booking.block', block_type=bt3, user=self.user,
            transferred_booking_id=booking.id
        )
        bt4 = mommy.make_recipe(
            'booking.blocktype5', event_type__subtype='Test4',
        )
        mommy.make_recipe(
            'booking.block', block_type=bt4, user=self.user,
        )

        self.client.login(username=self.user.username, password='test')
        resp = self.client.get(reverse('booking:block_list'))

        self.assertIn(
            'Test1 (transferred)', format_content(resp.rendered_content)
        )
        self.assertIn(
            'Test2 (free class)', format_content(resp.rendered_content)
        )
        self.assertIn(
            'Test3 (transferred from Test event 12Jan15)',
            format_content(resp.rendered_content)
        )
        self.assertIn('Test4', format_content(resp.rendered_content))
        self.assertNotIn('Test4 (', format_content(resp.rendered_content))


class BlockDeleteViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(BlockDeleteViewTests, self).setUp()
        self.client.login(username=self.user.username, password='test')
        self.block = mommy.make_recipe('booking.block', user=self.user)
        self.url = reverse('booking:delete_block', args=[self.block.id])

    def test_cannot_get_delete_page_if_not_logged_in(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(
            resp.url,
            reverse('login') + '?next=/blocks/{}/delete/'.format(self.block.id)
        )

    def test_can_get_delete_block_page(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context_data['block_to_delete'], self.block)

    def test_cannot_get_delete_block_page_if_block_paid(self):
        self.block.paid = True
        self.block.save()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

    def test_cannot_get_delete_block_page_if_block_has_bookings(self):
        mommy.make_recipe('booking.booking', block=self.block)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

    def test_cannot_post_delete_block_page_if_block_paid(self):
        self.block.paid = True
        self.block.save()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

        self.assertEqual(Block.objects.first(), self.block)

    def test_cannot_post_delete_block_page_if_block_has_bookings(self):
        mommy.make_recipe('booking.booking', block=self.block)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(resp.url, reverse('booking:permission_denied'))

        self.assertEqual(Block.objects.first(), self.block)

    def test_delete_block(self):
        self.client.post(self.url)
        self.assertFalse(Block.objects.exists())

        log = ActivityLog.objects.latest('id')
        self.assertEqual(
            log.log,
            'User {} deleted unpaid and unused block {} ({})'.format(
                self.user.username, self.block.id, self.block.block_type
            )
        )

    def test_delete_block_from_shopping_basket(self):
        resp = self.client.post(self.url + '?ref=basket')
        self.assertFalse(Block.objects.exists())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'Block deleted')

    def test_delete_block_with_booking_code(self):
        """
        Test deleting a block from basket with code returns with code in get
        """
        data = {'next': 'shopping_basket', 'booking_code': 'foo'}
        resp = self.client.post(self.url, data)
        self.assertFalse(Block.objects.exists())

        # redirects back to shopping basket with code
        self.assertIn(
            resp.url, reverse('booking:shopping_basket') + '?booking_code=foo'
        )

    def test_delete_block_with_block_code(self):
        """
        Test deleting a block from basket with code returns with code in get
        """
        data = {'next': 'shopping_basket', 'block_code': 'foo'}
        resp = self.client.post(self.url, data)
        self.assertFalse(Block.objects.exists())

        # redirects back to shopping basket with code
        self.assertIn(
            resp.url, reverse('booking:shopping_basket') + '?block_code=foo'
        )


class BlockModalTests(TestSetupMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('booking:blocks_modal')

    def setUp(self):
        super().setUp()
        self.client.login(username=self.user.username, password='test')

    def test_block_modal_no_blocks(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context['active_blocks'], [])
        self.assertEqual(resp.context['unpaid_blocks'], [])
        self.assertTrue('can_book_block')

    def test_block_modal_with_blocks(self):
        unpaid_block = mommy.make_recipe(
            'booking.block_5', user=self.user, paid=False,
            start_date=timezone.now()-timedelta(days=1)
        )
        paid_block = mommy.make_recipe(
            'booking.block_5', user=self.user, paid=True,
            start_date=timezone.now()-timedelta(days=1)
        )
        # expired
        mommy.make_recipe(
            'booking.block_5', user=self.user, paid=True,
            start_date=timezone.now()-timedelta(days=365)
        )
        full_block = mommy.make_recipe(
            'booking.block_5', user=self.user, paid=True,
            start_date=timezone.now()-timedelta(days=1)
        )
        for i in range(5):
            mommy.make_recipe('booking.booking', block=full_block)

        # paid and active, different user
        mommy.make_recipe(
            'booking.block_5', paid=True, start_date=timezone.now()-timedelta(days=1)
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.context['active_blocks'], (paid_block,))
        self.assertEqual(resp.context['unpaid_blocks'], [unpaid_block])
