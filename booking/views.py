from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView
)
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context

from braces.views import LoginRequiredMixin, StaffuserRequiredMixin

from paypal.standard.forms import PayPalPaymentsForm
from payments.forms import PayPalPaymentsListForm
from payments.models import PaypalBookingTransaction

from booking.models import Event, Booking, Block, BlockType
from booking.forms import (
    BookingCreateForm, BlockCreateForm, ConfirmPaymentForm)
import booking.context_helpers as context_helpers
from payments.helpers import create_booking_paypal_transaction, \
    create_block_paypal_transaction


def get_event_names(event_type):

    def callable():
        event_names = set([event.name for event in Event.objects.filter(
            Q(event_type__event_type=event_type) & Q(date__gte=timezone.now())
        ).order_by('name')])
        NAME_CHOICES = [(item, item) for i, item in enumerate(event_names)]
        NAME_CHOICES.insert(0, ('', 'All'))
        return tuple(sorted(NAME_CHOICES))

    return callable


class EventFilter(forms.Form):
    name = forms.ChoiceField(choices=get_event_names('EV'))


class EventListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        name = self.request.GET.get('name')
        if name:
            return Event.objects.filter(
                Q(event_type__event_type='EV') & Q(date__gte=timezone.now())
                & Q(name=name)).order_by('date')
        return Event.objects.filter(
            (Q(event_type__event_type='EV') & Q(date__gte=timezone.now())
        )).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
        # Add in the booked_events
            user_bookings = self.request.user.bookings.all()
            booked_events = [booking.event for booking in user_bookings
                             if not booking.status == 'CANCELLED']
            context['booked_events'] = booked_events
        context['type'] = 'events'

        event_name = self.request.GET.get('name', '')
        form = EventFilter(initial={'name': event_name})
        context['form'] = form
        return context


class EventDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(event_type__event_type='EV')

        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data()
        event = self.object
        return context_helpers.get_event_context(
            context, event, self.request.user
        )


class LessonFilter(forms.Form):
    name = forms.ChoiceField(choices=get_event_names('CL'))


class LessonListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        name = self.request.GET.get('name')
        if name:
            return Event.objects.filter(
                Q(event_type__event_type='CL') & Q(date__gte=timezone.now())
                & Q(name=name)).order_by('date')
        return Event.objects.filter(
            (Q(event_type__event_type='CL') & Q(date__gte=timezone.now())
        )).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(LessonListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
        # Add in the booked_events
            user_bookings = self.request.user.bookings.all()
            booked_events = [booking.event for booking in user_bookings
                             if not booking.status == 'CANCELLED']
            context['booked_events'] = booked_events
        context['type'] = 'lessons'

        event_name = self.request.GET.get('name', '')
        form = LessonFilter(initial={'name': event_name})
        context['form'] = form
        return context


class LessonDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(event_type__event_type='CL')

        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(LessonDetailView, self).get_context_data(**kwargs)
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
        active_block_event_types = [block.block_type.event_type for block in user_blocks
                             if block.active_block()]

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
            can_cancel = booking.event.can_cancel() and booking.status == 'OPEN'
            bookingform = {
                'booking': booking,
                'paypalform': paypal_form,
                'has_available_block': booking.event.event_type in active_block_event_types,
                'can_cancel': can_cancel}
            bookingformlist.append(bookingform)
        context['bookingformlist'] = bookingformlist
        return context


class BookingHistoryListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'


    def get_queryset(self):
        return Booking.objects.filter(
            (Q(event__date__lte=timezone.now()) | Q(status='CANCELLED')) & Q(user=self.request.user)
        ).order_by('event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingHistoryListView, self).get_context_data(**kwargs)
        # Add in the history flag
        context['history'] = True
        return context


class BookingCreateView(LoginRequiredMixin, CreateView):

    model = Booking
    template_name = 'booking/create_booking.html'
    success_message = 'You have booked for {}, {}, {}.'
    form_class = BookingCreateForm

    def dispatch(self, *args, **kwargs):
        self.event = get_object_or_404(Event, slug=kwargs['event_slug'])
        return super(BookingCreateView, self).dispatch(*args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk
        }

    def get(self, request, *args, **kwargs):
        # redirect if fully booked or already booked
        if self.event.spaces_left() == 0:
            return HttpResponseRedirect(reverse('booking:fully_booked',
                                        args=[self.event.slug]))
        try:
            booking = Booking.objects.get(
                user=self.request.user, event=self.event
            )
            if booking.status == 'CANCELLED':
                return super(BookingCreateView, self).get(request, *args, **kwargs)
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                        args=[self.event.slug]))
        except Booking.DoesNotExist:
            return super(BookingCreateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingCreateView, self).get_context_data(**kwargs)

        # find if block booking is available for this type of event
        blocktypes = [blocktype.event_type for blocktype in BlockType.objects.all()]
        blocktype_available = self.event.event_type in blocktypes
        context['blocktype_available'] = blocktype_available

        # Add in the event name
        context['event'] = self.event
        user_blocks = self.request.user.blocks.all()
        active_user_block = [block for block in user_blocks
                             if block.block_type.event_type == self.event.event_type
                             and block.active_block()]
        if active_user_block:
            context['active_user_block'] = True

        active_user_block_unpaid = [block for block in user_blocks
                             if block.block_type.event_type == self.event.event_type
                             and not block.expired
                             and not block.full
                             and not block.paid]
        if active_user_block_unpaid:
            context['active_user_block_unpaid'] = True
        return context

    def form_valid(self, form):
        booking = form.save(commit=False)
        try:
            cancelled_booking = Booking.objects.get(
                user=self.request.user, event=booking.event, status='CANCELLED')
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
        except IntegrityError:
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                                args=[self.event.slug]))

        if booking.block:
            blocks_used = booking.block.bookings_made()
            total_blocks = booking.block.block_type.size
        else:
            blocks_used = None
            total_blocks = None

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        send_mail('{} Booking for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                  get_template('booking/email/booking_received.txt').render(
                      Context({
                          'host': host,
                          'booking': booking,
                          'event': booking.event,
                          'date': booking.event.date.strftime('%A %d %B'),
                          'time': booking.event.date.strftime('%I:%M %p'),
                          'blocks_used':  blocks_used,
                          'total_blocks': total_blocks,
                          'prev_cancelled_and_direct_paid': previously_cancelled_and_direct_paid
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            fail_silently=False)
        # send email to studio
        additional_subject = ""
        if previously_cancelled_and_direct_paid:
            additional_subject = "ACTION REQUIRED!"
        send_mail('{} {} {} has just booked for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, additional_subject,
            booking.user.username, booking.event.name),
                  get_template('booking/email/to_studio_booking.txt').render(
                      Context({
                          'host': host,
                          'booking': booking,
                          'event': booking.event,
                          'date': booking.event.date.strftime('%A %d %B'),
                          'time': booking.event.date.strftime('%I:%M %p'),
                          'prev_cancelled_and_direct_paid': previously_cancelled_and_direct_paid,
                          'transaction_id': transaction_id,
                          'invoice_id': invoice_id
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_STUDIO_EMAIL],
            fail_silently=False)

        messages.success(
            self.request,
            self.success_message.format(
                booking.event.name,
                booking.event.date.strftime('%A %d %B'),
                booking.event.date.strftime('%I:%M %p')
            )
        )

        if previously_cancelled_and_direct_paid:
            messages.info(
                self.request, 'You previously paid for this booking; your '
                              'booking will remain as pending until the '
                              'organiser has reviewed your payment status.'
            )
        elif not booking.block:
            messages.info(
                self.request, 'Your place will be confirmed once your payment '
                              'has been received.'
            )
        elif not booking.block.active_block():
            messages.info(self.request,
                          'You have just used the last space in your block.  '
                          'Go to <a href="/blocks">'
                          'Your Blocks</a> to buy a new one.',
                          extra_tags='safe')

        return HttpResponseRedirect(booking.get_absolute_url())


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

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        send_mail('{} Block booking confirmed'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
                  get_template('booking/email/block_booked.txt').render(
                      Context({
                          'host': host,
                          'block': block,
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [block.user.email],
            fail_silently=False)
        # send email to studio
        send_mail('{} {} has just booked a block'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, block.user.username),
                  get_template('booking/email/to_studio_block_booked.txt').render(
                      Context({
                          'host': host,
                          'block': block,
                    })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_STUDIO_EMAIL],
            fail_silently=False)
        messages.success(self.request, self.success_message.format(block.block_type))
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
    success_message = 'Booking updated!'
    fields = ['paid']

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
            blocktypes = [blocktype.event_type for blocktype in BlockType.objects.all()]
            blocktype_available = self.event.event_type in blocktypes
            context['blocktype_available'] = blocktype_available

        #TODO redirect in get() if already paid
        #TODO cancelled may have paid=True but payment_confirmed=False;
        # paypal
        invoice_id = create_booking_paypal_transaction(
            self.request.user, self.object
        ).invoice_id
        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        paypal_form = PayPalPaymentsForm(
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
        # add to active block if ticked, don't require paid to be ticked
        booking = form.save(commit=False)
        if 'block_book' in form.data:
            blocks = self.request.user.blocks.all()
            active_block = [block for block in blocks
                            if block.active_block()][0]
            booking.block = active_block
            booking.payment_confirmed = True
        booking.paid = True
        booking.user = self.request.user
        booking.save()

        if booking.block:
            blocks_used = booking.block.bookings_made()
            total_blocks = booking.block.block_type.size
        else:
            blocks_used = None
            total_blocks = None

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        send_mail('{} Booking for {} has been updated'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                  get_template('booking/email/booking_updated.txt').render(
                      Context({
                          'host': host,
                          'booking': booking,
                          'event': booking.event,
                          'date': booking.event.date.strftime('%A %d %B'),
                          'time': booking.event.date.strftime('%I:%M %p'),
                          'blocks_used':  blocks_used,
                          'total_blocks': total_blocks,
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            fail_silently=False)
        # send email to studio
        send_mail('{} {} has just confirmed payment for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.user.username, booking.event.name),
                  get_template('booking/email/to_studio_booking_updated.txt').render(
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
        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(booking.get_absolute_url())


class BookingDeleteView(LoginRequiredMixin, DeleteView):
    model = Booking
    template_name = 'booking/delete_booking.html'
    success_message = 'Booking cancelled for {}, {}, {}'

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

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        send_mail('{} Booking for {} cancelled'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                  get_template('booking/email/booking_deleted.txt').render(
                      Context({
                          'host': host,
                          'booking': booking,
                          'event': booking.event,
                          'date': booking.event.date.strftime('%A %d %B'),
                          'time': booking.event.date.strftime('%I:%M %p'),
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            fail_silently=False)
        # send email to studio
        send_mail('{} {} has just cancelled a booking for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.user.username, booking.event.name),
                  get_template('booking/email/to_studio_booking_deleted.txt').render(
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
        if booking.block:
            booking.block = None
            booking.paid = False
        booking.status = 'CANCELLED'
        booking.payment_confirmed = False
        booking.save()

        messages.success(
            self.request,
            self.success_message.format(
                booking.event.name,
                booking.event.date.strftime('%A %d %B'),
                booking.event.date.strftime('%I:%M %p'))
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:bookings')


class BookingDetailView(LoginRequiredMixin, DetailView):
    model = Booking
    context_object_name = 'booking'
    template_name = 'booking/booking.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingDetailView, self).get_context_data(**kwargs)
        booking = self.object

        # paypal
        invoice_id = create_booking_paypal_transaction(
            self.request.user, self.object
        ).invoice_id
        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        paypal_form = PayPalPaymentsForm(
            initial=context_helpers.get_paypal_dict(
                host,
                self.object.event.cost,
                self.object.event,
                invoice_id,
                '{} {}'.format('booking', self.object.id)
            )
        )
        context["paypalform"] = paypal_form

        return context_helpers.get_booking_context(context, booking)


def duplicate_booking(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/duplicate_booking.html', context)


def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/fully_booked.html', context)


def has_active_block(request):
     return render(request, 'booking/has_active_block.html')


def cancellation_period_past(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/cancellation_period_past.html', context)


class ConfirmPaymentView(LoginRequiredMixin, UpdateView):

    model = Booking
    form_class = ConfirmPaymentForm
    template_name = 'booking/confirm_payment.html'
    success_message = 'Change to payment status confirmed.  An update email ' \
                      'has been sent to user {}.'

    def get(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(ConfirmPaymentView, self).get(request, *args, **kwargs)

    def get_initial(self):
        return {
            'paid': self.object.paid,
            'payment_confirmed': self.object.payment_confirmed
        }

    def form_valid(self, form):

        if form.has_changed():
            booking = form.save(commit=False)
            booking.paid = form.data.get('paid', False)
            booking.payment_confirmed = form.data.get('payment_confirmed', False)
            booking.date_payment_confirmed = timezone.now()
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.user.username)
            )

            #TODO send user email; list changes (form may be used to remove
            #TODO paid as well as confirm
        else:
            messages.info(
                self.request, "Saved without making changes to the payment "
                              "status for {}'s booking for {}.".format(
                    self.object.user.username, self.object.event)
            )

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('booking:lessons')


def permission_denied(request):
     return render(request, 'booking/permission_denied.html')