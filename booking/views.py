from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.urlresolvers import reverse
from django.core.exceptions import ImproperlyConfigured

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context

from braces.views import LoginRequiredMixin

from paypal.standard.forms import PayPalPaymentsForm

from booking.models import Event, Booking, Block, BlockType
from booking.forms import BookingUpdateForm, BookingCreateForm, BlockCreateForm
import booking.context_helpers as context_helpers
from payments.models import create_booking_paypal_transaction, \
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
            & Q(status='OPEN')
        ).order_by('event__date')


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
    success_message = 'New booking created for {}, {}, {}'
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

        return context

    def form_valid(self, form):
        booking = form.save(commit=False)
        try:
            cancelled_booking = Booking.objects.get(
                user=self.request.user, event=booking.event, status='CANCELLED')
            booking = cancelled_booking
            booking.status = 'OPEN'
        except Booking.DoesNotExist:
            pass

        if 'block_book' in form.data:
            blocks = self.request.user.blocks.all()
            active_block = [
                block for block in blocks if block.active_block()
                and block.block_type.event_type == booking.event.event_type][0]

            booking.block = active_block
            booking.paid = True
            booking.payment_confirmed = True
        booking.user = self.request.user
        booking.save()

        if booking.block:
            blocks_used = booking.block.bookings_made()
            total_blocks = booking.block.block_type.size
            if not booking.block.active_block():
                messages.info(self.request,
                             "You have just used the last block in your block "
                             "booking. Go to 'Your Blocks' to add a new one.")
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
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [booking.user.email],
            fail_silently=False)
        # send email to studio
        send_mail('{} {} has just booked for {}'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.user.username, booking.event.name),
                  get_template('booking/email/to_studio_booking.txt').render(
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
        messages.success(
            self.request,
            self.success_message.format(
                booking.event.name,
                booking.event.date.strftime('%A %d %B'),
                booking.event.date.strftime('%I:%M %p'))
        )

        return HttpResponseRedirect(booking.get_absolute_url())


class BlockCreateView(LoginRequiredMixin, CreateView):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block booking created: {}'
    def _get_blocktypes_available_to_book(self):
        user_blocks = self.request.user.blocks.all()
        active_user_block_event_types = [block.block_type.event_type
                                         for block in user_blocks
                                         if block.active_block()]
        return BlockType.objects.exclude(
            event_type__in=active_user_block_event_types
        )

    def get(self, request, *args, **kwargs):
        # redirect if user already has active blocks for all blocktypes
        if not self._get_blocktypes_available_to_book():
            return HttpResponseRedirect(reverse('booking:has_active_block'))

        return super(BlockCreateView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockCreateView, self).get_context_data(**kwargs)
        context['form'].fields['block_type'].queryset = self._get_blocktypes_available_to_book()
        context['block_types'] = self._get_blocktypes_available_to_book()
        return context

    def form_valid(self, form):
        block_type = form.cleaned_data['block_type']
        user_blocks = self.request.user.blocks.all()
        active_user_block_event_types = [block.block_type.event_type
                                         for block in user_blocks
                                         if block.active_block()]

        if block_type.event_type in active_user_block_event_types:
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
        user_blocks = self.request.user.blocks.all()
        active_user_blocks = [block for block in user_blocks
                             if block.active_block()]
        if active_user_blocks:
            context['active_user_block'] = True

        user_block_event_types = [block.block_type.event_type for block in active_user_blocks]
        blocktypes_available_to_book = BlockType.objects.exclude(event_type__in=user_block_event_types)
        if blocktypes_available_to_book:
            context['can_book_block'] = True

        blockformlist = []
        for block in self.object_list:
            invoice_id = create_block_paypal_transaction(
                self.request.user, block).invoice_id
            paypal_form = PayPalPaymentsForm(
                initial=context_helpers.get_paypal_dict(
                    block.block_type.cost,
                    block.block_type,
                    invoice_id,
                    '{} {}'.format('block', block.id)
                )
            )
            blockform = {'block': block, 'paypalform': paypal_form}
            blockformlist.append(blockform)
        context['blockformlist'] = blockformlist

        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')


class BlockUpdateView(LoginRequiredMixin, UpdateView):
    model = Block
    template_name = 'booking/update_block.html'
    success_message = 'Block updated!'
    form_class = BookingUpdateForm

    def get_context_data(self, **kwargs):
        context = super(BlockUpdateView, self).get_context_data(**kwargs)

        # paypal
        invoice_id = create_block_paypal_transaction(
            self.request.user, self.object
        ).invoice_id
        paypal_form = PayPalPaymentsForm(
            initial=context_helpers.get_paypal_dict(
                self.object.block_type.cost,
                self.object.block_type,
                invoice_id,
                '{} {}'.format('block', self.object.id)
            )
        )
        context["paypalform"] = paypal_form
        return context

    def form_valid(self, form):
        block = form.save(commit=False)
        block.user = self.request.user
        block.paid = True
        block.save()

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        send_mail('{} Block booking updated'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
                  get_template('booking/email/block_booked.txt').render(
                      Context({
                          'host': host,
                          'block': block,
                          'updated': True,
                      })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [block.user.email],
            fail_silently=False)
        # send email to studio
        send_mail('{} {} has just confirmed payment for a block booking'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, block.user.username),
                  get_template('booking/email/to_studio_block_booked.txt').render(
                      Context({
                          'host': host,
                          'block': block,
                          'updated': True
                    })
                  ),
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_STUDIO_EMAIL],
            fail_silently=False)
        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(reverse('booking:block_list'))


class BookingUpdateView(LoginRequiredMixin, UpdateView):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_message = 'Booking updated!'
    form_class = BookingUpdateForm

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingUpdateView, self).get_context_data(**kwargs)
        user_blocks = self.request.user.blocks.all()
        active_user_block = [block for block in user_blocks
                             if block.active_block()]
        if active_user_block:
            context['active_user_block'] = True

        #TODO redirect in get() if already paid
        #TODO cancelled may have paid=True but payment_confirmed=False;
        # paypal
        invoice_id = create_booking_paypal_transaction(
            self.request.user, self.object
        ).invoice_id

        paypal_form = PayPalPaymentsForm(
            initial=context_helpers.get_paypal_dict(
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

        booking.block = None
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

        paypal_form = PayPalPaymentsForm(
            initial=context_helpers.get_paypal_dict(
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
