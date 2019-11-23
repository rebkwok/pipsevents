from django.conf import settings
from django.shortcuts import HttpResponseRedirect, render
from django.urls import reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.generic import FormView

from dateutil.relativedelta import relativedelta
from shortuuid import ShortUUID

from activitylog.models import ActivityLog
from payments.forms import PayPalPaymentsUpdateForm
from payments.helpers import create_gift_voucher_paypal_transaction
from payments.models import PaypalGiftVoucherTransaction
from ..context_helpers import get_paypal_dict
from ..forms import GiftVoucherForm
from ..models import BlockVoucher, EventVoucher, GiftVoucherType


class GiftVoucherPurchaseView(FormView):
    # no need to be logged in

    # GET need a form with:
    # - email - autofill if user logged in
    # - select drop down - voucher type

    # POST ->
    # (add purchaser email field to voucher model - or add a "inactive" flag to
    # the voucher code which only gets activated on payment processing?  That would let
    # us store the code against the payment but only activate it when payment processed?)
    # generate voucher code, assign purchaser email
    # render paypal form for selected voucher - plus timeout

    # payments - need a paypal payment model for vouchers
    # user not required; include an email field for non-registered users
    # on processing paypal - assign user based on email, if found

    # on processing paypal - generate voucher PDF/url and send email

    template_name = 'booking/gift_voucher_purchase.html'
    form_class = GiftVoucherForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            kwargs['user'] = self.request.user
        if "voucher_code" in self.kwargs:
            try:
                voucher = BlockVoucher.objects.get(code=self.kwargs["voucher_code"])
            except BlockVoucher.DoesNotExist:
                voucher = EventVoucher.objects.get(code=self.kwargs["voucher_code"])
            kwargs["instance"] = voucher
        return kwargs


    def form_valid(self, form):
        voucher_type = form.cleaned_data["voucher_type"]
        email = form.cleaned_data["user_email"]
        name = form.cleaned_data["recipient_name"]
        message = form.cleaned_data["message"]

        voucher_type_change = False
        existing_voucher_code = None
        existing_voucher_activated = False

        if hasattr(form, "instance"):
            # We are updating an existing voucher
            voucher = form.instance
            existing_voucher_code = voucher.code
            existing_voucher_activated = voucher.activated

            if not existing_voucher_activated:
                # We only allow the voucher type and email to change for not activated (i.e. not paid) vouchers. These form
                # fields should be disabled anyway, so this check is just in case
                # Update the existing paypal transaction object
                # codes are random UUIDs, we'll probably only have one transaction per code/voucher type
                voucher.purchaser_email = email
                if isinstance(voucher, BlockVoucher):
                    old_voucher_type = GiftVoucherType.objects.get(block_type=voucher.block_types.first())
                else:
                    old_voucher_type = GiftVoucherType.objects.get(event_type=voucher.event_types.first())
                if old_voucher_type != voucher_type:
                    existing_ppt = PaypalGiftVoucherTransaction.objects.filter(voucher_code=voucher.code, voucher_type=old_voucher_type)
                    if existing_ppt:
                        existing_ppt = existing_ppt[0]
                        existing_ppt.voucher_type = voucher_type
                        existing_ppt.save()

                # Update the voucher type
                if isinstance(voucher, BlockVoucher) and voucher_type.block_type:
                    # still a BlockVoucher, update the blocktypes
                    if voucher_type.block_type not in voucher.block_types.all():
                        # changed block type, remove the old one and add the new one
                        for block_type in voucher.block_types.all():
                            voucher.block_types.remove(block_type)
                        voucher.block_types.add(voucher_type.block_type)
                elif isinstance(voucher, EventVoucher) and voucher_type.event_type:
                    # still an EventVoucher, update the eventtypes
                    if voucher_type.event_type not in voucher.event_types.all():
                        # changed block type, remove the old one and add the new one
                        for event_type in voucher.event_types.all():
                            voucher.event_types.remove(event_type)
                        voucher.event_types.add(voucher_type.event_type)
                else:
                    voucher_type_change = True

            # Update the voucher with new form info that we allow to be changed on activated or inactivated vouchers
            voucher.name = name
            voucher.message = message

            # If the voucher type changed (block <--> event), we need to delete the voucher and make a new one
            # If it didn't change, save the new form fields
            if voucher and not voucher_type_change:
                voucher.save()
                ActivityLog.objects.create(log=f"Gift Voucher {voucher.code} updated; purchaser email {voucher.purchaser_email}")
            else:
                voucher.delete()

        if not hasattr(form, "instance") or voucher_type_change:
            # Making a new voucher from scratch, or with a new voucher type
            if voucher_type_change:
                code = existing_voucher_code
            else:
                code = ShortUUID().random(length=12)

            if voucher_type.block_type:
                # unlikely, but make sure we haven't made a code that's been used before
                while BlockVoucher.objects.filter(code=code).exists():
                    code = ShortUUID().random(length=12)
                voucher = BlockVoucher.objects.create(
                    activated=existing_voucher_activated,
                    is_gift_voucher=True, expiry_date=timezone.now() + relativedelta(months=6),
                    code=code, max_vouchers=1, max_per_user=1, discount=100, name=name, message=message,
                    purchaser_email=email
                )
                voucher.block_types.add(voucher_type.block_type)
            else:
                while EventVoucher.objects.filter(code=code).exists():
                    code = ShortUUID().random(length=12)
                voucher = EventVoucher.objects.create(
                    activated=existing_voucher_activated,
                    is_gift_voucher=True, expiry_date=timezone.now() + relativedelta(months=6),
                    code=code, max_vouchers=1, max_per_user=1, discount=100, name=name, message=message,
                    purchaser_email=email
                )
                voucher.event_types.add(voucher_type.event_type)
            if voucher_type_change:
                ActivityLog.objects.create(log=f"Gift Voucher {voucher.code} updated; purchaser email {voucher.purchaser_email}")
            else:
                ActivityLog.objects.create(log=f"Gift Voucher {voucher.code} created; purchaser email {voucher.purchaser_email}")

        if not voucher.activated:
            # unpaid voucher, go to paypal page again
            invoice_id = create_gift_voucher_paypal_transaction(voucher_type=voucher_type, voucher_code=voucher.code).invoice_id
            paypal_form = PayPalPaymentsUpdateForm(
                initial=get_paypal_dict(
                    'http://{}'.format(self.request.META.get('HTTP_HOST')),
                    voucher_type.cost,
                    f"gift voucher - {voucher_type}",
                    invoice_id,
                    f'gift_voucher {voucher.id} {voucher.code}',
                    paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
                )
            )
            return TemplateResponse(
                self.request, template='booking/gift_voucher_purchase.html', context={"paypal_form": paypal_form, "voucher_type": voucher_type, "voucher": voucher}
            )
        else:
            return HttpResponseRedirect(reverse("booking:gift_voucher_details", args=(voucher.code,)))


def get_voucher_details(voucher_code):
    try:
        voucher = BlockVoucher.objects.get(code=voucher_code)
        voucher_type = 'block'
        valid_for = voucher.block_types.all()
    except BlockVoucher.DoesNotExist:
        voucher = EventVoucher.objects.get(code=voucher_code)
        voucher_type = 'event'
        valid_for = voucher.event_types.all()
    return voucher, voucher_type, valid_for


def gift_voucher_details(request, voucher_code):
    voucher, voucher_type, valid_for = get_voucher_details(voucher_code)
    context={"voucher": voucher, "valid_for": valid_for, "voucher_type": voucher_type}
    return TemplateResponse(
        request, template='booking/gift_voucher_detail.html', context=context

        )


def gift_voucher_delete(request, voucher_code):
    voucher, voucher_type, valid_for = get_voucher_details(voucher_code)
    if voucher.activated:
        return HttpResponseRedirect(reverse('booking:permission_denied'))
    voucher.delete()
    ActivityLog.objects.create(log=f"Gift Voucher with code {voucher_code} deleted")
    return HttpResponseRedirect(reverse('booking:buy_gift_voucher'))
