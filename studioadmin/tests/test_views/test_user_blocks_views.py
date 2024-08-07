from datetime import timedelta
from model_bakery import baker

from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from booking.models import Block
from common.tests.helpers import format_content
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserBlocksViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBlocksViewTests, self).setUp()
        self.block = baker.make_recipe('booking.block', user=self.user)
        self.url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        self.client.force_login(self.staff_user)

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': str(self.block.id),
            'blocks-0-block_type': str(self.block.block_type.id),
            'blocks-0-start_date': self.block.start_date.strftime('%d %b %Y'),
            'blocks-0-paid': self.block.paid
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        self.client.logout()
        resp = self.client.get(self.url)
        redirected_url = reverse('account_login') + "?next={}".format(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
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

    def test_view_users_blocks(self):
        """
        Test only user's bookings for future events shown by default
        """
        new_user = baker.make_recipe('booking.user')
        new_blocks = baker.make_recipe(
            'booking.block', user=new_user, _quantity=2
        )
        self.assertEqual(Block.objects.count(), 3)
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': new_user.id}
        )
        resp = self.client.get(url)
        # get all but last form (last form is the empty extra one)
        block_forms = resp.context_data['userblockformset'].forms[:-1]
        self.assertEqual(len(block_forms), 2)

        new_blocks.reverse()  # blocks are shown in reverse order by start date
        self.assertEqual(
            [block.instance for block in block_forms],
            new_blocks
        )

    def test_can_update_block(self):
        self.assertFalse(self.block.paid)
        self.client.post(
            self.url,
            self.formset_data({'blocks-0-paid': True})
        )
        block = Block.objects.get(id=self.block.id)
        self.assertTrue(block.paid)

    def test_can_create_block(self):
        block_type = baker.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        self.client.post(
            self.url,
            self.formset_data(
                {
                    'blocks-TOTAL_FORMS': 2,
                    'blocks-1-block_type': block_type.id
                }
            )
        )
        self.assertEqual(Block.objects.count(), 2)

    def test_can_create_block_without_start_date(self):
        block_type = baker.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        self.client.post(
            self.url,
            self.formset_data(
                {
                    'blocks-TOTAL_FORMS': 2,
                    'blocks-1-block_type': block_type.id,
                    'blocks-1-start_date': ''
                }
            )
        )
        self.assertEqual(Block.objects.count(), 2)
        new_block = Block.objects.latest('id')
        today = timezone.now()
        self.assertEqual(new_block.start_date.day, today.day)

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user block list
        """
        resp = self.client.post(
            self.url, self.formset_data()
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_blocks_list',
                kwargs={'user_id': self.user.id}
            ) + '?page='
        )

    def test_delete_block(self):
        self.assertFalse(self.block.paid)
        self.client.post(
            self.url,
            self.formset_data({'blocks-0-DELETE': True})
        )
        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(id=self.block.id)

    def test_submitting_with_form_errors_shows_messages(self):
        block_type = baker.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        data = self.formset_data(
            {
                'blocks-TOTAL_FORMS': 2,
                'blocks-1-block_type': block_type.id,
                'blocks-1-start_date': '34 Jan 2023'
            }
        )
        resp = self.client.post(self.url, data)

        self.assertIn(
            'There were errors in the following fields:start_date',
            format_content(resp.rendered_content)
        )
        self.assertEqual(Block.objects.count(), 1)

    def test_block_pagination(self):
        # Blocks are paginated by 10
        for i in range(20):
            baker.make_recipe(
                'booking.block', user=self.user,
                start_date=timezone.now()+timedelta(1+i)
            )

        self.assertEqual(Block.objects.filter(user=self.user).count(), 21)

        # no page in url, shows first page
        resp = self.client.get(self.url)
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

        # page 1
        resp = self.client.get(self.url + '?page=1')
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

        # page number > max pages gets last page
        resp = self.client.get(self.url + '?page=4')
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 1)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 3)

        # page not a number > gets first page
        resp = self.client.get(self.url + '?page=foo')
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page_obj']
        self.assertEqual(paginator.number, 1)

    def test_post_with_page(self):
        # Post return same page number
        new_blocks = baker.make_recipe('booking.block', user=self.user, _quantity=15)
        self.assertEqual(Block.objects.filter(user=self.user).count(), 16)

        data = self.formset_data(
            {
                'blocks-INITIAL_FORMS': 16,
                'blocks-TOTAL_FORMS': 16,
                'page': '2'
            }
        )

        for i, block in enumerate(new_blocks, 1):
            data['blocks-{}-id'.format(i)] = block.id
            data['blocks-{}-block_type'.format(i)] = block.block_type.id
            data['blocks-{}-start_date'.format(i)] = block.start_date.strftime(
                '%d %b %Y'
            ),
            data['blocks-{}-paid'.format(i)] = self.block.paid

        resp = self.client.post(
           self.url, data
        )

        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ) + '?page=2'
        )
