import logging

from django import forms
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
from django.template import Context
from braces.views import LoginRequiredMixin

from payments.forms import PayPalPaymentsListForm, PayPalPaymentsUpdateForm
from payments.models import PaypalBookingTransaction

from booking.models import Event, Booking, Block, BlockType, WaitingListUser, \
    BookingError
from booking.forms import BookingCreateForm, BlockCreateForm, EventFilter, \
    LessonFilter, get_event_names
import booking.context_helpers as context_helpers
from booking.email_helpers import send_support_email, send_waiting_list_email
from payments.helpers import create_booking_paypal_transaction, \
    create_block_paypal_transaction

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class EventListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        if self.kwargs['ev_type'] == 'events':
            ev_abbr = 'EV'
        else:
            ev_abbr = 'CL'

        name = self.request.GET.get('name')

        if name:
            return Event.objects.filter(
                Q(event_type__event_type=ev_abbr) & Q(date__gte=timezone.now())
                & Q(name=name)).order_by('date')
        return Event.objects.filter(
            (Q(event_type__event_type=ev_abbr) & Q(date__gte=timezone.now()))
            ).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
            # Add in the booked_events
            user_bookings = self.request.user.bookings.all()
            booked_events = [booking.event for booking in user_bookings
                             if not booking.status == 'CANCELLED']
            user_waiting_lists = WaitingListUser.objects.filter(user=self.request.user)
            waiting_list_events = [wluser.event for wluser in user_waiting_lists]
            context['booked_events'] = booked_events
            context['waiting_list_events'] = waiting_list_events
            context['is_regular_student'] = self.request.user.has_perm(
                "booking.is_regular_student"
            )
        context['type'] = self.kwargs['ev_type']

        event_name = self.request.GET.get('name', '')
        if self.kwargs['ev_type'] == 'events':
            form = EventFilter(initial={'name': event_name})
        else:
            form = LessonFilter(initial={'name': event_name})
        context['form'] = form
        return context


class EventDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        if self.kwargs['ev_type'] == 'event':
            ev_abbr = 'EV'
        else:
            ev_abbr = 'CL'
        queryset = Event.objects.filter(event_type__event_type=ev_abbr)

        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data()
        event = self.object
        return context_helpers.get_event_context(
            context, event, self.request.user
        )


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

            can_cancel = booking.event.can_cancel() and \
                booking.status == 'OPEN'
            bookingform = {
                'ev_type': booking.event.event_type.event_type,
                'booking': booking,
                'paypalform': paypal_form,
                'has_available_block': booking.event.event_type in
                active_block_event_types,
                'can_cancel': can_cancel,
                'on_waiting_list': on_waiting_list
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
        return super(BookingCreateView, self).dispatch(*args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk
        }

    def get(self, request, *args, **kwargs):
        if self.event.event_type.subtype == "Pole practice" \
                and not request.user.has_perm("booking.is_regular_student"):
            return HttpResponseRedirect(reverse('booking:permission_denied'))

        # redirect if fully booked or already booked
        elif 'join waiting list' in request.GET:
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

            ev_type = 'lessons' \
                if self.event.event_type.event_type == 'CL' \
                else 'events'

            if 'bookings' in request.GET:
                return HttpResponseRedirect(
                    reverse('booking:bookings')
                )
            return HttpResponseRedirect(
                reverse('booking:{}'.format(ev_type))
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

            ev_type = 'lessons' \
                if self.event.event_type.event_type == 'CL' \
                else 'events'

            if 'bookings' in request.GET:
                return HttpResponseRedirect(
                    reverse('booking:bookings')
                )
            return HttpResponseRedirect(
                reverse('booking:{}'.format(ev_type))
            )
        elif self.event.spaces_left() <= 0:
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

        transaction_id = None
        invoice_id = None
        previously_cancelled_and_direct_paid = False

        if 'block_book' in form.data:
            blocks = self.request.user.blocks.all()
            active_block = [
                block for block in blocks if block.active_block()
                and block.block_type.event_type == booking.event.event_type][0]

            booking.block = active_block
            booking.paid = True
            booking.payment_confirmed = True

        elif "claim_free" in form.data:
            # if user is requesting a free class, send email to studio and
            # make booking unpaid
            ActivityLog.objects.create(
                log='Free class requested ({}) by user {}'.format(
                    form.instance.event, self.request.user.username)
            )
            booking.paid = False
            booking.payment_confirmed = False
            booking.block = None
            try:
                # send email and set messages
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                # send email to studio
                ctx = Context({
                      'host': host,
                      'event': form.instance.event,
                      'user': self.request.user,
                      'booking_status': 'rebook' if previously_cancelled else 'create',
                })
                send_mail(
                    '{} Request to claim free class from {} {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        self.request.user.first_name, self.request.user.last_name
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
                    self.request,
                    "Your request to claim a free class has been sent "
                    "to the studio for review."
                )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(e, __name__, "CreateBookingView - claim free class email")
                messages.error(self.request, "An error occured, please contact "
                    "the studio for information")
        elif previously_cancelled and booking.paid:
            previously_cancelled_and_direct_paid = True
            pptrans = PaypalBookingTransaction.objects.filter(booking=booking)\
                .exclude(transaction_id__isnull=True)
            if pptrans:
                transaction_id = pptrans[0].transaction_id
                invoice_id = pptrans[0].invoice_id

        booking.user = self.request.user
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
        else:
            blocks_used = None
            total_blocks = None

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        ctx = Context({
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
              'ev_type': 'event' if
              self.event.event_type.event_type == 'EV' else 'class'
        })
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
                          Context({
                              'host': host,
                              'booking': booking,
                              'event': booking.event,
                              'date': booking.event.date.strftime('%A %d %B'),
                              'time': booking.event.date.strftime('%H:%M'),
                              'prev_cancelled_and_direct_paid':
                              previously_cancelled_and_direct_paid,
                              'transaction_id': transaction_id,
                              'invoice_id': invoice_id
                          })
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

        messages.success(
            self.request,
            self.success_message.format(booking.event)
        )

        if 'claim_free' in form.data:
            messages.info(
                self.request, 'Your place will be secured once your free '
                'class request has been reviewed and approved. '
            )
        elif previously_cancelled_and_direct_paid:
            messages.info(
                self.request, 'You previously paid for this booking; your '
                              'booking will remain as pending until the '
                              'organiser has reviewed your payment status.'
            )
        elif not booking.block:
            if booking.event.cost:
                cancellation_warning = ""
                if booking.event.advance_payment_required:
                    cancellation_warning = "Note that if payment " \
                        "has not been received by the cancellation period, " \
                        "your booking will be automatically cancelled."
                messages.info(
                    self.request, mark_safe('Please make your payment as soon '
                        'as possible.  '
                        '<strong>{}</strong>'.format(cancellation_warning)
                    )
                )
        elif not booking.block.active_block():
            messages.info(self.request, mark_safe(
                          'You have just used the last space in your block.  '
                          'Go to <a href="/blocks">'
                          'Your Blocks</a> to buy a new one.'))
            if booking.block.block_type.size == 10:
                try:
                    send_mail('{} {} has just used the last of 10 blocks'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        booking.user.username),
                              "{} {} ({}) has just used the last of a block of 10"
                              " and is now eligible for a free class.".format(
                                booking.user.first_name,
                                booking.user.last_name, booking.user.username
                              ),
                              settings.DEFAULT_FROM_EMAIL,
                              [settings.DEFAULT_STUDIO_EMAIL],
                              fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(e, __name__, "CreateBookingView - notify studio of completed 10 block")

        try:
            waiting_list_user = WaitingListUser.objects.get(
                user=booking.user, event=booking.event
            )
            waiting_list_user.delete()
            ActivityLog.objects.create(
                log='User {} has been removed from the waiting list '
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


class BlockCreateView(LoginRequiredMixin, CreateView):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block booking created: {}'

    def get(self, request, *args, **kwargs):
        # redirect if user already has active (paid or unpaid) blocks for all
        # blocktypes
        if not context_helpers.get_blocktypes_available_to_book(
                self.request.user):
            return HttpResponseRedirect(reverse('booking:has_active_block'))
        return super(BlockCreateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockCreateView, self).get_context_data(**kwargs)
        context['form'].fields['block_type'].queryset = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        context['block_types'] = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        return context

    def form_valid(self, form):
        block_type = form.cleaned_data['block_type']
        types_available = context_helpers.get_blocktypes_available_to_book(
            self.request.user)
        if block_type.event_type in types_available:
            return HttpResponseRedirect(reverse('booking:has_active_block'))

        block = form.save(commit=False)
        block.user = self.request.user
        block.save()

        ActivityLog.objects.create(
            log='Block {} has been created; Block type: {}; user: {}'.format(
                block.id, block.block_type, block.user.username
            )
        )

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        ctx = Context({
                          'host': host,
                          'user': block.user,
                          'block_type': block.block_type,
                          'start_date': block.start_date,
                          'expiry_date': block.expiry_date,
                      })
        send_mail('{} Block booking confirmed'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            get_template('booking/email/block_booked.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [block.user.email],
            html_message=get_template(
                'booking/email/block_booked.html').render(ctx),
            fail_silently=False)
        # send email to studio
        # send_mail('{} {} has just booked a block'.format(
        #     settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, block.user.username),
        #     get_template('booking/email/to_studio_block_booked.txt').render(ctx),
        #     settings.DEFAULT_FROM_EMAIL,
        #     [settings.DEFAULT_STUDIO_EMAIL],
        #     fail_silently=False)
        ActivityLog.objects.create(
            log='Email sent to user ({}) regarding new block id {}; type: {}'.format(
                block.user.email, block.id, block.block_type
            )
        )
        messages.success(
            self.request, self.success_message.format(block.block_type)
            )
        return HttpResponseRedirect(block.get_absolute_url())


class BlockListView(LoginRequiredMixin, ListView):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)

        types_available_to_book = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        if types_available_to_book:
            context['can_book_block'] = True

        blockformlist = []
        for block in self.object_list:
            if not block.paid:
                invoice_id = create_block_paypal_transaction(
                    self.request.user, block).invoice_id
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                paypal_form = PayPalPaymentsListForm(
                    initial=context_helpers.get_paypal_dict(
                        host,
                        block.block_type.cost,
                        block.block_type,
                        invoice_id,
                        '{} {}'.format('block', block.id)
                    )
                )
            else:
                paypal_form = None

            expired = block.expiry_date < timezone.now()
            full = Booking.objects.filter(
                block__id=block.id).count() >= block.block_type.size
            blockform = {
                'block': block,
                'paypalform': paypal_form,
                'expired': expired or full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')


class BookingUpdateView(LoginRequiredMixin, UpdateView):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_message = 'Booking updated for {}!'
    fields = ['paid']

    def get(self, request, *args, **kwargs):
        # redirect if cancelled
        try:
            booking = Booking.objects.get(
                user=self.request.user, id=self.kwargs['pk'],
                status='CANCELLED'
            )
            return HttpResponseRedirect(reverse('booking:update_booking_cancelled',
                                        args=[booking.id]))
        except Booking.DoesNotExist:
            return super(BookingUpdateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingUpdateView, self).get_context_data(**kwargs)

        # find if a user has a usable block
        user_blocks = self.request.user.blocks.all()
        active_user_block_event_types = [block.block_type.event_type
                                         for block in user_blocks
                                         if block.active_block()]

        if self.object.event.event_type in active_user_block_event_types:
            context['active_user_block'] = True
        else:
            # find if block booking is available for this type of event
            blocktypes = [
                blocktype.event_type for blocktype in BlockType.objects.all()
                ]
            blocktype_available = self.object.event.event_type in blocktypes
            context['blocktype_available'] = blocktype_available

        if self.object.event.event_type.subtype == "Pole level class" or \
            (self.object.event.event_type.subtype == "Pole practice" and \
            self.request.user.has_perm('booking.can_book_free_pole_practice')):
            context['can_be_free_class'] = True

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

        return context

    def form_valid(self, form):

        if "claim_free"in form.data:
            # if user is requesting a free class, send email to studio but
            # do not make booking yet
            ActivityLog.objects.create(
                log='Free class requested ({}) by user {}'.format(
                    form.instance.event, self.request.user.username)
            )
            try:
                # send email and set messages
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                # send email to studio
                ctx = Context({
                      'host': host,
                      'event': form.instance.event,
                      'user': self.request.user,
                      'booking_status': 'update',
                })
                send_mail('{} Request to claim free class from {} {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                        self.request.user.first_name,
                        self.request.user.last_name
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
                    self.request,
                    "Your request to claim {} as a free class has been "
                    "sent to the studio.  Your booking has been "
                    "provisionally made and your place will be secured once "
                    "your request has been approved.".format(form.instance.event)
                )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(e, __name__, "UpdateBookingView - claim free class email")
                messages.error(self.request, "An error occured, please contact "
                    "the studio for information")

        else:
            # add to active block if ticked, don't require paid to be ticked
            booking = form.save(commit=False)
            if 'block_book' in form.data:
                blocks = self.request.user.blocks.all()
                active_block = [block for block in blocks
                                if block.active_block() and
                                block.block_type.event_type ==
                                booking.event.event_type][0]
                booking.block = active_block
                booking.payment_confirmed = True
                booking.paid = True
                booking.user = self.request.user
                try:
                    booking.save()
                except BookingError:
                    return HttpResponseRedirect(
                        reverse('booking:fully_booked',
                            args=[booking.event.slug])
                    )
                booking.save()
                ActivityLog.objects.create(
                    log='Booking id {} (for {}), user {}, has been paid with block id {}'.format(
                        booking.id, booking.event, booking.user.username, booking.block.id
                    )
                )

            if booking.block:
                blocks_used = booking.block.bookings_made()
                total_blocks = booking.block.block_type.size
                # send email to user if they used block to book (paypal payment
                # sends separate emails
                host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
                ctx = Context({
                            'host': host,
                            'booking': booking,
                            'event': booking.event,
                            'date': booking.event.date.strftime('%A %d %B'),
                            'time': booking.event.date.strftime('%I:%M %p'),
                            'blocks_used':  blocks_used,
                            'total_blocks': total_blocks,
                            'ev_type':
                            'event' if booking.event.event_type.event_type == 'EV'
                            else 'class'
                        })
                send_mail('{} Block used for booking for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                    get_template('booking/email/booking_updated.txt').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [booking.user.email],
                    html_message=get_template(
                        'booking/email/booking_updated.html').render(ctx),
                    fail_silently=False)
                ActivityLog.objects.create(
                    log='Email sent to user ({}) regarding payment for '
                        'booking id {} (for {}) with block id {}'.format(
                        booking.user.email, booking.id, booking.event,
                        booking.block.id
                    )
                )
                if not booking.block.active_block():
                    messages.info(self.request,
                                  mark_safe(
                                      'You have just used the last space in your block.  '
                                      'Go to <a href="/blocks">'
                                      'Your Blocks</a> to buy a new one.'
                                  ))
                    if booking.block.block_type.size == 10:
                        try:
                            send_mail('{} {} has just used the last of 10 blocks'.format(
                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                                booking.user.username),
                                      "{} {} ({}) has just used the last of a block of 10"
                                      " and is now eligible for a free class.".format(
                                        booking.user.first_name,
                                        booking.user.last_name, booking.user.username
                                      ),
                                      settings.DEFAULT_FROM_EMAIL,
                                      [settings.DEFAULT_STUDIO_EMAIL],
                                      fail_silently=False)
                        except Exception as e:
                            # send mail to tech support with Exception
                            send_support_email(e, __name__, "CreateBookingView - notify studio of completed 10 block")

            messages.success(
                self.request, self.success_message.format(booking.event)
            )

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:bookings')


class BookingDeleteView(LoginRequiredMixin, DeleteView):
    model = Booking
    template_name = 'booking/delete_booking.html'
    success_message = 'Booking cancelled for {}'

    def get(self, request, *args, **kwargs):
        # redirect if cancellation period past
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        if not booking.event.can_cancel():
            return HttpResponseRedirect(
                reverse('booking:cancellation_period_past',
                        args=[booking.event.slug])
            )
        return super(BookingDeleteView, self).get(request, *args, **kwargs)

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

        ctx = Context({
                      'host': host,
                      'booking': booking,
                      'event': booking.event,
                      'date': booking.event.date.strftime('%A %d %B'),
                      'time': booking.event.date.strftime('%I:%M %p'),
                      })
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
                          Context({
                              'host': host,
                              'booking': booking,
                              'event': booking.event,
                              'date': booking.event.date.strftime('%A %d %B'),
                              'time': booking.event.date.strftime('%I:%M %p'),
                          })
                      ),
                settings.DEFAULT_FROM_EMAIL,
                [settings.DEFAULT_STUDIO_EMAIL],
                fail_silently=False)

        # if booking was bought with a block, remove from block and set
        # paid and payment_confirmed to False. If paid directly, we need to
        # deal with refunds manually, so leave paid as True but change
        # payment_confirmed to False
        # if class was previously a free one, remove the "free class" flag; if
        # user reopens, they need to request as free again
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
    context = {'event': event}
    return render(request, 'booking/duplicate_booking.html', context)

def update_booking_cancelled(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    ev_type = 'class' if booking.event.event_type.event_type == 'CL' else 'event'
    context = {'booking': booking, 'ev_type': ev_type}
    if booking.event.spaces_left() == 0:
        context['full'] = True
    return render(request, 'booking/update_booking_cancelled.html', context)

def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    ev_type = 'class' if event.event_type.event_type == 'CL' else 'event'
    context = {'event': event, 'ev_type': ev_type}
    return render(request, 'booking/fully_booked.html', context)


def has_active_block(request):
    return render(request, 'booking/has_active_block.html')


def cancellation_period_past(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/cancellation_period_past.html', context)


def permission_denied(request):
    return render(request, 'booking/permission_denied.html')
