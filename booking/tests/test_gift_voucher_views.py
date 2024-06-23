from model_bakery import baker

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import override_settings, TestCase

from booking.models import Event, BlockVoucher, EventVoucher, GiftVoucherType
from common.tests.helpers import TestSetupMixin
from payments.models import PaypalGiftVoucherTransaction
from payments.helpers import create_gift_voucher_paypal_transaction


class GiftVoucherTestMixin(TestSetupMixin):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.eventtype_pc = baker.make_recipe('booking.event_type_PC')
        eventtype_pp = baker.make_recipe('booking.event_type_PP')
        # Need to make at least one event of each type, it'll be used for the voucher cost
        baker.make(Event, event_type=cls.eventtype_pc, cost=10)
        baker.make(Event, event_type=eventtype_pp, cost=5)
        cls.blocktype5 = baker.make_recipe('booking.blocktype5', cost=20)
        cls.blocktype10 = baker.make_recipe('booking.blocktype10', cost=40)

        cls.event_voucher_type1 = baker.make(GiftVoucherType, event_type=cls.eventtype_pc)
        cls.event_voucher_type2 = baker.make(GiftVoucherType, event_type=eventtype_pp)
        cls.block_voucher_type1 = baker.make(GiftVoucherType, block_type=cls.blocktype5)
        cls.block_voucher_type2 = baker.make(GiftVoucherType, block_type=cls.blocktype10)


