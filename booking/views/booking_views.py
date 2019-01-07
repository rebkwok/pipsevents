# -*- coding: utf-8 -*-
import logging
import pytz

from decimal import Decimal

from datetime import timedelta

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.db.models import Q, Sum
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
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

from accounts.utils import has_expired_disclaimer, has_active_disclaimer

from booking.models import (
    Block, BlockType, Booking, Event, UsedEventVoucher, EventVoucher,
    WaitingListUser
)
from booking.forms import BookingCreateForm, VoucherForm
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email
from booking.views.views_utils import DisclaimerRequiredMixin, \
    DataPolicyAgreementRequiredMixin, \
    _get_active_user_block, _get_block_status, validate_voucher_code

from booking.templatetags.bookingtags import format_paid_status, get_shopping_basket_icon

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
        bookings = context['bookings']

        for booking in bookings:
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

            bookingform = {
                'booking_status': 'CANCELLED' if
                (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
                'ev_type': booking.event.event_type.event_type,
                'booking': booking,
                'paypalform': paypal_form,
                'has_available_block': booking.event.event_type in
                active_block_event_types,
                'on_waiting_list': on_waiting_list,
                'due_date_time': due_date_time(booking),
                }
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist

        return context


class BookingHistoryListView(DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'
    paginate_by = 20

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
        bookings = context['bookings']

        for booking in bookings:
            bookingform = {
                'booking_status': 'CANCELLED' if
                (booking.status == 'CANCELLED' or booking.no_show) else 'OPEN',
                'booking': booking,
                'ev_type': booking.event.event_type.event_type
            }
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


# TODO: unused, delete?
class BookingCreateView(
    DataPolicyAgreementRequiredMixin, DisclaimerRequiredMixin, LoginRequiredMixin,
    CreateView
):

    model = Booking
    template_name = 'booking/create_booking.html'
    success_message = 'Your booking has been made for {}.'
    form_class = BookingCreateForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        self.event = get_object_or_404(Event, slug=kwargs['event_slug'])

        if self.event.event_type.event_type == 'CL':
            self.ev_type = 'lessons'
            self.ev_type_str = 'class'
        elif self.event.event_type.event_type == 'EV':
            self.ev_type = 'events'
            self.ev_type_str = 'workshop/event'
        else:
            self.ev_type = 'room_hires'
            self.ev_type_str = 'room hire'

        if self.event.cancelled:
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        if self.event.event_type.subtype == "Pole practice" \
                and not self.request.user.has_perm("booking.is_regular_student"):
            return HttpResponseRedirect(reverse('booking:permission_denied'))

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
            booking = Booking.objects.get(user=request.user, event=self.event)
            # all getting page to rebook if cancelled or previously marked as
            # no_show (i.e. cancelled after cancellation period or cancelled a
            # non-refundable event)
            if booking.status == 'CANCELLED' or booking.no_show:
                return super().dispatch(request, *args, **kwargs)
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
        except (Booking.DoesNotExist):
            return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk
        }

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingCreateView, self).get_context_data(**kwargs)
        updated_context = context_helpers.get_booking_create_context(
            self.event, self.request, context
        )
        return updated_context

    def form_valid(self, form):
        booking = form.save(commit=False)
        previously_cancelled = False
        previously_no_show = False
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
            pass

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
              'ev_type': self.ev_type_str
        }
        try:
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

        except Exception as e:
            # send mail to tech support with Exception
            send_support_email(e, __name__, "BookingCreateView")
            messages.error(self.request, "An error occured, please contact "
                "the studio for information")
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
            try:
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
                        "your booking will be automatically cancelled and you " \
                        "will need to contact the studio directly to " \
                        "rebook.".format(
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

        # keep the booking so we can use it in BookingMultiCreateView
        self.booking = booking

        if not booking.paid and booking.event.cost:
            return HttpResponseRedirect(reverse('booking:shopping_basket'))
        return HttpResponseRedirect(reverse('booking:bookings'))


# TODO: unused, delete?
class BookingMultiCreateView(BookingCreateView):

    success_message = "Booking for {} created"

    def form_valid(self, form):
        super(BookingMultiCreateView, self).form_valid(form)
        filter = form.data.get('filter')
        # redirect to specified next page, or to ev_type (lessons/events/roomhires)
        params = {
            'name': form.data.get('filter', ''),
            'tab': form.data.get('tab', 0),
            'page': form.data.get('page', '')
        }

        # get rid of base class messages and just show the add to basket one
        list(messages.get_messages(self.request))

        msg = self.success_message.format(self.booking.event)

        if not self.booking.paid:
            # booking could still be paid if it's a rebooking for a cancelled
            # free class or for a booking previously cancelled after allowed
            # time
            msg += " and added to <a href='/bookings/shopping-basket'>basket</a>"

        messages.success(self.request, mark_safe(msg))
        next = form.data.get('next', self.ev_type)
        url = reverse('booking:{}'.format(next))
        url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)


