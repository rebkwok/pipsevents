from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from braces.views import LoginRequiredMixin
from booking.models import Event, Booking
from booking.forms import BookingUpdateForm, BookingCreateForm
import booking.context_helpers as context_helpers

class EventListView(ListView):

    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        return Event.objects.filter(date__gte=timezone.now()).order_by('date')


class EventDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(date__gte=timezone.now())
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data(**kwargs)
        event = self.object
        return context_helpers.get_event_context(context, event, self.request.user)


class BookingListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(
            event__date__gte=timezone.now(),
            user=self.request.user).order_by('event__date'
        )


class BookingHistoryListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'


    def get_queryset(self):
        return Booking.objects.filter(
            event__date__lte=timezone.now(),
            user=self.request.user).order_by('-event__date'
        )

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

def duplicate_booking(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/duplicate_booking.html', context)


def fully_booked(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    context = {'event': event}
    return render(request, 'booking/fully_booked.html', context)