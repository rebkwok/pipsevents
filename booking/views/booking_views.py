# -*- coding: utf-8 -*-
import logging
import pytz

from decimal import Decimal

from datetime import timedelta

from operator import itemgetter

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView
)
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template.response import TemplateResponse
from braces.views import LoginRequiredMixin

from payments.forms import PayPalPaymentsListForm, PayPalPaymentsUpdateForm
from payments.models import PaypalBookingTransaction

from accounts.utils import has_expired_disclaimer

from booking.models import (
    Block, BlockType, Booking, Event, UsedEventVoucher, EventVoucher,
    WaitingListUser
)
from booking.forms import BookingCreateForm, VoucherForm
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email
from booking.views.views_utils import DisclaimerRequiredMixin

from payments.helpers import create_booking_paypal_transaction
from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class BookingListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(
            Q(event__date__gte=timezone.now()) & Q(user=self.request.user)
        ).order_by('event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingListView, self).get_context_data(**kwargs)

        user_blocks = self.request.user.blocks.all()
        active_block_event_types = [
            block.block_type.event_type for block in user_blocks
            if block.active_block()
        ]

        bookingformlist = []
        for booking in self.object_list:
            if booking.event.event_type not in active_block_event_types \
                    and booking.status == 'OPEN' and not booking.paid:
                # ONLY DO THIS IF PAYPAL BUTTON NEEDED
                invoice_id = create_booking_paypal_transaction(
                    self.request.user, booking).invoice_id
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                paypal_form = PayPalPaymentsListForm(
                    initial=context_helpers.get_paypal_dict(
                        host,
                        booking.event.cost,
                        booking.event,
                        invoice_id,
                        '{} {}'.format('booking', booking.id),
                        paypal_email=booking.event.paypal_email,
                    )
                )
            else:
                paypal_form = None

            try:
                WaitingListUser.objects.get(user=self.request.user, event=booking.event)
                on_waiting_list = True
            except WaitingListUser.DoesNotExist:
                on_waiting_list = False

            can_cancel = booking.event.allow_booking_cancellation and \
                         booking.event.can_cancel() and \
                         (booking.status == 'OPEN' and not booking.no_show)

            due_date_time = None
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
                    due_date_time = due_date_time.astimezone(uk_tz)

            bookingform = {
                'booking_status': 'CANCELLED' if
                (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
                'ev_type': booking.event.event_type.event_type,
                'booking': booking,
                'paypalform': paypal_form,
                'has_available_block': booking.event.event_type in
                active_block_event_types,
                'can_cancel': can_cancel,
                'on_waiting_list': on_waiting_list,
                'due_date_time': due_date_time,
                }
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


class BookingHistoryListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(
            event__date__lte=timezone.now(), user=self.request.user
        ).order_by('-event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(
            BookingHistoryListView, self
            ).get_context_data(**kwargs)
        # Add in the history flag
        context['history'] = True

        bookingformlist = []
        for booking in self.object_list:
            bookingform = {
                'booking_status': 'CANCELLED' if
                (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
                'booking': booking,
                'ev_type': booking.event.event_type.event_type
            }
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


class BookingCreateView(
    DisclaimerRequiredMixin, LoginRequiredMixin, CreateView
):

    model = Booking
    template_name = 'booking/create_booking.html'
    success_message = 'Your booking has been made for {}.'
    form_class = BookingCreateForm

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(Event, slug=kwargs['event_slug'])

        if self.event.event_type.event_type == 'CL':
            self.ev_type = 'lessons'
        elif self.event.event_type.event_type == 'EV':
            self.ev_type = 'events'
        else:
            self.ev_type = 'room_hires'

        if self.event.cancelled:
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        if self.event.event_type.subtype == "Pole practice" \
                and not self.request.user.has_perm("booking.is_regular_student"):
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        # don't redirect fully/already booked if trying to join/leave waiting
        # list
        if request.method == 'GET' and \
                ('join waiting list' in self.request.GET or
                    'leave waiting list' in self.request.GET):
            return super(BookingCreateView, self).dispatch(request, *args, **kwargs)

        # redirect if fully booked and user doesn't already have open booking
        if self.event.spaces_left <= 0 and self.request.user not in \
            [
                booking.user for booking in self.event.bookings.all()
                if booking.status == 'OPEN' and not booking.no_show
                ]:
            return HttpResponseRedirect(
                reverse('booking:fully_booked', args=[self.event.slug])
            )

        try:
            # redirect if already booked
            booking = Booking.objects.get(
                user=request.user, event=self.event
            )
            # all getting page to rebook if cancelled or previously marked as
            # no_show (i.e. cancelled after cancellation period or cancelled a
            # non-refundable event)
            if booking.status == 'CANCELLED' or booking.no_show:
                return super(
                    BookingCreateView, self
                    ).dispatch(request, *args, **kwargs)
            # redirect if arriving back here from booking update page
            elif request.session.get(
                    'booking_created_{}'.format(booking.id)
            ):
                del self.request.session[
                    'booking_created_{}'.format(booking.id)
                ]
                return HttpResponseRedirect(
                    reverse('booking:{}'.format(self.ev_type))
                )
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                        args=[self.event.slug]))
        except Booking.DoesNotExist:
            return super(BookingCreateView, self).dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk
        }

    def get(self, request, *args, **kwargs):
        if 'join waiting list' in request.GET:
            waitinglistuser, new = WaitingListUser.objects.get_or_create(
                    user=request.user, event=self.event
                )
            if new:
                msg = 'You have been added to the waiting list for {}. ' \
                    ' We will email you if a space becomes ' \
                    'available.'.format(self.event)
                ActivityLog.objects.create(
                    log='User {} has joined the waiting list '
                    'for {}'.format(
                        request.user.username, self.event
                    )
                )
            else:
                msg = 'You are already on the waiting list for {}'.format(
                        self.event
                    )
            messages.success(request, msg)

            if 'bookings' in request.GET:
                return HttpResponseRedirect(
                    reverse('booking:bookings')
                )
            return HttpResponseRedirect(
                reverse('booking:{}'.format(self.ev_type))
            )
        elif 'leave waiting list' in request.GET:
            try:
                waitinglistuser = WaitingListUser.objects.get(
                        user=request.user, event=self.event
                    )
                waitinglistuser.delete()
                msg = 'You have been removed from the waiting list ' \
                    'for {}. '.format(self.event)
                ActivityLog.objects.create(
                    log='User {} has left the waiting list '
                    'for {}'.format(
                        request.user.username, self.event
                    )
                )
            except WaitingListUser.DoesNotExist:
                msg = 'You are not on the waiting list '\
                    'for {}. '.format(self.event)

            messages.success(request, msg)

            if 'bookings' in request.GET:
                return HttpResponseRedirect(
                    reverse('booking:bookings')
                )
            return HttpResponseRedirect(
                reverse('booking:{}'.format(self.ev_type))
            )
        return super(BookingCreateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingCreateView, self).get_context_data(**kwargs)
        updated_context = context_helpers.get_booking_create_context(
            self.event, self.request, context
        )
        return updated_context

    def form_valid(self, form):
        booking = form.save(commit=False)
        try:
            # We shouldn't even get here with a booking that isn't either
            # cancelled or no_show; those get redirected in the dispatch()
            existing_booking = Booking.objects.get(
                user=self.request.user,
                event=booking.event,
                )
            booking = existing_booking
            if booking.status == 'CANCELLED':
                previously_cancelled = True
                previously_no_show = False
            elif booking.no_show:
                previously_no_show = True
                previously_cancelled = False
            booking.status = 'OPEN'
            booking.no_show = False
        except Booking.DoesNotExist:
            previously_cancelled = False
            previously_no_show = False

        booking.user = self.request.user
        transaction_id = None
        invoice_id = None
        previously_cancelled_and_direct_paid = False

        if "claim_free" in form.data:
            _email_free_class_request(
                self.request, booking,
                'rebook' if previously_cancelled else 'create'
            )

        elif previously_cancelled and booking.paid:
            previously_cancelled_and_direct_paid = True
            pptrans = PaypalBookingTransaction.objects.filter(booking=booking)\
                .exclude(transaction_id__isnull=True)
            if pptrans:
                transaction_id = pptrans[0].transaction_id
                invoice_id = pptrans[0].invoice_id

        elif previously_no_show and booking.paid:
            # leave paid no_show booking with existing payment method
            pass

        elif 'block_book' in form.data:
            active_block = _get_active_user_block(self.request.user, booking)
            if active_block:
                booking.block = active_block
                booking.paid = True
                booking.payment_confirmed = True

        # check for existence of free child block on pre-saved booking
        # note for prev no-shows booked with block, any free child blocks should
        # have already been created.  Rebooking prev no-show doesn;t add a new
        # block booking
        has_free_block_pre_save = False
        if booking.block and booking.block.children.exists():
            has_free_block_pre_save = True

        try:
            booking.save()
            ActivityLog.objects.create(
                log='Booking {} {} for "{}" by user {}'.format(
                    booking.id,
                    'created' if not
                    (previously_cancelled or previously_no_show)
                    else 'rebooked',
                    booking.event, booking.user.username)
            )
        except ValidationError:  # pragma: no cover
            # we shouldn't ever get here, because the dispatch should deal
            # with it
            logger.warning(
                'Validation error, most likely due to duplicate booking '
                'attempt; redirected to duplicate booking page'
            )
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                                args=[self.event.slug]))

        # set flag on session so if user clicks "back" after posting the form,
        # we can redirect
        self.request.session['booking_created_{}'.format(booking.id)] = True

        blocks_used, total_blocks = _get_block_status(booking, self.request)

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        ctx = {
              'host': host,
              'booking': booking,
              'event': booking.event,
              'date': booking.event.date.strftime('%A %d %B'),
              'time': booking.event.date.strftime('%H:%M'),
              'blocks_used':  blocks_used,
              'total_blocks': total_blocks,
              'prev_cancelled_and_direct_paid':
              previously_cancelled_and_direct_paid,
              'claim_free': True if "claim_free" in form.data else False,
              'ev_type': self.ev_type[:-1]
        }
        try:
            send_mail('{} Booking for {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                get_template('booking/email/booking_received.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
                html_message=get_template(
                    'booking/email/booking_received.html'
                    ).render(ctx),
                fail_silently=False)

        except Exception as e:
            # send mail to tech support with Exception
            send_support_email(e, __name__, "BookingCreateView")
            messages.error(self.request, "An error occured, please contact "
                "the studio for information")
        # send email to studio if flagged for the event or if previously
        # cancelled and direct paid
        if (booking.event.email_studio_when_booked or
                previously_cancelled_and_direct_paid):
            additional_subject = ""
            if previously_cancelled_and_direct_paid:
                additional_subject = "ACTION REQUIRED!"
            try:
                send_mail('{} {} {} {} has just booked for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, additional_subject,
                    booking.user.first_name, booking.user.last_name, booking.event.name),
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
                                  'transaction_id': transaction_id,
                                  'invoice_id': invoice_id
                              }
                          ),
                          settings.DEFAULT_FROM_EMAIL,
                          [settings.DEFAULT_STUDIO_EMAIL],
                          fail_silently=False)
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(e, __name__, "BookingCreateView")

        extra_msg = ''
        if 'claim_free' in form.data:
            extra_msg = 'Your place will be secured once your free class ' \
                        'request has been reviewed and approved. '
        elif previously_cancelled_and_direct_paid:
            extra_msg = 'You previously paid for this booking; your booking ' \
                        'will remain as pending until the organiser has ' \
                        'reviewed your payment status.'
        elif previously_no_show:
            if booking.block:
                extra_msg = "You previously paid for this booking with a " \
                            "block and your booking has been reopened."
            elif booking.paid:
                extra_msg = "You previously paid for this booking and your " \
                            "booking has been reopened."
        elif not booking.block:
            if booking.event.cost and not booking.paid:
                # prev no_show could still be paid
                cancellation_warning = ""
                if booking.event.advance_payment_required and \
                        booking.event.allow_booking_cancellation:

                    if booking.event.payment_due_date:
                        cancel_str = "by the payment due date"
                    elif booking.event.payment_time_allowed:
                        cancel_str = "within {} hours".format(
                            booking.event.payment_time_allowed
                        )
                    else:
                        cancel_str = "by the cancellation period"

                    cancellation_warning = "Note that if payment " \
                        "has not been received {}, " \
                        "your booking will be automatically cancelled.".format(
                            cancel_str
                        )
                extra_msg = 'Please make your payment as soon as possible. ' \
                            '<strong>{}</strong>'.format(cancellation_warning)
        elif not booking.block.active_block():
            transfer_block = booking.block.block_type.identifier\
                .startswith('transferred') \
                if booking.block.block_type.identifier else False
            if not transfer_block:
                extra_msg = 'You have just used the last space in your block. '
                if booking.block.children.exists() and not has_free_block_pre_save:
                    extra_msg += '</br><span style="color: #9A2EFE;">' \
                                 '<strong>You have qualified for a extra free ' \
                                 'class which has been added to ' \
                                 '<a href="/blocks">your blocks</a></strong><span>  '
                else:
                    extra_msg += 'Go to <a href="/blocks">Your Blocks</a> to ' \
                                 'buy a new one.'

        messages.success(
            self.request,
            mark_safe("{}<br>{}".format(
                self.success_message.format(booking.event),
                extra_msg))
        )

        try:
            waiting_list_user = WaitingListUser.objects.get(
                user=booking.user, event=booking.event
            )
            waiting_list_user.delete()
            ActivityLog.objects.create(
                log='User {} removed from waiting list '
                'for {}'.format(
                    booking.user.username, booking.event
                )
            )
        except WaitingListUser.DoesNotExist:
            pass

        if not booking.paid and booking.event.cost:
            return HttpResponseRedirect(
                reverse('booking:update_booking', args=[booking.id])
            )
        return HttpResponseRedirect(reverse('booking:bookings'))