# TODO: unused, delete?
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

        custom = context_helpers.get_paypal_custom(
            item_type='booking',
            item_ids=str(self.object.id),
            voucher_code=voucher.code if context.get('valid_voucher', False) else None,
            user_email=self.request.user.email
        )
        paypal_form = PayPalPaymentsUpdateForm(
            initial=context_helpers.get_paypal_dict(
                host,
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

        return context_helpers.get_booking_create_context(
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
            if booking.block.children.exists() \
                    and not has_free_block_pre_save:
                messages.info(
                    self.request,
                    mark_safe(
                        'You have just used the last space in your block and '
                        'have qualified for a extra free class which has '
                        'been added to <a href="/blocks">your blocks</a>!  '
                    )
                )
            elif not booking.has_available_block:
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
        context['block_booked_within_allowed_time'] = self._block_booked_within_allowed_time(booking)
        context['booking'] = booking
        return context

    def _block_booked_within_allowed_time(self, booking):
        allowed_datetime = timezone.now() - timedelta(minutes=15)
        if booking.block:
            return (booking.date_rebooked and booking.date_rebooked > allowed_datetime) \
                   or (booking.date_booked > allowed_datetime)
        return False

    def _can_fully_delete(self, booking):
        # if booking isn't paid, and wasn't a rebooking, and has no associated
        # paypal transaction (i.e. it's not refunded), we can just fully delete it
        if not (booking.paid or booking.deposit_paid or booking.date_rebooked):
            return not PaypalBookingTransaction.objects\
                .filter(booking=booking, transaction_id__isnull=False).exists()
        return False

    def delete(self, request, *args, **kwargs):
        booking = self.get_object()
        event = booking.event

        can_fully_delete = self._can_fully_delete(booking)

        # Booking can be fully cancelled if the event allows cancellation AND
        # the cancellation period is not past
        # If not, we let people cancel but leave the booking status OPEN and
        # set to no-show
        can_cancel_and_refund = booking.event.allow_booking_cancellation \
            and event.can_cancel() and not can_fully_delete

        event_was_full = event.spaces_left == 0

        if not can_fully_delete:
            # email if this isn't an unpaid/non-rebooked booking

            host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
            # send email to user

            ctx = {
                      'host': host,
                      'booking': booking,
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
                if event.event_type.event_type != 'EV':
                    block_type, _ = BlockType.objects.get_or_create(
                        event_type=event.event_type,
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

        elif can_fully_delete:
            ActivityLog.objects.create(
                log='Booking id {} for event {} was cancelled by user '
                    '{} and deleted'.format(
                        booking.id, event,
                        self.request.user.username
                    )
            )
            booking.delete()

        else:
            # if the booking was made with a block, allow 15 mins to cancel in case user
            # clicked the wrong button by mistake and autobooked with a block
            # if the booking wasn't paid, just cancel it
            booked_within_allowed_time = self._block_booked_within_allowed_time(booking)

            can_cancel = (booking.block and booked_within_allowed_time) or not booking.paid
            if can_cancel:
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
        if event_was_full:
            waiting_list_users = WaitingListUser.objects.filter(
                event=event
            )
            if waiting_list_users:
                try:
                    send_waiting_list_email(
                        event,
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
                            event
                        )
                    )
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(e, __name__, "DeleteBookingView - waiting list email")
                    messages.error(self.request, "An error occured, please contact "
                        "the studio for information")

        next = request.GET.get('next') or request.POST.get('next')
        params = {}
        if request.GET.get('booking_code'):
            params['booking_code'] = request.GET['booking_code']
        if request.GET.get('block_code'):
            params['block_code'] = request.GET['block_code']
        if request.GET.get('filter'):
            params['name'] = request.GET['filter']
        if request.GET.get('tab'):
            params['tab'] = request.GET['tab']
        if request.GET.get('page'):
            params['page'] = request.GET['page']

        url = self.get_success_url(next)
        if params:
            url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)

    def get_success_url(self, next):
        if next:
            return reverse('booking:{}'.format(next))
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


@login_required
@require_http_methods(['POST'])
def ajax_create_booking(request, event_id):

    if not has_active_disclaimer(request.user):
        return HttpResponseRedirect(reverse('booking:disclaimer_required'))

    event = Event.objects.get(id=event_id)
    location_index = request.GET.get('location_index')
    location_page = request.GET.get('location_page', 1)
    ref = request.GET.get('ref')

    if event.event_type.event_type == 'CL':
        ev_type_str = 'class'
        ev_type = 'lessons'
    elif event.event_type.event_type == 'EV':
        ev_type_str = 'workshop/event'
        ev_type = 'events'
    else:
        ev_type_str = 'room hire'
        ev_type = 'room_hires'

    previously_cancelled = False
    previously_no_show = False

    context = {
        "event": event, "type": ev_type,
        "location_index": location_index,
        "location_page": location_page,
        "ref": ref
    }

    # make sure this isn't an open booking already
    if Booking.objects.filter(user=request.user, event=event).exists():
        booking = Booking.objects.get(user=request.user, event=event)
        if booking.status == "OPEN" and not booking.no_show:
            return HttpResponseBadRequest()

    # if pole practice, make sure this user has permission
    if event.event_type.subtype == "Pole practice" \
        and not request.user.has_perm("booking.is_regular_student"):
            return HttpResponseBadRequest(
                "You must be a regular student to book this class; please "
                "contact the studio for further information."
            )

    # make sure the event isn't full or cancelled
    if not event.spaces_left or event.cancelled:
        message = "Sorry, this event {}".format('is now full' if not event.spaces_left else "has been cancelled")
        return HttpResponseBadRequest(message)

    booking, new = Booking.objects.get_or_create(user=request.user, event=event)
    context['booking'] = booking

    if not new:
        if booking.status == 'CANCELLED':
            previously_cancelled = True
            previously_no_show = False
        elif booking.no_show:
            previously_no_show = True
            previously_cancelled = False

    booking.status = 'OPEN'
    booking.no_show = False

    transaction_id = None
    invoice_id = None
    previously_cancelled_and_direct_paid = False

    if previously_cancelled and booking.paid:
        previously_cancelled_and_direct_paid = True
        pptrans = PaypalBookingTransaction.objects.filter(booking=booking)\
            .exclude(transaction_id__isnull=True)
        if pptrans:
            transaction_id = pptrans[0].transaction_id
            invoice_id = pptrans[0].invoice_id

    elif previously_no_show and booking.paid:
        # leave paid no_show booking with existing payment method
        pass

    active_block = _get_active_user_block(request.user, booking)

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

    booking.save()
    ActivityLog.objects.create(
        log='Booking {} {} for "{}" by user {}'.format(
            booking.id,
            'created' if not
            (previously_cancelled or previously_no_show)
            else 'rebooked',
                booking.event, booking.user.username)
    )

    blocks_used, total_blocks = _get_block_status(booking, request)

    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
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
          'claim_free': False,
          'ev_type': ev_type_str
    }
    try:
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
    except Exception as e:
        # send mail to tech support with Exception
        send_support_email(e, __name__, "ajax_create_booking")

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

        try:
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
                              'transaction_id': transaction_id,
                              'invoice_id': invoice_id
                          }
                      ),
                      settings.DEFAULT_FROM_EMAIL,
                      [settings.DEFAULT_STUDIO_EMAIL],
                      fail_silently=False)
        except Exception as e:
            # send mail to tech support with Exception
            send_support_email(e, __name__, "ajax_create_booking")

    alert_message = {}

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
        msg = "Booked with block. "
        if not booking.block.active_block():
            transfer_block = booking.block.block_type.identifier\
                .startswith('transferred') \
                if booking.block.block_type.identifier else False
            if not transfer_block:
                msg += 'You have just used the last space in your block. '
                if booking.block.children.exists() and not has_free_block_pre_save:
                    msg += 'You have qualified for a extra free ' \
                                 'class which has been added to your blocks'
                else:
                    alert_message['message_type'] = 'warning'
                    msg += 'Go to My Blocks buy a new one.'
        alert_message['message'] = msg
    elif not booking.paid:
        alert_message['message_type'] = 'error'
        alert_message['message'] =  "Added to basket; booking not confirmed until payment has been made."

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

    context["alert_message"] = alert_message

    return render(
        request,
        "booking/includes/ajax_book_button.txt",
        context
    )


