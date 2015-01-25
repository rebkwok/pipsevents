from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from braces.views import LoginRequiredMixin
from booking.models import Event, Booking


class EventListView(ListView):

    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        return Event.objects.filter(date__gte=timezone.now()).order_by('date')


class EventDetailView(DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(date__gte=timezone.now())
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data(**kwargs)
        # Add in the booked flag
        context['booked'] = True
        return context

class BookingListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(event__date__gte=timezone.now()).filter(user=self.request.user).order_by('event__date')


class BookingHistoryListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(event__date__lte=timezone.now()).filter(user=self.request.user).order_by('-event__date')

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
    fields = ('event',)


    def get_initial(self):
        event = get_object_or_404(Event, slug=self.kwargs.get('event_slug'))
        return {
            'event': event,
        }

    def form_valid(self, form):
        booking = form.save(commit=False)
        booking.user = self.request.user
        booking.save()
        return HttpResponseRedirect(booking.get_absolute_url())


class BookingUpdateView(LoginRequiredMixin, BookingActionMixin, UpdateView):
    model = Booking
    template_name = 'booking/update_booking.html'
    success_msg = 'Booking updated!'

    fields = ('paid',)


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
