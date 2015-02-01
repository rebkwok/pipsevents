from django.contrib import messages
from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template import Context
from braces.views import LoginRequiredMixin
from booking.models import Event, Booking
from booking.forms import BookingUpdateForm, BookingCreateForm
import booking.context_helpers as context_helpers

class EventListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        return Event.objects.filter(
            (Q(type=Event.OTHER_EVENT) | Q(type=Event.WORKSHOP)) &
            Q(date__gte=timezone.now())
        ).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
        # Add in the booked_events
            user_bookings = self.request.user.bookings.all()
            booked_events = [booking.event for booking in user_bookings]
            context['booked_events'] = booked_events
            context['type'] = 'events'
        return context


class EventDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(
            (Q(type=Event.OTHER_EVENT) | Q(type=Event.WORKSHOP)) &
            Q(date__gte=timezone.now())
        ).order_by('date')

        #TODO ?? redirect to past event page if event found but in past
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data(**kwargs)
        event = self.object
        return context_helpers.get_event_context(
            context, event, self.request.user
        )


class LessonListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        return Event.objects.filter(
            (Q(type=Event.POLE_CLASS) | Q(type=Event.OTHER_CLASS)) &
            Q(date__gte=timezone.now())
        ).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(LessonListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
        # Add in the booked_events
            user_bookings = self.request.user.bookings.all()
            booked_events = [booking.event for booking in user_bookings]
            context['booked_events'] = booked_events
            context['type'] = 'lessons'
        return context


class LessonDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(
            (Q(type=Event.POLE_CLASS) | Q(type=Event.OTHER_CLASS)) &
            Q(date__gte=timezone.now())
        ).order_by('date')

        #TODO ?? redirect to past event page if event found but in past
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
            Q(event__date__gte=timezone.now()) & Q(user=self.request.user())
        ).order_by('event__date')


class BookingHistoryListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'


    def get_queryset(self):
        return Booking.objects.filter(
            Q(event__date__lte=timezone.now()) & Q(user=self.request.user())
        ).order_by('event__date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingHistoryListView, self).get_context_data(**kwargs)
        # Add in the history flag
        context['history'] = True
        return context


class BookingActionMixin(object):

    @property
    def success_msg(self):
        return NotImplemented

    def form_valid(self, form):
        messages.info(self.request, self.success_msg)
        return super(BookingActionMixin, self).form_valid(form)


class BookingCreateView(LoginRequiredMixin, BookingActionMixin, CreateView):

    model = Booking
    template_name = 'booking/create_booking.html'
    success_msg = 'New booking confirmed!'
    form_class = BookingCreateForm

    def dispatch(self, *args, **kwargs):
        self.event = get_object_or_404(Event, slug=kwargs['event_slug'])
        return super(BookingCreateView, self).dispatch(*args, **kwargs)

    def get_initial(self):
        return {
            'event': self.event.pk,
        }

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingCreateView, self).get_context_data(**kwargs)
        # Add in the event name
        context['event_name'] = self.event.name
        return context

    def form_valid(self, form):
        # check there are spaces available
        if self.event.spaces_left() == 0:
            return HttpResponseRedirect(reverse('booking:fully_booked',
                                        args=[self.event.slug]))
        try:
            booking = form.save(commit=False)
            booking.user = self.request.user
            booking.save()

            host = 'http://' + self.request.get_host()
            # send email to user
            send_mail('{} Space for {} confirmed'.format(
                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event.name),
                      get_template('booking/email/booking_received.txt').render(
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

            return HttpResponseRedirect(booking.get_absolute_url())
        except IntegrityError:
            #trying to make a booking that already exists
            return HttpResponseRedirect(reverse('booking:duplicate_booking',
                                        args=[self.event.slug]))


class BookingUpdateView(LoginRequiredMixin, BookingActionMixin, UpdateView):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_msg = 'Booking updated!'

    form_class = BookingUpdateForm


class BookingDeleteView(LoginRequiredMixin, BookingActionMixin, DeleteView):
    model = Booking
    template_name = 'booking/delete_booking.html'
    success_msg = 'Booking deleted!'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingDeleteView, self).get_context_data(**kwargs)
        booking = get_object_or_404(Booking, pk=self.kwargs['pk'])
        event = Event.objects.get(id=booking.event.id)
        # Add in the event
        context['event'] = event
        return context

    def get_success_url(self):
        return reverse('booking:bookings')


class BookingDetailView(LoginRequiredMixin, BookingActionMixin, DetailView):
    model = Booking
    context_object_name = 'booking'
    template_name = 'booking/booking.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BookingDetailView, self).get_context_data(**kwargs)
        booking = self.object
        return context_helpers.get_booking_context(context, booking)


def duplicate_booking(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/duplicate_booking.html', context)


def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/fully_booked.html', context)