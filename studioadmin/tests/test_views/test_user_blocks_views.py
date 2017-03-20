from datetime import timedelta
from model_mommy import mommy

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from booking.models import Block
from booking.tests.helpers import _create_session, format_content
from studioadmin.views import user_blocks_view
from studioadmin.tests.test_views.helpers import TestPermissionMixin


class UserBlocksViewTests(TestPermissionMixin, TestCase):

    def setUp(self):
        super(UserBlocksViewTests, self).setUp()
        self.block = mommy.make_recipe('booking.block', user=self.user)

    def _get_response(self, user, user_id):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.get(url)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def _post_response(self, user, user_id, form_data):
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': user_id}
        )
        session = _create_session()
        request = self.factory.post(url, form_data, follow=True)
        request.session = session
        request.user = user
        messages = FallbackStorage(request)
        request._messages = messages
        return user_blocks_view(request, user_id)

    def formset_data(self, extra_data={}):

        data = {
            'blocks-TOTAL_FORMS': 1,
            'blocks-INITIAL_FORMS': 1,
            'blocks-0-id': str(self.block.id),
            'blocks-0-block_type': str(self.block.block_type.id),
            'blocks-0-start_date': self.block.start_date.strftime(
                '%Y-%m-%d %H:%M:%S'
            ),
            'initial-blocks-0-start_date': self.block.start_date.strftime(
                '%Y-%m-%d %H:%M:%S'
            ),
            'blocks-0-paid': self.block.paid
            }

        for key, value in extra_data.items():
            data[key] = value

        return data

    def test_cannot_access_if_not_logged_in(self):
        """
        test that the page redirects if user is not logged in
        """
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        resp = self.client.get(url)
        redirected_url = reverse('account_login') + "?next={}".format(url)
        self.assertEquals(resp.status_code, 302)
        self.assertIn(redirected_url, resp.url)

    def test_cannot_access_if_not_staff(self):
        """
        test that the page redirects if user is not a staff user
        """
        resp = self._get_response(self.user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_instructor_group_cannot_access(self):
        """
        test that the page redirects if user is in the instructor group but is
        not a staff user
        """
        resp = self._get_response(self.instructor_user, self.user.id)
        self.assertEquals(resp.status_code, 302)
        self.assertEquals(resp.url, reverse('booking:permission_denied'))

    def test_can_access_as_staff_user(self):
        """
        test that the page can be accessed by a staff user
        """
        resp = self._get_response(self.staff_user, self.user.id)
        self.assertEquals(resp.status_code, 200)

    def test_view_users_blocks(self):
        """
        Test only user's bookings for future events shown by default
        """
        new_user = mommy.make_recipe('booking.user')
        new_blocks = mommy.make_recipe(
            'booking.block', user=new_user, _quantity=2
        )
        self.assertEqual(Block.objects.count(), 3)
        resp = self._get_response(self.staff_user, new_user.id)
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
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data({'blocks-0-paid': True})
        )
        block = Block.objects.get(id=self.block.id)
        self.assertTrue(block.paid)

    def test_can_create_block(self):
        block_type = mommy.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        resp = self._post_response(
            self.staff_user, self.user.id,
            self.formset_data(
                {
                    'blocks-TOTAL_FORMS': 2,
                    'blocks-1-block_type': block_type.id
                }
            )
        )
        self.assertEqual(Block.objects.count(), 2)

    def test_formset_unchanged(self):
        """
        test formset submitted unchanged redirects back to user block list
        """
        resp = self._post_response(
            self.staff_user, self.user.id, self.formset_data()
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
        self._post_response(
            self.staff_user, self.user.id,
            self.formset_data({'blocks-0-DELETE': True})
        )
        with self.assertRaises(Block.DoesNotExist):
            Block.objects.get(id=self.block.id)

    def test_submitting_with_form_errors_shows_messages(self):
        block_type = mommy.make_recipe('booking.blocktype')
        self.assertEqual(Block.objects.count(), 1)
        data = self.formset_data(
            {
                'blocks-TOTAL_FORMS': 2,
                'blocks-1-block_type': block_type.id,
                'blocks-1-start_date': '34 Jan 2023'
            }
        )
        url = reverse(
            'studioadmin:user_blocks_list',
            kwargs={'user_id': self.user.id}
        )
        self.client.login(username=self.staff_user.username, password='test')
        resp = self.client.post(url, data)

        self.assertIn(
            'There were errors in the following fields:start_date',
            format_content(resp.rendered_content)
        )
        self.assertEqual(Block.objects.count(), 1)

    def test_block_pagination(self):
        # Blocks are paginated by 10
        for i in range(20):
            mommy.make(
                'booking.block', user=self.user,
                start_date=timezone.now()+timedelta(1+i)
            )

        self.assertEqual(Block.objects.filter(user=self.user).count(), 21)

        self.client.login(username=self.staff_user.username, password='test')
        # no page in url, shows first page
        resp = self.client.get(
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            )
        )
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page']
        self.assertEqual(paginator.number, 1)

        # page 1
        resp = self.client.get(
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ) + '?page=1'
        )
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page']
        self.assertEqual(paginator.number, 1)

        # page number > max pages gets last page
        resp = self.client.get(
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ) + '?page=4'
        )
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 1)
        paginator = resp.context_data['page']
        self.assertEqual(paginator.number, 3)

        # page not a number > gets first page
        resp = self.client.get(
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ) + '?page=foo'
        )
        blocks = resp.context_data['userblockformset'].queryset
        self.assertEqual(blocks.count(), 10)
        paginator = resp.context_data['page']
        self.assertEqual(paginator.number, 1)

    def test_post_with_page(self):
        # Post return same page number
        new_blocks = mommy.make('booking.block', user=self.user, _quantity=15)
        self.assertEqual(Block.objects.filter(user=self.user).count(), 16)

        self.client.login(username=self.staff_user.username, password='test')

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
                '%Y-%m-%d %H:%M:%S'
            ),
            data['blocks-{}-paid'.format(i)] = self.block.paid

        resp = self.client.post(
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ), data
        )

        self.assertEqual(
            resp.url,
            reverse(
                'studioadmin:user_blocks_list', args=[self.user.id]
            ) + '?page=2'
        )
