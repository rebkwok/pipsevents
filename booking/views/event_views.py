import logging

from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView
)
from django.utils import timezone
from braces.views import LoginRequiredMixin

from accounts.utils import has_active_disclaimer, has_expired_disclaimer
from booking.models import Booking, Event, WaitingListUser
from booking.forms import EventFilter, LessonFilter, RoomHireFilter
import booking.context_helpers as context_helpers


logger = logging.getLogger(__name__)


class EventListView(ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    def get_queryset(self):
        if self.kwargs['ev_type'] == 'events':
            ev_abbr = 'EV'
        elif self.kwargs['ev_type'] == 'lessons':
            ev_abbr = 'CL'
        else:
            ev_abbr = 'RH'

        name = self.request.GET.get('name')

        if name:
            return Event.objects.select_related('event_type').filter(
                event_type__event_type=ev_abbr,
                date__gte=timezone.now(),
                name=name,
                cancelled=False
            ).order_by('date')
        return Event.objects.select_related('event_type').filter(
            event_type__event_type=ev_abbr,
            date__gte=timezone.now(),
            cancelled=False
        ).order_by('date')

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)
        if not self.request.user.is_anonymous():
            # Add in the booked_events
            user_booked_events = Booking.objects.select_related()\
                .filter(user=self.request.user, status='OPEN', no_show=False)\
                .values_list('event__id', flat=True)
            booked_events = Event.objects.select_related()\
                .filter(id__in=user_booked_events).values_list('id', flat=True)
            waiting_list_events = WaitingListUser.objects\
                .filter(user=self.request.user)\
                .values_list('event__id', flat=True)
            context['booked_events'] = booked_events
            context['waiting_list_events'] = waiting_list_events
            context['is_regular_student'] = self.request.user.has_perm(
                "booking.is_regular_student"
            )
        context['type'] = self.kwargs['ev_type']

        event_name = self.request.GET.get('name', '')
        if self.kwargs['ev_type'] == 'events':
            form = EventFilter(initial={'name': event_name})
        elif self.kwargs['ev_type'] == 'lessons':
            form = LessonFilter(initial={'name': event_name})
        else:
            form = RoomHireFilter(initial={'name': event_name})
        context['form'] = form

        if not self.request.user.is_anonymous():
            context['disclaimer'] = has_active_disclaimer(self.request.user)
            context['expired_disclaimer'] = has_expired_disclaimer(
                self.request.user
            )

        return context


class EventDetailView(LoginRequiredMixin, DetailView):

    model = Event
    context_object_name = 'event'
    template_name = 'booking/event.html'

    def get_object(self):
        if self.kwargs['ev_type'] == 'event':
            ev_abbr = 'EV'
        elif self.kwargs['ev_type'] == 'lesson':
            ev_abbr = 'CL'
        else:
            ev_abbr = 'RH'
        queryset = Event.objects.filter(event_type__event_type=ev_abbr)

        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(EventDetailView, self).get_context_data()
        event = self.object
        return context_helpers.get_event_context(
            context, event, self.request.user
        )