@login_required
def update_shopping_basket_count(request):
    context = get_shopping_basket_icon(request.user, True)
    return render(
        request,
        "booking/includes/shopping_basket_icon.html",
        context
    )


@login_required
def update_booking_count(request, event_id):
    event = Event.objects.get(id=event_id)
    return render(request, "booking/includes/booking_count.html", {'event': event})


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


@login_required
def booking_details(request, event_id):
    booking = Booking.objects.get(user=request.user, event=Event.objects.get(id=event_id))
    if booking.paid:
        payment_due = "Received"
    elif due_date_time(booking):
        payment_due = due_date_time(booking).strftime('%a %d %b %H:%M')
    else:
        payment_due = "N/A"

    if booking.space_confirmed and booking.paid:
        confirmed = '<span class="fa fa-check"></span>'
    elif booking.status == 'CANCELLED':
        confirmed = '<span class="fa fa-times"></span>'
    else:
        confirmed = 'Pending'

    return JsonResponse(
        {
            'paid': booking.paid,
            'paid_status': format_paid_status(booking),
            'status': booking.status,
            'payment_due': payment_due,
            'block': '<span class="confirmed fa fa-check"></span>' if booking.block else '<strong>N/A</strong>',
            'confirmed': confirmed,
            'no_show': booking.no_show
        }
    )


