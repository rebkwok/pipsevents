import logging
import pytz

from datetime import timedelta

from operator import itemgetter

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail
from django.template.loader import get_template
from braces.views import LoginRequiredMixin

from payments.forms import PayPalPaymentsListForm, PayPalPaymentsUpdateForm
from payments.models import PaypalBookingTransaction

from booking.models import Event, Booking, Block, BlockType, WaitingListUser, \
    BookingError
from booking.forms import BookingCreateForm
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email
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
                        '{} {}'.format('booking', booking.id)
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
                         booking.status == 'OPEN'

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
            (Q(event__date__lte=timezone.now()) | Q(status='CANCELLED')) &
            Q(user=self.request.user)
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
            bookingform = {'booking': booking}
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


class BookingCreateView(LoginRequiredMixin, CreateView):

    model = Booking
    template_name = 'booking/create_booking.html'
    success_message = 'Your booking has been made for {}.'
    form_class = BookingCreateForm

    def dispatch(self, *args, **kwargs):
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

        return super(BookingCreateView, self).dispatch(*args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk
        }

    def get(self, request, *args, **kwargs):

        # redirect if fully booked or already booked
        if 'join waiting list' in request.GET:
            waitinglistuser, new = WaitingListUser.objects.get_or_create(
                    user=request.user, event=self.event
                )
            if new:
                msg = 'You have been added to the waiting list for {}. ' \
                    ' We will email you if a space becomes ' \
                    'available.'.format(self.event)
                ActivityLog.objects.create(
                    log='User {} has been added to the waiting list '
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
        elif self.event.spaces_left() <= 0 and self.request.user not in \
            [
                booking.user for booking in self.event.bookings.all()
                if booking.status == 'OPEN'
                ]:
            return HttpResponseRedirect(
                reverse('booking:fully_booked', args=[self.event.slug])
            )

        try:
            booking = Booking.objects.get(
                user=self.request.user, event=self.event
            )
            if booking.status == 'CANCELLED':
                return super(
                    BookingCreateView, self
                    ).get(request, *args, **kwargs)
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                        args=[self.event.slug]))
        except Booking.DoesNotExist:
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
            cancelled_booking = Booking.objects.get(
                user=self.request.user,
                event=booking.event,
                status='CANCELLED'
                )
            booking = cancelled_booking
            booking.status = 'OPEN'
            previously_cancelled = True
        except Booking.DoesNotExist:
            previously_cancelled = False

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

        elif 'block_book' in form.data:
            active_block = _get_active_user_block(self.request.user, booking)
            if active_block:
                booking.block = active_block
                booking.paid = True
                booking.payment_confirmed = True

        # check for existence of free child block on pre-saved booking
        has_free_block_pre_save = False
        if booking.block and booking.block.children.exists():
            has_free_block_pre_save = True

        try:
            booking.save()
            ActivityLog.objects.create(
                log='Booking {} {} for "{}" by user {}'.format(
                    booking.id,
                    'created' if not previously_cancelled else 'rebooked',
                    booking.event, booking.user.username)
            )
        except IntegrityError:
            logger.warning(
                'Integrity error; redirected to duplicate booking page'
            )
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                                args=[self.event.slug]))
        except BookingError:
            return HttpResponseRedirect(reverse('booking:fully_booked',
                                                args=[self.event.slug]))

        blocks_used, total_blocks = _get_block_status(
            booking, has_free_block_pre_save
        )

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
            ActivityLog.objects.create(
                log='Email sent to user {} regarding {}booking id {} '
                '(for {})'.format(
                    booking.user.username,
                    're' if previously_cancelled else '', booking.id, booking.event
                )
            )
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

            ActivityLog.objects.create(
                log= 'Email sent to studio ({}) regarding {}booking id {} '
                '(for {})'.format(
                    settings.DEFAULT_STUDIO_EMAIL,
                    're' if previously_cancelled else '', booking.id,
                    booking.event
                )
            )

        extra_msg = ''
        if 'claim_free' in form.data:
            extra_msg = 'Your place will be secured once your free class ' \
                        'request has been reviewed and approved. '
        elif previously_cancelled_and_direct_paid:
            extra_msg = 'You previously paid for this booking; your booking ' \
                        'will remain as pending until the organiser has ' \
                        'reviewed your payment status.'
        elif not booking.block:
            if booking.event.cost:
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
                        "your booking will be atically cancelled.".format(
                            cancel_str
                        )
                extra_msg = 'Please make your payment as soon as possible. ' \
                            '<strong>{}</strong>'.format(cancellation_warning)
        elif not booking.block.active_block():
            extra_msg = 'You have just used the last space in your block. '
            if booking.block.children.exists() and not has_free_block_pre_save:
                extra_msg += '</br><span style="color: #9A2EFE;"><strong>You have qualified for a extra free ' \
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

        if "book_one_off" in form.data and booking.event.cost:
            return HttpResponseRedirect(
                reverse( 'booking:update_booking', args=[booking.id])
            )
        return HttpResponseRedirect(reverse('booking:bookings'))