class TestGiftVoucherPurchseView(GiftVoucherTestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url = reverse("booking:buy_gift_voucher")

    def test_gift_voucher_view_no_login_required(self):
        response = self.client.get(self.url)
        assert response.status_code == 200

    def test_gift_voucher_view_with_login_populated_email_fields(self):
        self.client.login(username=self.user.username, password="test")
        response = self.client.get(self.url)
        assert response.context_data['form'].fields["user_email"].initial == "test@test.com"
        assert response.context_data['form'].fields["user_email1"].initial == "test@test.com"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_purchase_gift_voucher_event(self):
        assert EventVoucher.objects.exists() is False
        assert BlockVoucher.objects.exists() is False
        data = {
            'voucher_type': self.event_voucher_type1.id,
            'user_email': "test@test.com",
            'user_email1': "test@test.com",
            'name': '',
            'message': ''
        }
        resp = self.client.post(self.url, data)
        assert EventVoucher.objects.exists()
        assert BlockVoucher.objects.exists() is False

        voucher = EventVoucher.objects.first()
        assert voucher.activated is False
        assert voucher.is_gift_voucher
        assert self.event_voucher_type1.event_type in voucher.event_types.all()
        assert voucher.event_types.count() == 1
        assert voucher.purchaser_email == 'test@test.com'
        assert voucher.discount == 100
        assert voucher.max_per_user == 1
        assert voucher.max_vouchers == 1

        assert "paypal_form" in resp.context_data

    @override_settings(PAYMENT_METHOD="paypal")
    def test_purchase_gift_voucher_block(self):
        assert EventVoucher.objects.exists() is False
        assert BlockVoucher.objects.exists() is False
        data = {
            'voucher_type': self.block_voucher_type1.id,
            'user_email': "test@test.com",
            'user_email1': "test@test.com",
            'recipient_name': 'Donald Duck',
            'message': 'Quack'
        }
        resp = self.client.post(self.url, data)
        assert BlockVoucher.objects.exists()
        assert EventVoucher.objects.exists() is False

        voucher = BlockVoucher.objects.first()
        assert voucher.activated is False
        assert voucher.is_gift_voucher
        assert self.block_voucher_type1.block_type in voucher.block_types.all()
        assert voucher.block_types.count() == 1
        assert voucher.purchaser_email, 'test@test.com'
        assert voucher.discount == 100
        assert voucher.max_per_user == 1
        assert voucher.max_vouchers == 1
        assert voucher.name == 'Donald Duck'
        assert voucher.message == "Quack"

        assert "paypal_form" in resp.context_data

    def test_purchase_gift_voucher_invalid_email(self):
        data = {
            'voucher_type': self.block_voucher_type1.id,
            'user_email': "test@test.com",
            'user_email1': "test1@test.com",
            'recipient_name': 'Donald Duck',
            'message': 'Quack'
        }
        resp = self.client.post(self.url, data)
        assert resp.status_code == 200
        assert resp.context_data["form"].errors == {
            "user_email1": ["Email addresses do not match"]
        }


class TestGiftVoucherUpdateView(GiftVoucherTestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url_string = "booking:gift_voucher_update"

    @override_settings(PAYMENT_METHOD="paypal")
    def test_update_gift_voucher(self):
        # deactivated gift voucher redirects to payment view
        # voucher type not changed, voucher has same id
        event_voucher = baker.make_recipe(
            "booking.event_gift_voucher", purchaser_email="test@test.com", name="Donald Duck", message="Quack",
        )
        event_voucher.event_types.add(self.eventtype_pc)
        data = {
            'voucher_type': self.event_voucher_type1.id,
            'user_email': "new@test.com",
            'user_email1': "new@test.com",
            'recipient_name': 'Mickey Mouse',
            'message': 'Hello'
        }
        resp = self.client.post(reverse(self.url_string, args=(event_voucher.code,)), data)
        assert EventVoucher.objects.count() == 1
        updated_voucher = EventVoucher.objects.first()
        assert updated_voucher.id == event_voucher.id
        assert updated_voucher.purchaser_email == "new@test.com"
        assert updated_voucher.name == "Mickey Mouse"
        assert updated_voucher.message == "Hello"
        assert updated_voucher.activated == False
        assert "paypal_form" in resp.context_data

    @override_settings(PAYMENT_METHOD="paypal")
    def test_update_gift_voucher_existing_paypal_payment_transaction(self):
        # deactivated gift voucher redirects to payment view, same invoice number
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher",
            purchaser_email="test@test.com", name="Donald Duck", message="Quack"
        )
        block_voucher.block_types.add(self.blocktype5)
        create_gift_voucher_paypal_transaction(self.block_voucher_type1, block_voucher.code)
        assert PaypalGiftVoucherTransaction.objects.count() == 1
        ppt = PaypalGiftVoucherTransaction.objects.first()
        data = {
            'voucher_type': self.block_voucher_type1.id,
            'user_email': "new@test.com",
            'user_email1': "new@test.com",
            'recipient_name': 'Mickey Mouse',
            'message': 'Hello'
        }
        resp = self.client.post(reverse(self.url_string, args=(block_voucher.code,)), data)
        assert BlockVoucher.objects.count() == 1
        updated_voucher = BlockVoucher.objects.first()

        assert updated_voucher.id == block_voucher.id
        assert "paypal_form" in resp.context_data
        # still just the one ppt
        assert resp.context_data["paypal_form"].fields["invoice"].initial == ppt.invoice_id
        assert PaypalGiftVoucherTransaction.objects.count() == 1
        assert PaypalGiftVoucherTransaction.objects.first().id == ppt.id

    @override_settings(PAYMENT_METHOD="paypal")
    def test_update_gift_voucher_change_voucher_block_type(self):
        # deactivated gift voucher, changing between block types keeps same voucher
        # original paypal payment transaction updated
        # deactivated gift voucher redirects to payment view, same invoice number
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com"
        )
        block_voucher.block_types.add(self.blocktype5)
        create_gift_voucher_paypal_transaction(self.block_voucher_type1, block_voucher.code)

        assert PaypalGiftVoucherTransaction.objects.count() == 1
        ppt = PaypalGiftVoucherTransaction.objects.first()
        data = {
            'voucher_type': self.block_voucher_type2.id,
            'user_email': "test@test.com",
            'user_email1': "test@test.com",
            'recipient_name': '',
            'message': ''
        }

        # different block type, but still a block voucher rather than an event voucher, so the voucher id is the same
        resp = self.client.post(reverse(self.url_string, args=(block_voucher.code,)), data)
        assert BlockVoucher.objects.count() == 1
        updated_voucher = BlockVoucher.objects.first()
        assert updated_voucher.id == block_voucher.id
        assert updated_voucher.block_types.count() == 1
        assert self.block_voucher_type2.block_type in updated_voucher.block_types.all()

        # still just the one ppt, but it's voucher type has changed
        assert resp.context_data["paypal_form"].fields["invoice"].initial == ppt.invoice_id
        assert PaypalGiftVoucherTransaction.objects.count() == 1
        assert PaypalGiftVoucherTransaction.objects.first().id == ppt.id
        ppt.refresh_from_db()
        assert ppt.voucher_type == self.block_voucher_type2

    @override_settings(PAYMENT_METHOD="paypal")
    def test_update_gift_voucher_change_voucher_event_type(self):
        # deactivated gift voucher, changing between event types keeps same voucher
        # original paypal payment transaction updated
        # deactivated gift voucher redirects to payment view, same invoice number
        event_voucher = baker.make_recipe(
            "booking.event_gift_voucher", purchaser_email="test@test.com"
        )
        event_voucher.event_types.add(self.event_voucher_type1.event_type)
        create_gift_voucher_paypal_transaction(self.event_voucher_type1, event_voucher.code)

        assert PaypalGiftVoucherTransaction.objects.count() == 1
        ppt = PaypalGiftVoucherTransaction.objects.first()
        data = {
            'voucher_type': self.event_voucher_type2.id,
            'user_email': "test@test.com",
            'user_email1': "test@test.com",
            'recipient_name': '',
            'message': ''
        }

        # different block type, but still a block voucher rather than an event voucher, so the voucher id is the same
        resp = self.client.post(reverse(self.url_string, args=(event_voucher.code,)), data)
        assert EventVoucher.objects.count() == 1
        updated_voucher = EventVoucher.objects.first()
        assert updated_voucher.id == event_voucher.id
        assert updated_voucher.event_types.count() == 1
        assert self.event_voucher_type2.event_type in updated_voucher.event_types.all()

        # still just the one ppt, but it's voucher type has changed
        assert resp.context_data["paypal_form"].fields["invoice"].initial == ppt.invoice_id
        assert PaypalGiftVoucherTransaction.objects.count() == 1
        assert PaypalGiftVoucherTransaction.objects.first().id == ppt.id
        ppt.refresh_from_db()
        assert ppt.voucher_type == self.event_voucher_type2

    @override_settings(PAYMENT_METHOD="paypal") 
    def test_update_gift_voucher_change_voucher_type(self):
        # deactivated gift voucher, changing block type to event type deletes and recreates voucher
        # original paypal payment transaction updated
        # deactivated gift voucher redirects to payment view, same invoice number
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com"
        )
        block_voucher.block_types.add(self.blocktype5)
        create_gift_voucher_paypal_transaction(self.block_voucher_type1, block_voucher.code)

        assert PaypalGiftVoucherTransaction.objects.count() == 1
        ppt = PaypalGiftVoucherTransaction.objects.first()
        data = {
            'voucher_type': self.event_voucher_type1.id,
            'user_email': "test@test.com",
            'user_email1': "test@test.com",
            'recipient_name': '',
            'message': ''
        }

        # different block type, but still a block voucher rather than an event voucher, so the voucher id is the same
        resp = self.client.post(reverse(self.url_string, args=(block_voucher.code,)), data)
        assert BlockVoucher.objects.exists() is False
        assert EventVoucher.objects.count() == 1
        updated_voucher = EventVoucher.objects.first()
        assert updated_voucher.event_types.count() == 1
        assert self.event_voucher_type1.event_type in updated_voucher.event_types.all()

        # still just the one ppt, but it's voucher type has changed
        assert resp.context_data["paypal_form"].fields["invoice"].initial == ppt.invoice_id
        assert PaypalGiftVoucherTransaction.objects.count() == 1
        assert PaypalGiftVoucherTransaction.objects.first().id == ppt.id
        ppt.refresh_from_db()
        assert ppt.voucher_type == self.event_voucher_type1

    def test_update_activated_gift_voucher(self):
        # can't update voucher type or email
        # redirects to voucher detail page
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com", activated=True
        )
        block_voucher.block_types.add(self.blocktype5)

        data = {
            'voucher_type': self.block_voucher_type2.id,
            'user_email': "new@test.com",
            'user_email1': "new@test.com",
            'recipient_name': 'Test',
            'message': 'Test message'
        }
        resp = self.client.post(reverse(self.url_string, args=(block_voucher.code,)), data)
        assert BlockVoucher.objects.count() == 1
        block_voucher.refresh_from_db()
        # Attempt to update voucher type and email ignored
        assert block_voucher.block_types.count() == 1
        assert block_voucher.block_types.first() == self.block_voucher_type1.block_type
        assert block_voucher.purchaser_email == "test@test.com"
        # name and message can be updated
        assert block_voucher.name == "Test"
        assert block_voucher.message == "Test message"

        assert resp.url == reverse("booking:gift_voucher_details", args=(block_voucher.code,))


