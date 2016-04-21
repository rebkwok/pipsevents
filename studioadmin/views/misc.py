# -*- coding: utf-8 -*-

import logging
import shortuuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect
from django.views.generic import UpdateView
from django.utils import timezone
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.context_helpers import get_paypal_dict
from booking.models import Booking
from studioadmin.forms import ConfirmPaymentForm
from studioadmin.views.helpers import StaffUserMixin, staff_required
from activitylog.models import ActivityLog
from payments.forms import PayPalPaymentsUpdateForm

logger = logging.getLogger(__name__)


class ConfirmPaymentView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_payment.html'
    success_message = 'Payment status changed to {}. An update email ' \
                      'has been sent to user {}.'
    form_class = ConfirmPaymentForm

    def get_initial(self):
        return {
            'payment_confirmed': self.object.payment_confirmed
        }

    def form_valid(self, form):
        if form.has_changed():
            booking = form.save(commit=False)

            if booking.payment_confirmed and 'payment_confirmed' \
                    in form.changed_data:
                # if user leaves paid unchecked but checks payment confirmed
                # as true, booking should be marked as paid
                booking.paid = True
                booking.date_payment_confirmed = timezone.now()

            if not booking.paid and 'paid' in form.changed_data:
                # if booking is changed to unpaid, reset payment_confirmed to
                # False too
                booking.payment_confirmed = False
            booking.save()

            if booking.paid and booking.payment_confirmed:
                payment_status = 'paid and confirmed'
            elif booking.paid:
                payment_status = "paid - payment not confirmed yet"
            else:
                payment_status = 'not paid'

            messages.success(
                self.request,
                self.success_message.format(payment_status, booking.user.username)
            )

            ctx = {
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST')),
                'payment_status': payment_status
            }
            try:
                send_mail(
                    '{} Payment status updated for {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                    get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [self.request.user.email],
                    html_message=get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    fail_silently=False)
            except Exception as e:
                logger.error(
                        'EXCEPTION "{}"" while sending email for booking '
                        'id {}'.format(e, booking.id)
                        )

            ActivityLog.objects.create(
                log='Payment status for booking id {} for event {}, '
                'user {} updated by admin user {}'.format(
                booking.id, booking.event, booking.user.username,
                self.request.user.username
                )
            )
        else:
            messages.info(
                self.request, "No changes made to the payment "
                              "status for {}'s booking for {}.".format(
                    self.object.user.username, self.object.event)
            )

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')


class ConfirmRefundView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_refunded.html'
    success_message = "Refund of payment for {}'s {}booking for {} has been " \
                      "confirmed.  An update email has been sent to {}."
    fields = ('id',)

    def form_valid(self, form):
        booking = form.save(commit=False)
        free = booking.free_class

        if 'confirmed' in self.request.POST:
            booking.deposit_paid = False
            booking.paid = False
            booking.payment_confirmed = False
            booking.date_payment_confirmed = None
            if free:
                booking.free_class = False
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.user.username,
                                            '(free) ' if free else '',
                                            booking.event,
                                            booking.user.username)
            )

            ctx = {
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST')),
                'free': free
            }

            send_mail(
                '{} Payment refund confirmed for {}{}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event,
                    '(free class)' if free else '',
                ),
                get_template('studioadmin/email/confirm_refund.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                html_message=get_template(
                    'studioadmin/email/confirm_refund.html').render(ctx),
                fail_silently=False)

            ActivityLog.objects.create(
                log='Payment refund for {}booking id {} for event {}, '
                    'user {} updated by admin user {}'.format(
                    '(free) ' if free else '',
                    booking.id, booking.event, booking.user.username,
                    self.request.user.username
                )
            )

        if 'cancelled' in self.request.POST:
            messages.info(
                self.request,
                "Cancelled; no changes to payment status for {}'s booking "
                "for {}".format(booking.user.username, booking.event)
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')


@login_required
@staff_required
def test_paypal_view(request):
    ctx = {'sidenav_selection': 'test_paypal'}
    if request.method == 'GET':
        email = request.GET.get('email', '')
        ctx.update({'email': email})
    elif request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            ctx.update(
                {'email_errors': 'Please enter an email address to test'}
            )
        else:
            ramdomnum = shortuuid.ShortUUID().random(length=6)
            invoice_id = '{}_{}'.format(email, ramdomnum)
            host = 'http://{}'.format(request.META.get('HTTP_HOST'))
            paypal_form = PayPalPaymentsUpdateForm(
                initial=get_paypal_dict(
                    host,
                    0.01,
                    'paypal_test',
                    invoice_id,
                    'paypal_test 0 {} {} {}'.format(
                        invoice_id, email, request.user.email
                    ),
                    paypal_email=email,
                )
            )
            ctx.update({'paypalform': paypal_form, 'email': email})

    return TemplateResponse(request, 'studioadmin/test_paypal_email.html', ctx)
