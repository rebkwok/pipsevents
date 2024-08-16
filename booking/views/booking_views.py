# -*- coding: utf-8 -*-
import logging
from typing import Any
import pytz

from decimal import Decimal

from datetime import timedelta

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.urls import reverse
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.generic import (
    ListView, UpdateView, DeleteView
)
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail
from django.template.loader import get_template, render_to_string
from django.template.response import TemplateResponse

from braces.views import LoginRequiredMixin

from payments.forms import PayPalPaymentsUpdateForm
from payments.models import PaypalBookingTransaction

from accounts.models import has_expired_disclaimer, has_active_disclaimer

from booking.models import (
    Block, BlockType, Booking, Event, UsedEventVoucher, EventVoucher,
    WaitingListUser
)
from booking.forms import VoucherForm
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email
from booking.views.shopping_basket_views import shopping_basket_bookings_total_context
from booking.views.views_utils import DisclaimerRequiredMixin, \
    DataPolicyAgreementRequiredMixin, \
    get_block_status, validate_voucher_code

from booking.templatetags.bookingtags import format_paid_status, get_shopping_basket_icon

from common.views import _set_pagination_context

from payments.helpers import create_booking_paypal_transaction
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


def due_date_time(booking):
    if booking.event.advance_payment_required:
        uk_tz = pytz.timezone('Europe/London')
        if booking.event.payment_due_date:
            due_date_time = booking.event.payment_due_date
        elif booking.event.payment_time_allowed:
            last_booked = booking.date_rebooked if booking.date_rebooked else booking.date_booked
            due_date_time = last_booked + timedelta(hours=booking.event.payment_time_allowed)
        elif booking.event.cancellation_period:
            due_date_time = booking.event.date - timedelta(
                hours=booking.event.cancellation_period
            )
        return due_date_time.astimezone(uk_tz)


