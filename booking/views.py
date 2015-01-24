from django.shortcuts import HttpResponse, render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.utils import timezone
from braces.views import LoginRequiredMixin
from booking.models import Event, Booking


class EventListView(ListView):

    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        return Event.objects.filter(date__gte=timezone.now()).order_by('-date')


class EventDetailView(DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        queryset = Event.objects.filter(date__gte=timezone.now())
        return get_object_or_404(queryset, slug=self.kwargs['slug'])


class BookingListView(LoginRequiredMixin, ListView):

    model = Booking
    context_object_name = 'bookings'
    template_name = 'booking/bookings.html'

    def get_queryset(self):
        return Booking.objects.filter(event__date__gte=timezone.now()).filter(user=self.request.user).order_by('-event__date')


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