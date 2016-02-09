from datetime import datetime
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Block
from booking.tests.helpers import _create_session
from studioadmin.views import BlockListView
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class BlockListViewTests(TestPermissionMixin, TestCase):

    def _get_response(self, user, form_data={}):
        url = reverse('studioadmin:blocks')
        session = _create_session()
        request = self.factory.get(url, form_data)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        view = BlockListView.as_view()
        return view(request)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse('studioadmin:blocks')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user)
        self.assertEquals(resp.status_code, 200)

    def test_current_blocks_returned_on_get(self):
        active_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = mommy.make_recipe(
            'booking.block', paid=False, _quantity=3
        )
        current_blocks = active_blocks + unpaid_blocks
        full_block = mommy.make_recipe(
            'booking.block', paid=False, block_type__size=1
        )
        mommy.make_recipe('booking.booking', block=full_block)

        resp = self._get_response(self.staff_user)
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(
                id__in=[block.id for block in current_blocks]
            ).order_by('user__first_name')
            )
        )

    def test_block_status_filter(self):
        active_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = mommy.make_recipe(
            'booking.block', _quantity=3, paid=False
        )
        current_blocks = active_blocks + unpaid_blocks
        expired_blocks = mommy.make_recipe(
            'booking.block', paid=True,
            start_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        unpaid_expired_blocks = mommy.make_recipe(
            'booking.block', paid=False,
            start_date=datetime(2000, 1, 1, tzinfo=timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        full_blocks = mommy.make_recipe(
            'booking.block', paid=True,
            block_type__size=1,
            _quantity=3
        )
        for block in full_blocks:
            mommy.make_recipe('booking.booking', block=block)

        # all blocks
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'all'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.all().order_by('user__first_name'))
        )
        # active blocks are paid and not expired
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'active'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in active_blocks]
                ).order_by('user__first_name')
            )
        )

        # unpaid blocks are unpaid but not expired; should not show any
        # from unpaid_expired_blocks
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'unpaid'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in unpaid_blocks]
                ).order_by('user__first_name')
            )
        )

        #current blocks are paid or unpaid, not expired, not full
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'current'}
        )
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(
                id__in=[block.id for block in current_blocks]
            ).order_by('user__first_name')
            )
        )

        # expired blocks are past expiry date or full
        resp = self._get_response(
            self.staff_user, form_data={'block_status': 'expired'}
        )
        expired = expired_blocks + unpaid_expired_blocks + full_blocks
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in expired]
                ).order_by('user__first_name')
            )
        )
