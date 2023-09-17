from importlib.metadata import metadata
from os import environ

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.conf import settings
from django.db import models
from django.utils import timezone

from hashlib import sha512
from shortuuid import ShortUUID


class Invoice(models.Model):
    # username(email address) rather than FK; in case we delete the user later, we want to keep financial info
    username = models.CharField(max_length=255, verbose_name="Purchaser email")
    invoice_id = models.CharField(max_length=255)
    amount = models.DecimalField(decimal_places=2, max_digits=8)
    stripe_payment_intent_id = models.CharField(max_length=255, null=True, blank=True)
    # register date created so we can periodically delete any unpaid ones that were created by a user going to the
    # checkout and changing their mind
    date_created = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)
    date_paid = models.DateTimeField(null=True, blank=True)
    total_voucher_code = models.CharField(
        max_length=255, null=True, blank=True, help_text="Voucher applied to invoice total"
    )
    is_stripe_test = models.BooleanField(default=False)

    class Meta:
        ordering = ("-date_paid",)

    def __str__(self):
        return f"{self.invoice_id} - {self.username} - £{self.amount}{' (paid)' if self.paid else ''}"

    @classmethod
    def generate_invoice_id(cls):
        invoice_id = ShortUUID().random(length=22)
        while Invoice.objects.filter(invoice_id=invoice_id).exists():
            invoice_id = ShortUUID().random(length=22)
        return invoice_id

    def signature(self):
        return sha512((self.invoice_id + environ["INVOICE_KEY"]).encode("utf-8")).hexdigest()

    @property
    def payment_intent_ids(self):
        return ", ".join(self.payment_intents.values_list("payment_intent_id", flat=True))

    @property
    def gift_vouchers(self):
        return {
            gift_voucher for gift_voucher in set(self.block_gift_vouchers.all()) | set(self.event_gift_vouchers.all())
        }

    def items_summary(self):
        return {
            "bookings": [booking.event.str_no_location() for booking in self.bookings.all()],
            "blocks": [str(block.block_type) for block in self.blocks.all()],
            "gift_vouchers": [gift_voucher.gift_voucher_type.name for gift_voucher in self.gift_vouchers],
            "ticket_bookings": [str(tb.ticketed_event) for tb in self.ticket_bookings.all()],
        }

    def items_dict(self):
        if self.is_stripe_test:
            return {
                "stripe_test": {
                    "name": "Stripe test payment",
                    "cost_str": "£0.30",
                    "cost_in_p": 30,
                }
            }
        def _cost_str(item):
            cost_str = f"£{item.cost_with_voucher:.2f}"
            if item.voucher_code:
                cost_str = f"{cost_str} (voucher applied: {item.voucher_code})"
            return cost_str
         
        bookings = {
            f"booking_{item.id}": {
                "name": item.event.str_no_location(), 
                "voucher": item.voucher_code,
                "cost_str": _cost_str(item),
                "cost_in_p": int(item.cost_with_voucher * 100),
                "user": item.user,
            } for item in self.bookings.all()
        }
        blocks = {
            f"block_{item.id}": {
                "name": str(item.block_type), 
                "voucher": item.voucher_code,
                "cost_str": _cost_str(item),
                "cost_in_p": int(item.cost_with_voucher * 100),
                "user": item.user,
            } for item in self.blocks.all()
        }
        ticket_bookings = {
            f"ticket_booking_{item.id}": {
                "name": f"Tickets ({item.tickets.count()}) for {item.ticketed_event}", 
                "voucher": None,
                "cost_str":f"£{item.cost:.2f}",
                "cost_in_p": int(item.cost * 100),
                "user": item.user,
            } for item in self.ticket_bookings.all()
        }
        gift_vouchers = {
            f"gift_voucher_{gift_voucher.id}": {
                "name": gift_voucher.gift_voucher_type.name, 
                "cost_str": f"£{gift_voucher.gift_voucher_type.cost:.2f}", 
                "cost_in_p": int(gift_voucher.gift_voucher_type.cost * 100)
            } for gift_voucher in self.gift_vouchers
        }

        return {**bookings, **ticket_bookings, **blocks, **gift_vouchers}

    def _item_counts(self):
        return {
            "bookings": self.bookings.count(),
            "blocks": self.blocks.count(),
            "gift_vouchers": len(self.gift_vouchers),
            "ticket_bookings": self.ticket_bookings.count(),
        }

    def item_count(self):
        if self.is_stripe_test:
            return 1
        return sum(self._item_counts().values())

    def item_types(self):
        if self.is_stripe_test:
            return "stripe_test"
        return [key for key, count in self._item_counts().items() if count > 0]

    def items_metadata(self):
        # This is used for the payment intent metadata, which is limited to 40 chars keys and string values
        all_items = self.items_dict()
        metadata = {}
        if self.total_voucher_code:  # pragma: no cover
            # We don't currently use total vouchers, this is kept in case we add them in future
            metadata = {"Voucher code used on total invoice": self.total_voucher_code}
        items_summary = {}
        for key, item in all_items.items():
            summary = {
                f"{key}_item": item["name"][:40],
                f"{key}_cost_in_p": str(item['cost_in_p']),
            }
            if item.get('voucher'):
                summary[f"{key}_voucher"] = item['voucher']
            items_summary.update(summary)
        return {**metadata, **items_summary}

    def save(self, *args, **kwargs):
        if self.paid and not self.date_paid:
            self.date_paid = timezone.now()
        super().save()