class BookingListView(DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'
    paginate_by = 20

    def get_queryset(self):
        return Booking.objects.exclude(event__event_type__event_type="OT").filter(
            Q(event__date__gte=timezone.now()) & Q(user=self.request.user)
        ).order_by('event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingListView, self).get_context_data(**kwargs)

        user_blocks = self.request.user.blocks.filter(expiry_date__gte=timezone.now())
        active_block_event_types = [
            block.block_type.event_type for block in user_blocks if block.active_block()
        ]

        bookingformlist = []
        bookings = context['bookings']

        for booking in bookings:
            bookingform = get_booking_context(booking)
            bookingform['has_available_block'] = booking.event.event_type in active_block_event_types
            try:
                WaitingListUser.objects.get(user=self.request.user, event=booking.event)
                bookingform['on_waiting_list'] = True
            except WaitingListUser.DoesNotExist:
                bookingform['on_waiting_list'] = False
            bookingformlist.append(bookingform)

        context['bookingformlist'] = bookingformlist
        _set_pagination_context(context)

        return context
    

def get_booking_context(booking):
    return {
        'booking_status': 'CANCELLED' if
        (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
        'ev_type_code': booking.event.event_type.event_type,
        'booking': booking,
        'due_date_time': due_date_time(booking),
    }


class BookingHistoryListView(DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'
    paginate_by = 20

    def get_queryset(self):
        return Booking.objects.exclude(event__event_type__event_type="OT").filter(
            event__date__lte=timezone.now(), user=self.request.user
        ).order_by('-event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingHistoryListView, self).get_context_data(**kwargs)
        # Add in the history flag
        context['history'] = True

        bookingformlist = []
        bookings = context['bookings']

        for booking in bookings:
            bookingform = {
                'booking_status': 'CANCELLED' if
                (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
                'booking': booking,
                'ev_type_code': booking.event.event_type.event_type
            }
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


class PurchasedTutorialsListView(DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'purchased_tutorials'
    template_name = 'booking/purchased_tutorials.html'
    paginate_by = 20

    def get_queryset(self):
        return self.request.user.bookings.filter(
            event__event_type__event_type="OT", paid=True, status="OPEN", no_show=False
        ).order_by('date_booked')

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        _set_pagination_context(context)
        return context


class BookingUpdateView(
    DataPolicyAgreementRequiredMixin, DisclaimerRequiredMixin, LoginRequiredMixin,
    UpdateView
):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_message = 'Booking updated for {}!'
    fields = ['paid']

    def dispatch(self, request, *args, **kwargs):
        # redirect if event cancelled
        booking = get_object_or_404(Booking, id=self.kwargs['pk'])
        if booking.event.cancelled:
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        # redirect if booking cancelled
        if booking.status == 'CANCELLED':
            return HttpResponseRedirect(reverse('booking:update_booking_cancelled',
                                        args=[booking.id]))

        # redirect if booking already paid so we don't create duplicate
        # paypal booking transactions and allow duplicate payment
        if booking.paid:
            return HttpResponseRedirect(reverse('booking:already_paid',
                                        args=[booking.id]))

        return super(BookingUpdateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingUpdateView, self).get_context_data(**kwargs)

        invoice_id = create_booking_paypal_transaction(
            self.request.user, self.object
        ).invoice_id

        paypal_cost = self.object.event.cost
        voucher = kwargs.get('voucher', None)
        voucher_error = kwargs.get('voucher_error', None)
        code = kwargs.get('code', None)
        context['voucher_form'] = VoucherForm(initial={'code': code})

        if voucher:
            valid = not bool(voucher_error)
            context['valid_voucher'] = valid
            if valid:
                paypal_cost = Decimal(
                    float(paypal_cost) * ((100 - voucher.discount) / 100)
                ).quantize(Decimal('.05'))
                messages.info(self.request, 'Voucher has been applied')
                times_used = UsedEventVoucher.objects.filter(
                    voucher=voucher, user=self.request.user
                ).count()
                context['times_voucher_used'] = times_used

        custom = context_helpers.get_paypal_custom(
            item_type='booking',
            item_ids=str(self.object.id),
            voucher_code=voucher.code if context.get('valid_voucher', False) else None,
            voucher_applied_to=[self.object.id] if context.get('valid_voucher') else [],
            user_email=self.request.user.email
        )
        paypal_form = PayPalPaymentsUpdateForm(
            initial=context_helpers.get_paypal_dict(
                self.request,
                paypal_cost,
                '{}'.format(self.object.event),
                invoice_id,
                custom,
                paypal_email=self.object.event.paypal_email,
            )
        )
        context["paypalform"] = paypal_form
        context["paypal_cost"] = paypal_cost

        # set cart items so we can set paypal_pending
        self.request.session['cart_items'] = custom

        return context_helpers.get_booking_update_context(
            self.object.event, self.request, context
        )

    def form_valid(self, form):
        # posting the form means we're not using paypal,
        # so remove the cart items from the session
        if self.request.session.get('cart_items'):
            del self.request.session['cart_items']

        if "apply_voucher" in form.data:
            code = form.data['code'].strip()
            try:
                voucher = EventVoucher.objects.get(code=code)
            except EventVoucher.DoesNotExist:
                voucher = None
                voucher_error = 'Invalid code' if code else 'No code provided'

            if voucher:
                voucher_error = validate_voucher_code(
                    voucher, self.request.user, self.object.event
                )
            context = self.get_context_data(
                voucher=voucher, voucher_error=voucher_error, code=code
            )
            return TemplateResponse(self.request, self.template_name, context)

        booking = form.save(commit=False)
        if "claim_free"in form.data:
            _email_free_class_request(self.request, booking, 'update')

        elif 'block_book' in form.data:
            active_block = booking.get_next_active_block()
            if active_block:
                booking.block = active_block
                booking.paid = True
                booking.payment_confirmed = True
            else:
                messages.error(self.request, 'Error: No available block')

        booking.save()
        blocks_used, total_blocks = get_block_status(booking, self.request)
        if booking.block:
            # send email to user if they used block to book (paypal payment
            # sends separate emails
            host = 'http://{}'.format(self.request.get_host())
            if booking.event.event_type.event_type == 'EV':
                ev_type = 'event'
            elif booking.event.event_type.event_type == 'CL':
                ev_type = 'class'
            else:
                ev_type = 'room hire'

            ctx = {
                'host': host,
                'booking': booking,
                'event': booking.event,
                'date': booking.event.date.strftime('%A %d %B'),
                'time': booking.event.date.strftime('%I:%M %p'),
                'blocks_used':  blocks_used,
                'total_blocks': total_blocks,
                'ev_type': ev_type
            }
            send_mail('{} Block used for booking for {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event
            ),
                get_template('booking/email/booking_updated.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
                html_message=get_template(
                    'booking/email/booking_updated.html').render(ctx),
                fail_silently=False)

        messages.success(
            self.request, self.success_message.format(booking.event)
        )
        if booking.block and not booking.block.active_block():
            if not booking.has_available_block:
                messages.info(
                    self.request,
                    mark_safe(
                        'You have just used the last space in your block. '
                       'Go to <a href="/blocks">My Blocks</a> to buy a new one.'
                    )
                )
        if 'shopping_basket' in form.data:
            url = reverse('booking:shopping_basket')
            params = {}
            if 'booking_code' in self.request.POST:
                params['booking_code'] = self.request.POST['booking_code']
            if 'block_code' in self.request.POST:
                params['block_code'] = self.request.POST['block_code']

            if params:
                url += '?{}'.format(urlencode(params))
            return HttpResponseRedirect(url)

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:bookings')


def _email_free_class_request(request, booking, booking_status):
    # if user is requesting a free class, send email to studio and
    # make booking unpaid (admin will update)
    ActivityLog.objects.create(
        log='Free class requested ({}) by user {}'.format(
            booking.event, request.user.username)
    )
    booking.free_class_requested = True
    booking.paid = False
    booking.payment_confirmed = False
    booking.block = None

    # send email and set messages
    host = 'http://{}'.format(request.get_host())
    # send email to studio
    ctx = {
            'host': host,
            'event': booking.event,
            'user': request.user,
            'booking_status': booking_status,
    }
    send_mail('{} Request to claim free class from {} {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
            request.user.first_name,
            request.user.last_name
        ),
        get_template(
            'studioadmin/email/free_class_request_to_studio.txt'
        ).render(ctx),
        settings.DEFAULT_FROM_EMAIL,
        [settings.DEFAULT_STUDIO_EMAIL],
        html_message=get_template(
            'studioadmin/email/free_class_request_to_studio.html'
            ).render(ctx),
        fail_silently=False)

    messages.success(
        request,
        "Your request to claim {} as a free class has been "
        "sent to the studio.  Your booking has been "
        "provisionally made and your place will be secured once "
        "your request has been approved.".format(booking.event)
    )


class BookingDeleteView(
    DataPolicyAgreementRequiredMixin, DisclaimerRequiredMixin, LoginRequiredMixin,
    DeleteView
):
    model = Booking
    template_name = 'booking/delete_booking.html'
    success_message = 'Booking cancelled for {}.'

    def dispatch(self, request, *args, **kwargs):
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        if booking.status == 'CANCELLED':
            # redirect if already cancelled
            return HttpResponseRedirect(
                reverse('booking:already_cancelled',
                        args=[booking.id])
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        event = Event.objects.get(id=booking.event.id)
        # Add in the event
        context['event'] = event
        # Add in block info
        context['booked_with_block'] = booking.block is not None
        context['block_booked_within_allowed_time'] = self._block_or_membership_booked_within_allowed_time(booking)
        context['booking'] = booking
        return context

    def _block_or_membership_booked_within_allowed_time(self, booking):
        allowed_datetime = timezone.now() - timedelta(minutes=15)
        if booking.block or booking.membership:
            return (booking.date_rebooked and booking.date_rebooked > allowed_datetime) \
                   or (booking.date_booked > allowed_datetime)
        return False

    def form_valid(self, _form):
        booking = self.get_object()
        event = booking.event
        delete_from_shopping_basket = self.request.GET.get('ref') == 'basket'

        # Booking can be fully cancelled if the event allows cancellation AND
        # the cancellation period is not past
        # If not, we let people cancel but leave the booking status OPEN and
        # set to no-show
        can_cancel_and_refund = booking.can_cancel

        # if the booking was made with a block, allow 15 mins to cancel in case user
        # clicked the wrong button by mistake and autobooked with a block
        # Check here so we can adjust the email message
        block_or_membership_booked_within_allowed_time = self._block_or_membership_booked_within_allowed_time(booking)

        host = 'http://{}'.format(self.request.get_host())

        # email if this isn't an unpaid/non-rebooked booking
        # send email to user

        ctx = {
                  'host': host,
                  'booking': booking,
                  'block_or_membership_booked_within_allowed_time': block_or_membership_booked_within_allowed_time,
                  'event': event,
                  'date': event.date.strftime('%A %d %B'),
                  'time': event.date.strftime('%I:%M %p'),
              }
        try:
            send_mail('{} Booking for {} cancelled'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, event),
                get_template('booking/email/booking_cancelled.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
                html_message=get_template(
                    'booking/email/booking_cancelled.html').render(ctx),
                fail_silently=False)
        except Exception as e:
            # send mail to tech support with Exception
            send_support_email(e, __name__, "DeleteBookingView - cancelled email")
            messages.error(self.request, "An error occured, please contact "
                "the studio for information")

        if can_cancel_and_refund:
            transfer_block_created = False
            if booking.paid and (not booking.block or booking.block.expired) and not booking.membership:
                # booking was paid directly, either in cash or by paypal
                # OR booking was free class but not made with free block
                # OR booking was made with block (normal/free/transfer) but
                # block has now expired and we can't credit by reassigning
                # space to block.
                # NOTE: this does mean that potentially someone could defer
                # a class indefinitely by cancelling and rebooking, but
                # let's assume that would be a rare occurrence

                # If event is CL or RH, get or create transfer block type,
                # create transfer block for user and set transferred_
                # booking_id to the cancelled one
                if event.event_type.event_type != 'EV':
                    block_type = BlockType.get_transfer_block_type(event.event_type)
                    Block.objects.create(
                        block_type=block_type, user=booking.user,
                        transferred_booking_id=booking.id
                    )
                    transfer_block_created = True
                    booking.deposit_paid = False
                    booking.paid = False
                    booking.payment_confirmed = False

                # send email to studio only for 'EV' which are not transferable
                else:
                    send_mail(
                        '{} {} {} has just cancelled a booking for {}'.format(
                            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                            'ACTION REQUIRED!' if not booking.block else '',
                            booking.user.username,
                            booking.event
                            ),
                          get_template(
                              'booking/email/to_studio_booking_cancelled.txt'
                          ).render(
                              {
                                  'host': host,
                                  'booking': booking,
                                  'event': booking.event,
                                  'date': booking.event.date.strftime('%A %d %B'),
                                  'time': booking.event.date.strftime('%I:%M %p'),
                              }
                          ),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        fail_silently=False)

            # if booking was bought with a block/membership, remove from block and set
            # paid and payment_confirmed to False. If paid directly, paid is only
            # changed to False for bookings that have created transfer blocks; for
            # EV event types, leave paid as True as refunds need to be dealt with
            # manually but change payment_confirmed to False
            # reassigning free class blocks is done in model save
            if booking.block:
                booking.block = None
                booking.paid = False
            
            if booking.membership:
                booking.membership = None
                booking.paid = False

            if booking.free_class:
                booking.free_class = False
                booking.paid = False
            booking.status = 'CANCELLED'
            booking.payment_confirmed = False
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.event)
            )
            ActivityLog.objects.create(
                log='Booking id {} for event {} was cancelled by user '
                    '{}'.format(
                        booking.id, event,
                        self.request.user.username
                    )
            )

            if transfer_block_created:
                ActivityLog.objects.create(
                    log='Transfer block created for user {} (for {}; transferred '
                        'booking id {} '.format(
                            booking.user.username, event.event_type.subtype,
                            booking.id
                        )
                )
                messages.info(
                    self.request,
                    mark_safe(
                        'A transfer block has been created for you as '
                        'credit for your cancelled booking and is valid for '
                        '1 month (<a href="/blocks">View your blocks</a>)'
                    )
                )

        else:
            # if the booking was made with a block, allow 15 mins to cancel in case user
            # clicked the wrong button by mistake and autobooked with a block
            # if the booking wasn't paid, just cancel it

            can_cancel = block_or_membership_booked_within_allowed_time or not booking.paid
            if can_cancel:
                booking.membership = None
                booking.block = None
                booking.paid = False
                booking.free_class = False
                booking.status = 'CANCELLED'
                booking.payment_confirmed = False
                booking.save()

                messages.success(
                    self.request,
                    self.success_message.format(event)
                )
                ActivityLog.objects.create(
                    log='Booking id {} for event {}, user {}, was cancelled by user '
                        '{}'.format(
                            booking.id, event, booking.user.username,
                            self.request.user.username
                        )
                )
            else:  # set to no-show
                booking.no_show = True
                booking.save()

                if not event.allow_booking_cancellation:
                    messages.success(
                        self.request,
                        self.success_message.format(event) +
                        ' Please note that this booking is not eligible for refunds '
                        'or transfer credit.'
                    )
                    ActivityLog.objects.create(
                        log='Booking id {} for NON-CANCELLABLE event {}, user {}, '
                            'was cancelled and set to no-show'.format(
                                booking.id, event, booking.user.username,
                                self.request.user.username
                            )
                    )
                else:
                    messages.success(
                        self.request,
                        self.success_message.format(event) +
                        ' Please note that this booking is not eligible for '
                        'refunds or transfer credit as the allowed '
                        'cancellation period has passed.'
                    )
                    ActivityLog.objects.create(
                        log='Booking id {} for event {}, user {}, was cancelled '
                            'after the cancellation period and set to '
                            'no-show'.format(
                                booking.id, event, booking.user.username,
                                self.request.user.username
                            )
                    )

        # if applicable, email users on waiting list
        waiting_list_users = WaitingListUser.objects.filter(
            event=event
        )
        if waiting_list_users:
            try:
                send_waiting_list_email(
                    event,
                    [wluser.user for wluser in waiting_list_users],
                    host='http://{}'.format(self.request.get_host())
                )
                ActivityLog.objects.create(
                    log='Waiting list email sent to user(s) {} for '
                    'event {}'.format(
                        ', '.join(
                            [wluser.user.username for \
                            wluser in waiting_list_users]
                        ),
                        event
                    )
                )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(e, __name__, "DeleteBookingView - waiting list email")
                messages.error(self.request, "An error occured, please contact "
                    "the studio for information")

        if delete_from_shopping_basket:
            # get rid of messages
            list(messages.get_messages(self.request))
            if settings.PAYMENT_METHOD == "stripe":
                template = "booking/includes/shopping_basket_bookings_checkout.html"
            else:
                template = "booking/includes/shopping_basket_bookings_total.html"
            context= {
                "booking": booking,
                'shopping_basket_bookings_total_html': render_to_string(
                    template,
                    shopping_basket_bookings_total_context(self.request)
                )
            }
    
            return render_row(
                self.request, 
                "booking/includes/shopping_basket_booking_row_htmx.html", 
                None,
                context
            )

        next_page = self.request.GET.get('next') or self.request.POST.get('next')
        params = {}
        if self.request.GET.get('booking_code'):
            params['booking_code'] = self.request.GET['booking_code']
        if self.request.GET.get('block_code'):
            params['block_code'] = self.request.GET['block_code']
        if self.request.GET.get('filter'):
            params['name'] = self.request.GET['filter']
        if self.request.GET.get('tab'):
            params['tab'] = self.request.GET['tab']
        if self.request.GET.get('page'):
            params['page'] = self.request.GET['page']

        url = self.get_success_url(next_page)
        if params:
            url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)

    def get_success_url(self, next_page=None):
        if next_page:
            return reverse('booking:{}'.format(next_page))
        return reverse('booking:bookings')


def duplicate_booking(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    _, _, ev_type_str = context_helpers.event_strings(event)
    context = {'event': event, 'ev_type_str': ev_type_str}

    return render(request, 'booking/duplicate_booking.html', context)


def update_booking_cancelled(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    _, _, ev_type_str = context_helpers.event_strings(booking.event)
    context = {'booking': booking, 'ev_type_str': ev_type_str}
    if booking.event.spaces_left == 0:
        context['full'] = True
    return render(request, 'booking/update_booking_cancelled.html', context)


def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    _, _, ev_type_str = context_helpers.event_strings(event)
    context = {'event': event, 'ev_type_str': ev_type_str}
    return render(request, 'booking/fully_booked.html', context)


def has_active_block(request):
    return render(request, 'booking/has_active_block.html')


def cancellation_period_past(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/cancellation_period_past.html', context)


def already_cancelled(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    context = {'booking': booking}
    return render(request, 'booking/already_cancelled.html', context)


def already_paid(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    context = {'booking': booking}
    return render(request, 'booking/already_paid.html', context)


def disclaimer_required(request):

    return render(
        request,
        'booking/disclaimer_required.html',
        {'has_expired_disclaimer': has_expired_disclaimer(request.user)}
    )


@login_required
@require_http_methods(['POST'])
def ajax_create_booking(request, event_id):
    if not has_active_disclaimer(request.user):
        return HttpResponseRedirect(reverse('booking:disclaimer_required'))

    if request.user.currently_banned():
        unlocked = request.user.ban.end_date.strftime("%d %b %Y, %H:%M")
        return HttpResponseBadRequest(f'Your account is currently blocked until {unlocked}')    

    event = Event.objects.get(id=event_id)
    ref = request.GET.get('ref', "events")

    ref_to_template = {
        "online_tutorial": "booking/includes/event_htmx.html",
        "event": "booking/includes/event_htmx.html",
        "bookings": "booking/includes/bookings_row_htmx.html",
        "events": "booking/includes/events_row_htmx.html",
        "online_tutorials": "booking/includes/events_row_htmx.html",
        
    }
    template = ref_to_template[ref]

    previously_cancelled = False
    previously_no_show = False

    context = {
        "event": event,
        "location_index": int(request.GET.get('location_index', 0)),
        "location_page": request.GET.get('location_page', 1),
        "ref": ref,
    }

    # make sure this isn't an open booking already
    event_bookings = request.user.bookings.filter(event=event)
    if event_bookings.exists():
        booking = event_bookings.first()
        if booking.status == "OPEN" and not booking.no_show:
            # Already booked; don't do anything else, just update button
            if ref == "bookings":
                context = get_booking_context(booking)
            else:
                context["booking"] = booking
            return render_row(request, template, booking, context)


    # if pole practice, make sure this user has permission
    if not event.has_permission_to_book(request.user):
        if event.members_only:
            logger.error("Attempt to book members-only %s by non-member", event.event_type)
            msg =  "Only members are allowed to book this class; please contact the studio for further information."
        else:
            logger.error("Attempt to book %s by student without '%s' permission", event.event_type, event.event_type.allowed_group)
            msg =  "Additional permission is required to book this class; please contact the studio for further information."
        return HttpResponseBadRequest(msg)

    # make sure the event isn't full or cancelled
    if not event.spaces_left or event.cancelled:
        message = "Sorry, this event {}".format('is now full' if not event.spaces_left else "has been cancelled")
        logger.error('Attempt to book %s class', 'cancelled' if event.cancelled else 'full')
        return HttpResponseBadRequest(message)

    booking, new = Booking.objects.get_or_create(user=request.user, event=event)
    context["booking"] = booking
    ev_type_code, ev_type_for_url, ev_type_str = context_helpers.event_strings(booking.event)
    context.update(
        {
            "ev_type_code": ev_type_code,
            "ev_type_for_url": ev_type_for_url,
            "ev_type_str": ev_type_str,
        }
    )
    if ev_type_code == "OT":
        context['tutorial'] = event

    if not new:
        if booking.status == 'CANCELLED':
            previously_cancelled = True
            previously_no_show = False
        elif booking.no_show:
            previously_no_show = True
            previously_cancelled = False

    booking.status = 'OPEN'
    booking.no_show = False

    previously_cancelled_and_direct_paid = False

    if previously_cancelled and booking.paid:
        previously_cancelled_and_direct_paid = True

    elif previously_no_show and booking.paid:
        # leave paid no_show booking with existing payment method
        pass
    
    def assign_membership(booking):
        active_membership = booking.get_next_active_user_membership()
        if active_membership:
            booking.membership = active_membership
            booking.paid = True
            booking.payment_confirmed = True
            return active_membership
    
    def assign_block(booking):
        active_block = booking.get_next_active_block()
        if active_block:
            booking.block = active_block
            booking.paid = True
            booking.payment_confirmed = True
            return active_block

    # assign to first availble membership or block, depending on booking preference for this user
    match request.user.userprofile.booking_preference:
        case "membership":
            active_membership = assign_membership(booking)
            if not active_membership:
                assign_block(booking)     
        case "block":
            active_block = assign_block(booking)
            if not active_block:
                assign_membership(booking)   
        case _: # pragma: no cover
            assert False

    if event.cost == 0:
        booking.paid = True
        booking.payment_confirmed = True

    booking.save()

    if ref == "bookings":
        context.update(get_booking_context(booking))
    else:
        context.update(
            context_helpers.get_event_context(context, event, request.user, booking=booking)
        )
        context["booking_open"] = context["booked"]


    ActivityLog.objects.create(
        log='Booking {} {} for "{}" by user {}'.format(
            booking.id,
            'created' if not
            (previously_cancelled or previously_no_show)
            else 'rebooked',
                booking.event, booking.user.username)
    )

    host = 'http://{}'.format(request.get_host())
    
    # send email to user ONLY IF PAID
    # If it's unpaid, they'll get the email with payment/update
    if ev_type_for_url != "online_tutorials" and booking.paid:
        ctx = {
            'host': host,
            'booking': booking,
            'event': booking.event,
            'date': booking.event.date.strftime('%A %d %B'),
            'time': booking.event.date.strftime('%H:%M'),
            'prev_cancelled_and_direct_paid':
            previously_cancelled_and_direct_paid,
            'claim_free': False,
            'ev_type': ev_type_str,
        }
        send_mail('{} Booking for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event
        ),
            get_template('booking/email/booking_received.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            html_message=get_template(
                'booking/email/booking_received.html'
                ).render(ctx),
            fail_silently=False)

    # send email to studio if flagged for the event or if previously
    # cancelled and direct paid OR for specific users being watched
    if (
        booking.event.email_studio_when_booked or
        previously_cancelled_and_direct_paid or
        booking.user.email in settings.WATCHLIST
    ):
        additional_subject = ""
        if previously_cancelled_and_direct_paid:
            additional_subject = "ACTION REQUIRED!"

        send_mail('{} {} {} {} has just booked for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, additional_subject,
            booking.user.first_name, booking.user.last_name,
            booking.event
        ),
                    get_template(
                    'booking/email/to_studio_booking.txt'
                    ).render(
                        {
                            'host': host,
                            'booking': booking,
                            'event': booking.event,
                            'date': booking.event.date.strftime('%A %d %B'),
                            'time': booking.event.date.strftime('%H:%M'),
                            'prev_cancelled_and_direct_paid':
                            previously_cancelled_and_direct_paid,
                        }
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_STUDIO_EMAIL],
                    fail_silently=False)

    alert_message = {}

    # If this is a user's first booking, send info email
    # Check for previous paid bookings
    # Also store flag on session so we don't send repeated emails if user books multiple
    # classes
    if not request.session.get("new_user_email_sent", False) and not booking.user.bookings.filter(paid=True).exists():
        request.session["new_user_email_sent"] = True
        send_mail(
            f'{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Important studio information - please read!',
            get_template('booking/email/new_user_booking.txt').render(),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            html_message=get_template('booking/email/new_user_booking.html').render(),
            fail_silently=False
        )

    if previously_cancelled_and_direct_paid:
        alert_message['message_type'] = 'warning'
        alert_message['message'] = 'You previously paid for this booking; your booking ' \
                    'will remain as pending until the organiser has ' \
                    'reviewed your payment status.'
    elif previously_no_show:
        alert_message['message_type'] = 'success'
        if booking.block:
            alert_message['message'] = "You previously paid for this booking with a " \
                        "block and your booking has been reopened."
        elif booking.paid:
            alert_message['message'] = "You previously paid for this booking and your " \
                        "booking has been reopened."

    elif booking.block:

        alert_message['message_type'] = 'success'

        transfer_block = booking.block.block_type.identifier\
                .startswith('transferred') \
                if booking.block.block_type.identifier else False
        msg = "Booked with block. " if not transfer_block else "Booked with credit block."

        if not booking.block.active_block() and not transfer_block:
            msg += 'You have just used the last space in your block.'
            alert_message['message_type'] = 'warning'

        alert_message['message'] = msg
    
    elif booking.membership:
        alert_message['message_type'] = 'success'
        alert_message['message'] =  "Booked with membership."

    elif event.cost == 0:
        alert_message['message_type'] = 'success'
        alert_message['message'] = "Booked." if ev_type_for_url != "online_tutorials" else "Purchased."

    elif not booking.paid:
        alert_message['message_type'] = 'error'
        if booking.event.event_type.event_type == "OT":
            message = "Added to basket; online tutorial not available until payment has been made."
        else:
            message = "Added to basket; booking not confirmed until payment has been made."
        alert_message['message'] = message
    try:
        booking.user.waitinglists.get(event=event).delete()
        ActivityLog.objects.create(
            log='User {} removed from waiting list '
            'for {}'.format(
                booking.user.username, booking.event
            )
        )
    except WaitingListUser.DoesNotExist:
        pass

    context["alert_message"] = alert_message
    return render_row(request, template, booking, context)


def render_row(request, template, booking, context):
    if booking:
        context['booking_count_html'] = render_to_string("booking/includes/booking_count.html", {'event': booking.event, "request": request})
    context['shopping_basket_html'] = render_to_string("booking/includes/shopping_basket_icon.html", get_shopping_basket_icon(request.user, True))
    return render(request, template, context)


@login_required
def update_shopping_basket_count(request):
    context = get_shopping_basket_icon(request.user, True)
    return render(
        request,
        "booking/includes/shopping_basket_icon.html",
        context
    )


@login_required
def toggle_waiting_list(request, event_id):
    user = request.user
    event = Event.objects.get(id=event_id)

    # toggle current status
    try:
        waitinglistuser = WaitingListUser.objects.get(user=user, event=event)
        waitinglistuser.delete()
        on_waiting_list = False
    except WaitingListUser.DoesNotExist:
        WaitingListUser.objects.create(user=user, event=event)
        on_waiting_list = True

    return render(
        request,
        "booking/includes/waiting_list_button.html",
        {'event': event, 'on_waiting_list': on_waiting_list}
    )
