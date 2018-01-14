from datetime import datetime, timedelta
from model_mommy import mommy

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from accounts.models import OnlineDisclaimer
from activitylog.models import ActivityLog
from booking.forms import BlockCreateForm
from booking.models import Block, BlockVoucher, UsedBlockVoucher
from booking.views import BlockCreateView, BlockDeleteView, BlockListView
from common.tests.helpers import _create_session, format_content, \
    setup_view, TestSetupMixin


class BlockCreateViewTests(TestSetupMixin, TestCase):

    def setUp(self):
        super(BlockCreateViewTests, self).setUp()
        self.user_no_disclaimer = mommy.make_recipe('booking.user')

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
        self.assertIn(resp.url, reverse('booking:block_list'))
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

        resp = self._get_response(user)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Block.objects.all().count(), 4)
        self.assertEqual(resp.context_data['blocks'].count(), 1)


    def test_cart_items_removed_from_session_if_no_unpaid_blocks(self):
        self.client.login(username=self.user.username, password='test')
        unpaid = mommy.make_recipe(
            'booking.block_5', user=self.user,
            start_date=timezone.now() - timedelta(10)
        )
        session = self.client.session
        session['cart_items'] = 'block {} {}'.format(unpaid.id, self.user.email)
        session.save()
        self.assertEqual(
            self.client.session['cart_items'],
            'block {} {}'.format(unpaid.id, self.user.email)
        )

        # make block paid and get again
        unpaid.paid = True
        unpaid.save()
        self.client.get(self.url)
        self.assertIsNone(self.client.session.get('cart_items'))

    def test_paid_and_expired_blocks_do_not_show_paypal_form(self):
        mommy.make_recipe(
            'booking.block_5', user=self.user,
            start_date=timezone.now() - timedelta(365)
        )
        unpaid = mommy.make_recipe(
            'booking.block_5', user=self.user,
            start_date=timezone.now() - timedelta(10)
        )
        mommy.make_recipe(
            'booking.block_5', user=self.user, paid=True,
            start_date=timezone.now() - timedelta(1)
        )

        resp = self._get_response(self.user)
        self.assertEqual(resp.status_code, 200)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(
            paypal_form.initial['custom'],
            'block {} {}'.format(unpaid.id, self.user.email)
        )

    def test_disclaimer_messages(self):
        mommy.make_recipe('booking.blocktype5')
        user = User.objects.create_user(
            username='test_no_disc', email='test@test.com', password='test'
        )
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

    def test_submitting_voucher_code(self):
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(self.block_type)
        block = mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )

        self.client.login(username=self.user.username, password='test')

        # On get, show standard costs
        resp = self.client.get(self.url)
        self.assertIn('£30.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount_1'], 30.00)
        self.assertNotIn('voucher', resp.context_data)

        # On post, show discounted costs
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertIn('£27.00', resp.rendered_content)

        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount_1'], 27.00)
        self.assertEqual(resp.context_data['voucher'], voucher)

    def test_no_voucher_code(self):
        self.client.login(username=self.user.username, password='test')
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': ''}
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'No code provided')

    def test_invalid_voucher_code(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(self.block_type)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'foo'}
        resp = self.client.post(self.url, form_data)
        self.assertEqual(resp.context_data['voucher_error'], 'Invalid code')

    def test_voucher_code_not_started_yet(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            start_date=timezone.now() + timedelta(2)
        )
        voucher.block_types.add(self.block_type)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code is not valid until {}'.format(
                voucher.start_date.strftime("%d %b %y")
            )
        )

    def test_expired_voucher(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            start_date=timezone.now() - timedelta(4),
            expiry_date=timezone.now() - timedelta(2)
        )
        voucher.block_types.add(self.block_type)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'], 'Voucher code has expired'
        )

    def test_voucher_used_max_times(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            max_vouchers=2
        )
        voucher.block_types.add(self.block_type)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedBlockVoucher.objects.create(voucher=voucher, user=user)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher has limited number of uses and has now expired'
        )

    def test_voucher_used_max_times_by_user(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            max_vouchers=6, max_per_user=2
        )
        voucher.block_types.add(self.block_type)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedBlockVoucher.objects.create(voucher=voucher, user=user)
        for i in range(2):
            UsedBlockVoucher.objects.create(voucher=voucher, user=self.user)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)

        # Used vouchers is < 6, but this user has used their max (2)
        self.assertLess(
            UsedBlockVoucher.objects.filter(voucher=voucher).count(),
            voucher.max_vouchers,
        )
        self.assertEqual(
            resp.context_data['voucher_error'],
            'Voucher code has already been used the maximum number of '
            'times (2)'
        )

    def test_voucher_only_shows_discount_for_valid_block_types(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(self.block_type)
        # valid block, cost=30, discounted cost = 27
        block1 = mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        # valid block, cost=50
        block2 = mommy.make(
            'booking.block', user=self.user, block_type__cost=50
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertIn('£27.00', resp.rendered_content)
        self.assertIn('£50.00', resp.rendered_content)

        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount_1'], 50.00)
        self.assertEqual(paypal_form.initial['amount_2'], 27.00)
        self.assertEqual(
            paypal_form.initial['custom'],
            'block {} {} test'.format(
                ','.join([str(id) for id in [block2.id, block1.id]]),
                self.user.email
            )
        )

    def test_voucher_no_valid_block_types(self):
        self.client.login(username=self.user.username, password='test')
        mommy.make(BlockVoucher, code='test', discount=10)
        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)

        # paypal form has non-discounted amount
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount_1'], 30.00)

        self.assertEqual(
            resp.context_data['voucher_error'],
            'Code is not valid for any of your currently unpaid blocks'
        )

    def test_voucher_not_valid_for_some_block_types(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(self.block_type)

        invalid_block_type = mommy.make_recipe('booking.blocktype5', cost=30)

        mommy.make('booking.block', block_type=self.block_type, user=self.user)
        mommy.make(
            'booking.block', block_type=invalid_block_type, user=self.user
        )

        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)

        self.assertIsNone(resp.context_data.get('voucher_error'))
        self.assertEqual(
            resp.context_data['voucher_msg'],
            [
                'Voucher cannot be used for some block types ({})'.format(
                    str(invalid_block_type)
                )
            ]
        )

    def test_remove_extra_spaces_from_voucher_code(self):
        """
        Test that extra leading and/or trailing spaces in code are ignored
        """
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(BlockVoucher, code='test', discount=10)
        voucher.block_types.add(self.block_type)
        block = mommy.make(
            'booking.block', block_type=self.block_type, user=self.user
        )

        form_data = {'apply_voucher': 'Apply', 'code': '  test '}
        resp = self.client.post(self.url, form_data)
        self.assertIn('£27.00', resp.rendered_content)
        paypal_form = resp.context_data['paypalform']
        self.assertEqual(paypal_form.initial['amount_1'], 27.00)

        self.assertEqual(
            paypal_form.initial['custom'], 'block {} {} {}'.format(
                block.id, self.user.email, voucher.code
            )
        )

    def test_voucher_will_be_used_max_total_times_with_basket_blocks(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            max_vouchers=3, max_per_user=10
        )
        voucher.block_types.add(self.block_type)
        users = mommy.make_recipe('booking.user', _quantity=2)
        for user in users:
            UsedBlockVoucher.objects.create(voucher=voucher, user=user)

        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user,
            _quantity=2
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertIsNone(resp.context_data.get('voucher_error'))
        self.assertEqual(
            resp.context_data['voucher_msg'],
            ['Voucher not applied to some blocks; voucher '
            'has limited number of total uses.']
        )

    def test_voucher_will_be_used_up_for_user_with_basket_blocks(self):
        self.client.login(username=self.user.username, password='test')
        voucher = mommy.make(
            BlockVoucher, code='test', discount=10,
            max_per_user=3
        )
        voucher.block_types.add(self.block_type)
        mommy.make(
            UsedBlockVoucher, voucher=voucher, user=self.user, _quantity=2
        )

        mommy.make(
            'booking.block', block_type=self.block_type, user=self.user,
            _quantity=2
        )
        form_data = {'apply_voucher': 'Apply', 'code': 'test'}
        resp = self.client.post(self.url, form_data)
        self.assertIsNone(resp.context_data.get('voucher_error'))
        self.assertEqual(
            resp.context_data['voucher_msg'],
            ['Voucher not applied to some blocks; you can only use this '
             'voucher a total of 3 times.']
        )


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