class Seller(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, null=True, blank=True)
    stripe_user_id = models.CharField(max_length=255, blank=True)
    stripe_access_token = models.CharField(max_length=255, blank=True)
    stripe_refresh_token = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.user.email


class StripePaymentIntent(models.Model):
    payment_intent_id = models.CharField(max_length=255)
    amount = models.PositiveIntegerField()
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payment_intents"    
    )
    seller = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField()
    client_secret = models.CharField(max_length=255)
    currency = models.CharField(max_length=3)

    @classmethod
    def update_or_create_payment_intent_instance(cls, payment_intent, invoice, seller=None):
        defaults = {
            "invoice": invoice,
            "amount": payment_intent.amount,
            "description": payment_intent.description,
            "status": payment_intent.status,
            "metadata": payment_intent.metadata,
            "client_secret": payment_intent.client_secret,
            "currency": payment_intent.currency
        }
        if seller is not None:
            defaults.update({"seller": seller})
        return cls.objects.update_or_create(payment_intent_id=payment_intent.id, defaults=defaults)

    def __str__(self):
        return f"{self.payment_intent_id} - invoice {self.invoice.invoice_id} - {self.invoice.username}"


# class StripeRefund(models.Model):
#     payment_intent = models.ForeignKey(
#         StripePaymentIntent, on_delete=models.SET_NULL, null=True, blank=True,
#         related_name="refunds"
#     )
#     refund_id = models.CharField(max_length=255)
#     amount = models.PositiveIntegerField()
#     status = models.CharField(max_length=255)
#     invoice = models.ForeignKey(
#         Invoice, on_delete=models.SET_NULL, null=True, blank=True,
#         related_name="refunds"
#     )
#     seller = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True)
#     metadata = models.JSONField()
#     currency = models.CharField(max_length=3)
#     reason = models.CharField(max_length=255)
#     booking_id = models.PositiveIntegerField()

#     @classmethod
#     def create_from_refund_obj(cls, refund, payment_intent_model_instance, booking_id):
#         return cls.objects.create(
#             refund_id=refund.id,
#             payment_intent=payment_intent_model_instance,
#             invoice=payment_intent_model_instance.invoice,
#             amount=refund.amount,
#             status=refund.status,
#             seller=payment_intent_model_instance.seller,
#             metadata=refund.metadata,
#             currency=refund.currency,
#             reason=refund.reason,
#             booking_id=booking_id,
#         )
