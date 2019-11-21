from django.conf import settings
from django.shortcuts import HttpResponseRedirect, render
from django.urls import reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.generic import FormView

from dateutil.relativedelta import relativedelta
from shortuuid import ShortUUID

from payments.forms import PayPalPaymentsShoppingBasketForm, PayPalPaymentsUpdateForm
from payments.helpers import create_gift_voucher_paypal_transaction
from ..context_helpers import get_paypal_dict
from ..forms import GiftVoucherForm
from ..models import BlockVoucher, EventVoucher, GiftVoucher


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
        return kwargs

    def form_valid(self, form):
        # TODO store user on the paypal payment model?
        # user email could be different to the one they put on the form
        voucher_type = form.cleaned_data["voucher_type"]
        email = form.cleaned_data["user_email"]
        name = form.cleaned_data["recipient_name"]
        message = form.cleaned_data["message"]
        code = ShortUUID().random(length=12)

        if voucher_type.block_type:
            # unlikely, but make sure we haven't made a code that's been used before
            while BlockVoucher.objects.filter(code=code).exists():
                code = ShortUUID().random(length=12)
            voucher = BlockVoucher.objects.create(
                activated=False, is_gift_voucher=True, expiry_date=timezone.now() + relativedelta(months=6),
                code=code, max_vouchers=1, max_per_user=1, discount=100, name=name, message=message
            )
            voucher.block_types.add(voucher_type.block_type)
        else:
            while EventVoucher.objects.filter(code=code).exists():
                code = ShortUUID().random(length=12)
            voucher = EventVoucher.objects.create(
                activated=False, is_gift_voucher=True, expiry_date=timezone.now() + relativedelta(months=6),
                code=code, max_vouchers=1, max_per_user=1, discount=100, name=name, message=message
            )
            voucher.event_types.add(voucher_type.event_type)

        invoice_id = create_gift_voucher_paypal_transaction(voucher_type=voucher_type, voucher_code=code).invoice_id
        paypal_form = PayPalPaymentsUpdateForm(
            initial=get_paypal_dict(
                'http://{}'.format(self.request.META.get('HTTP_HOST')),
                voucher_type.cost,
                f"gift voucher - {voucher_type}",
                invoice_id,
                f'gift_voucher {voucher.id} {voucher.code} {email}',
                paypal_email=settings.DEFAULT_PAYPAL_EMAIL,
            )
        )
        return TemplateResponse(
            self.request, template='booking/gift_voucher_purchase.html', context={"paypal_form": paypal_form, "voucher_type": voucher_type}
        )


def gift_voucher_details(request, voucher_code, print=False):

    try:
        voucher = BlockVoucher.objects.get(code=voucher_code)
        voucher_type = 'block'
        valid_for = voucher.block_types.all()
    except BlockVoucher.DoesNotExist:
        voucher = EventVoucher.objects.get(code=voucher_code)
        voucher_type = 'event'
        valid_for = voucher.event_types.all()

    context={"voucher": voucher, "valid_for": valid_for, "voucher_type": voucher_type}

    return TemplateResponse(
        request, template='booking/gift_voucher_detail.html', context=context

    )