import logging

from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.utils import timezone
from braces.views import LoginRequiredMixin

from booking.models import Event, WaitingListUser
from booking.forms import EventFilter, LessonFilter
import booking.context_helpers as context_helpers

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





