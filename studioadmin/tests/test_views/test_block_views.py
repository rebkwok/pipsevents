from datetime import datetime
from datetime import timezone as dt_timezone

from model_bakery import baker

from django.urls import reverse
from django.test import TestCase

from booking.models import Block
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class BlockListViewTests(TestPermissionMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse('studioadmin:blocks')

    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        url = reverse('studioadmin:blocks')
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.logout()
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        self.client.logout()
        self.client.force_login(self.instructor_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_current_blocks_returned_on_get(self):
        active_blocks = baker.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = baker.make_recipe(
            'booking.block', paid=False, _quantity=3
        )
        current_blocks = active_blocks + unpaid_blocks
        full_block = baker.make_recipe(
            'booking.block', paid=False, block_type__size=1
        )
        baker.make_recipe('booking.booking', block=full_block)

        resp = self.client.get(self.url)
        self.assertEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(
                id__in=[block.id for block in current_blocks]
            ).order_by('user__first_name')
            )
        )

    def test_block_status_filter(self):
        active_blocks = baker.make_recipe(
            'booking.block', _quantity=3, paid=True
        )
        unpaid_blocks = baker.make_recipe(
            'booking.block', _quantity=3, paid=False
        )

        expired_blocks = baker.make_recipe(
            'booking.block', paid=True,
            start_date=datetime(2000, 1, 1, tzinfo=dt_timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        unpaid_expired_blocks = baker.make_recipe(
            'booking.block', paid=False,
            start_date=datetime(2000, 1, 1, tzinfo=dt_timezone.utc),
            block_type__duration=1,
            _quantity=3
        )
        full_blocks = baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1,
            _quantity=3
        )
        transferred_blocks1 = baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1, block_type__identifier='transferred',
            _quantity=3
        )
        transferred_blocks2 = baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1, block_type__identifier='transferred',
            _quantity=3
        )
        current_blocks = active_blocks + unpaid_blocks + \
                         transferred_blocks1 + transferred_blocks2
        for block in full_blocks:
            baker.make_recipe('booking.booking', block=block)

        # all blocks
        resp = self.client.get(self.url, {'block_status': 'all'})
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.all().order_by('user__first_name'))
        )
        # unknown status returns all
        resp = self.client.get(self.url, {'block_status': 'foo'})
        assert len(resp.context_data['blocks']) == Block.objects.count()

        # active blocks are paid and not expired
        resp = self.client.get(self.url, {'block_status': 'active'})
        active = active_blocks + transferred_blocks1 + transferred_blocks2
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in active]
                ).order_by('user__first_name')
            )
        )

        # unpaid blocks are unpaid but not expired; should not show any
        # from unpaid_expired_blocks
        resp = self.client.get(self.url, {'block_status': 'unpaid'})
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in unpaid_blocks]
                ).order_by('user__first_name')
            )
        )

        #current blocks are paid or unpaid, not expired, not full
        resp = self.client.get(self.url, {'block_status': 'current'})
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(Block.objects.filter(
                id__in=[block.id for block in current_blocks]
            ).order_by('user__first_name')
            )
        )

        # expired blocks are past expiry date or full
        resp = self.client.get(self.url, {'block_status': 'expired'})
        expired = expired_blocks + unpaid_expired_blocks + full_blocks
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in expired]
                ).order_by('user__first_name')
            )
        )

        # transferred blocks
        resp = self.client.get(self.url, {'block_status': 'transfers'})
        transfers = transferred_blocks1 + transferred_blocks2
        self.assertCountEqual(
            list(resp.context_data['blocks']),
            list(
                Block.objects.filter(
                    id__in=[block.id for block in transfers]
                ).order_by('user__first_name')
            )
        )

    def test_transferred_from_display(self):

        baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1, block_type__identifier='transferred',
            transferred_booking_id='182893429'
        )
        resp = self.client.get(self.url, {'block_status': 'transfers'})
        self.assertIn('(182893429)', resp.rendered_content)

        resp = self.client.get(self.url, {'block_status': 'all'})
        self.assertNotIn('(182893429)', resp.rendered_content)

    def test_transferred_from_display_with_valid_booking(self):

        booking = baker.make_recipe('booking.booking', status='CANCELLED')

        baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1, block_type__identifier='transferred',
            transferred_booking_id=booking.id
        )
        resp = self.client.get(self.url, {'block_status': 'transfers'})
        self.assertIn(
            '{} {} ({})'.format(
                booking.event.name, booking.event.date.strftime('%d%b%y'),
                booking.id
            ),
            resp.rendered_content
        )

        resp = self.client.get(self.url, {'block_status': 'all'})
        self.assertNotIn(
            '{} {} ({})'.format(
                booking.event.name, booking.event.date.strftime('%d%b%y'),
                booking.id
            ),
            resp.rendered_content
        )

    def test_block_type_identfier_display(self):
        baker.make_recipe(
            'booking.block', paid=True,
            block_type__size=1, block_type__identifier='transferred',
        )
        resp = self.client.get(self.url)
        self.assertIn('(transfer)', resp.rendered_content)

        baker.make_recipe(
            'booking.block', paid=True, block_type__identifier='other id'
        )
        resp = self.client.get(self.url)
        self.assertIn('(other id)', resp.rendered_content)