class BookingUpdateView(LoginRequiredMixin, UpdateView):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_message = 'Booking updated for {}!'
    fields = ['paid']

    def get(self, request, *args, **kwargs):
        # redirect if event cancelled
        booking = get_object_or_404(Booking, id=self.kwargs['pk'])
        if booking.event.cancelled:
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        # redirect if booking cancelled
        if booking.status == 'CANCELLED':
            return HttpResponseRedirect(reverse('booking:update_booking_cancelled',
                                        args=[booking.id]))

        return super(BookingUpdateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingUpdateView, self).get_context_data(**kwargs)

        invoice_id = create_booking_paypal_transaction(
            self.request.user, self.object
        ).invoice_id
        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        paypal_form = PayPalPaymentsUpdateForm(
            initial=context_helpers.get_paypal_dict(
                host,
                self.object.event.cost,
                self.object.event,
                invoice_id,
                '{} {}'.format('booking', self.object.id)
            )
        )
        context["paypalform"] = paypal_form

        return context_helpers.get_booking_create_context(
            self.object.event, self.request, context
        )

    def form_valid(self, form):
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

        try:
            booking.save()
        except BookingError:
            return HttpResponseRedirect(
                reverse('booking:fully_booked',
                    args=[booking.event.slug])
            )

        blocks_used, total_blocks = _get_block_status(
            booking, has_free_block_pre_save
        )

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


def _get_block_status(booking, has_free_block_pre_save):
    blocks_used = None
    total_blocks = None
    if booking.block:
        blocks_used = booking.block.bookings_made()
        total_blocks = booking.block.block_type.size
        ActivityLog.objects.create(
            log='Block used for booking id {} (for {}). Block id {}, '
            'user {}'.format(
                booking.id, booking.event, booking.block.id,
                booking.user.username
            )
        )

        if booking.block.children.exists() and not has_free_block_pre_save:
            # just used last block in 10 class pole level class block;
            # check for free class block, add one if doesn't exist already
            ActivityLog.objects.create(
                log='Free class block created. Block id {}, parent '
                    'block id {}, user {}'.format(
                    booking.block.children.first().id, booking.block.id,
                    booking.user.username
                )
            )
    return blocks_used, total_blocks


class BookingDeleteView(LoginRequiredMixin, DeleteView):
    model = Booking
    template_name = 'booking/delete_booking.html'
    success_message = 'Booking cancelled for {}'

    def dispatch(self, request, *args, **kwargs):
        # redirect if cancellation period past
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        if not booking.event.allow_booking_cancellation:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        elif not booking.event.can_cancel():
            return HttpResponseRedirect(
                reverse('booking:cancellation_period_past',
                        args=[booking.event.slug])
            )
        elif booking.status == 'CANCELLED':
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
        event_was_full = booking.event.spaces_left() == 0

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

        if not booking.block and booking.paid and not booking.free_class:
            # send email to studio
            send_mail('{} {} {} has just cancelled a booking for {}'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                'ACTION REQUIRED!' if not booking.block else '',
                booking.user.username,
                booking.event.name),
                      get_template('booking/email/to_studio_booking_cancelled.txt').render(
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
        # paid and payment_confirmed to False. If paid directly, we need to
        # deal with refunds manually, so leave paid as True but change
        # payment_confirmed to False
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
            log='Booking id {} for event {}, user {}, was cancelled'.format(
                booking.id, booking.event, booking.user.username
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
    if booking.event.spaces_left() == 0:
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