class TestGiftVoucherDeleteView(GiftVoucherTestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url_string = "booking:gift_voucher_delete"

    def test_delete_gift_voucher(self):
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com"
        )
        block_voucher.block_types.add(self.blocktype5)
        self.client.post(reverse(self.url_string, args=(block_voucher.code,)))
        assert BlockVoucher.objects.exists() is False

        event_voucher = baker.make_recipe(
            "booking.event_gift_voucher", purchaser_email="test@test.com"
        )
        event_voucher.event_types.add(self.event_voucher_type1.event_type)
        self.client.post(reverse(self.url_string, args=(event_voucher.code,)))
        assert EventVoucher.objects.exists() is False

    def test_delete_activated_gift_voucher(self):
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com", activated=True
        )
        block_voucher.block_types.add(self.blocktype5)
        resp = self.client.post(reverse(self.url_string, args=(block_voucher.code,)))
        assert BlockVoucher.objects.filter(id=block_voucher.id).exists()
        assert resp.url == reverse("booking:permission_denied")


class TestGiftVoucherDetailView(GiftVoucherTestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.url_string = "booking:gift_voucher_details"

    def test_detail_view_block_voucher(self):
        block_voucher = baker.make_recipe(
            "booking.block_gift_voucher", purchaser_email="test@test.com", activated=True
        )
        block_voucher.block_types.add(self.blocktype5)
        resp = self.client.get(reverse(self.url_string, args=(block_voucher.code,)))
        assert resp.status_code == 200

    def test_detail_view_event_voucher(self):
        event_voucher = baker.make_recipe(
            "booking.event_gift_voucher", purchaser_email="test@test.com", activated=True
        )
        event_voucher.event_types.add(self.event_voucher_type1.event_type)
        resp = self.client.get(reverse(self.url_string, args=(event_voucher.code,)))
        assert resp.status_code == 200