class BookingUpdateView(DisclaimerRequiredMixin, LoginRequiredMixin, UpdateView):
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
        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))

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

        paypal_form = PayPalPaymentsUpdateForm(
            initial=context_helpers.get_paypal_dict(
                host,
                paypal_cost,
                '{}'.format(self.object.event),
                invoice_id,
                '{} {}{}'.format(
                    'booking', self.object.id,
                    ' {}'.format(voucher.code) if voucher else ''
                ),
                paypal_email=self.object.event.paypal_email,
            )
        )
        context["paypalform"] = paypal_form
        context["paypal_cost"] = paypal_cost

        return context_helpers.get_booking_create_context(
            self.object.event, self.request, context
        )

    def validate_voucher_code(self, voucher, user, event):
        if not voucher.check_event_type(event.event_type):
            return 'Voucher code is not valid for this event/class type'
        elif voucher.has_expired:
            return 'Voucher code has expired'
        elif voucher.max_vouchers and \
            UsedEventVoucher.objects.filter(voucher=voucher).count() >= \
                voucher.max_vouchers:
            return 'Voucher has limited number of total uses and has now expired'
        elif not voucher.has_started:
            return 'Voucher code is not valid until {}'.format(
                voucher.start_date.strftime("%d %b %y")
            )
        elif voucher.max_per_user and UsedEventVoucher.objects.filter(
                voucher=voucher, user=user
        ).count() >= voucher.max_per_user:
            return 'Voucher code has already been used the maximum number ' \
                   'of times ({})'.format(
                    voucher.max_per_user
                    )

    def form_valid(self, form):

        if "apply_voucher" in form.data:
            code = form.data['code'].strip()
            try:
                voucher = EventVoucher.objects.get(code=code)
            except EventVoucher.DoesNotExist:
                voucher = None
                voucher_error = 'Invalid code' if code else 'No code provided'

            if voucher:
                voucher_error = self.validate_voucher_code(
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
            active_block = _get_active_user_block(self.request.user, booking)
            if active_block:
                booking.block = active_block
                booking.paid = True
                booking.payment_confirmed = True
            else:
                messages.error(self.request, 'Error: No available block')

        # check for existence of free child block on pre-saved booking
        has_free_block_pre_save = False
        if booking.block and booking.block.children.exists():
            has_free_block_pre_save = True

        booking.save()

        blocks_used, total_blocks = _get_block_status(booking, self.request)

        if booking.block:
            # send email to user if they used block to book (paypal payment
            # sends separate emails
            host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
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
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
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
            msg = 'You have just used the last space in your block. '
            if booking.block.children.exists() \
                    and not has_free_block_pre_save:
                msg += 'You have qualified for a extra free ' \
                             'class which has been added to ' \
                             '<a href="/blocks">your blocks</a>!  '
            else:
                msg += 'Go to <a href="/blocks">Your Blocks</a> to ' \
                             'buy a new one.'
            messages.info(self.request, mark_safe(msg))

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:bookings')


def _get_active_user_block(user, booking):
    """
    return the active block for this booking with the soonest expiry date
    """
    blocks = user.blocks.all()
    active_blocks = [
        (block, block.expiry_date)
        for block in blocks if block.active_block()
        and block.block_type.event_type == booking.event.event_type
    ]
    # use the block with the soonest expiry date
    if active_blocks:
        return min(active_blocks, key=itemgetter(1))[0]
    else:
        return None


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
    try:
        # send email and set messages
        host = 'http://{}'.format(request.META.get('HTTP_HOST'))
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
    except Exception as e:
        # send mail to tech support with Exception
        send_support_email(e, __name__, "UpdateBookingView - claim free class email")
        messages.error(request, "An error occured, please contact "
            "the studio for information")


def _get_block_status(booking, request):
    blocks_used = None
    total_blocks = None
    if booking.block:
        blocks_used = booking.block.bookings_made()
        total_blocks = booking.block.block_type.size
        ActivityLog.objects.create(
            log='Block used for booking id {} (for {}). Block id {}, '
            'by user {}'.format(
                booking.id, booking.event, booking.block.id,
                request.user.username
            )
        )

    return blocks_used, total_blocks


class BookingDeleteView(DisclaimerRequiredMixin, LoginRequiredMixin, DeleteView):
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
        return super(BookingDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingDeleteView, self).get_context_data(**kwargs)
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        event = Event.objects.get(id=booking.event.id)
        # Add in the event
        context['event'] = event
        # Add in block info
        context['booked_with_block'] = booking.block is not None
        return context

    def delete(self, request, *args, **kwargs):
        booking = self.get_object()

        # Booking can be fully cancelled if the event allows cancellation AND
        # the cancellation period is not past
        # If not, we let people cancel but leave the booking status OPEN and
        # set to no-show
        can_cancel_and_refund = booking.event.allow_booking_cancellation \
            and booking.event.can_cancel()

        event_was_full = booking.event.spaces_left == 0

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user

        ctx = {
                  'host': host,
                  'booking': booking,
                  'event': booking.event,
                  'date': booking.event.date.strftime('%A %d %B'),
                  'time': booking.event.date.strftime('%I:%M %p'),
              }
        try:
            send_mail('{} Booking for {} cancelled'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
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
            if booking.paid and (not booking.block or booking.block.expired):
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
                if booking.event.event_type.event_type != 'EV':
                    block_type, _ = BlockType.objects.get_or_create(
                        event_type=booking.event.event_type,
                        size=1, cost=0, duration=1,
                        identifier='transferred',
                        active=False
                    )
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
                            booking.event.name
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

            # if booking was bought with a block, remove from block and set
            # paid and payment_confirmed to False. If paid directly, paid is only
            # changed to False for bookings that have created transfer blocks; for
            # EV event types, leave paid as True as refunds need to be dealt with
            # manually but change payment_confirmed to False
            # reassigning free class blocks is done in model save
            if booking.block:
                booking.block = None
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
                log='Booking id {} for event {}, user {}, was cancelled by user '
                    '{}'.format(
                        booking.id, booking.event, booking.user.username,
                        self.request.user.username
                    )
            )

            if transfer_block_created:
                ActivityLog.objects.create(
                    log='Transfer block created for user {} (for {}; transferred '
                        'booking id {} '.format(
                            booking.user.username, booking.event.event_type.subtype,
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
            # if the booking wasn't paid, just cancel it
            if not booking.paid:
                booking.status = 'CANCELLED'
                booking.payment_confirmed = False
                booking.save()
                messages.success(
                    self.request,
                    self.success_message.format(booking.event)
                )
                ActivityLog.objects.create(
                    log='Booking id {} for event {}, user {}, was cancelled by user '
                        '{}'.format(
                            booking.id, booking.event, booking.user.username,
                            self.request.user.username
                        )
                )
            else:  # set to no-show
                booking.no_show = True
                booking.save()

                if not booking.event.allow_booking_cancellation:
                    messages.success(
                        self.request,
                        self.success_message.format(booking.event) +
                        ' Please note that this booking is not eligible for refunds '
                        'or transfer credit.'
                    )
                    ActivityLog.objects.create(
                        log='Booking id {} for NON-CANCELLABLE event {}, user {}, '
                            'was cancelled and set to no-show'.format(
                                booking.id, booking.event, booking.user.username,
                                self.request.user.username
                            )
                    )
                else:
                    messages.success(
                        self.request,
                        self.success_message.format(booking.event) +
                        ' Please note that this booking is not eligible for '
                        'refunds or transfer credit as the allowed '
                        'cancellation period has passed.'
                    )
                    ActivityLog.objects.create(
                        log='Booking id {} for event {}, user {}, was cancelled '
                            'after the cancellation period and set to '
                            'no-show'.format(
                                booking.id, booking.event, booking.user.username,
                                self.request.user.username
                            )
                    )

        # if applicable, email users on waiting list
        if event_was_full:
            waiting_list_users = WaitingListUser.objects.filter(
                event=booking.event
            )
            if waiting_list_users:
                try:
                    send_waiting_list_email(
                        booking.event,
                        [wluser.user for wluser in waiting_list_users],
                        host='http://{}'.format(request.META.get('HTTP_HOST'))
                    )
                    ActivityLog.objects.create(
                        log='Waiting list email sent to user(s) {} for '
                        'event {}'.format(
                            ', '.join(
                                [wluser.user.username for \
                                wluser in waiting_list_users]
                            ),
                            booking.event
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(e, __name__, "DeleteBookingView - waiting list email")
                    messages.error(self.request, "An error occured, please contact "
                        "the studio for information")

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:bookings')


def duplicate_booking(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if event.event_type.event_type == 'EV':
        ev_type = 'event'
    elif event.event_type.event_type == 'CL':
        ev_type = 'class'
    else:
        ev_type = 'room hire'

    context = {'event': event, 'ev_type': ev_type}

    return render(request, 'booking/duplicate_booking.html', context)


def update_booking_cancelled(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.event.event_type.event_type == 'EV':
        ev_type = 'event'
    elif booking.event.event_type.event_type == 'CL':
        ev_type = 'class'
    else:
        ev_type = 'room hire'
    context = {'booking': booking, 'ev_type': ev_type}
    if booking.event.spaces_left == 0:
        context['full'] = True
    return render(request, 'booking/update_booking_cancelled.html', context)


def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    if event.event_type.event_type == 'EV':
        ev_type = 'event'
    elif event.event_type.event_type == 'CL':
        ev_type = 'class'
    else:
        ev_type = 'room hire'

    context = {'event': event, 'ev_type': ev_type}
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
