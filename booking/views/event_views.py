import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
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

        if name and name not in ['', 'all']:
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
        all_events = self.get_queryset()

        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)

        if not self.request.user.is_anonymous:
            # Add in the booked_events
            booked_events = Booking.objects.select_related('event', 'user')\
                .filter(event__in=all_events, user=self.request.user, status='OPEN', no_show=False)\
                .values_list('event__id', flat=True)
            auto_cancelled_events = Booking.objects.select_related('event', 'user') \
                .filter(
                    event__in=all_events, user=self.request.user, status='CANCELLED',
                    auto_cancelled=True
                ) \
                .values_list('event__id', flat=True)
            waiting_list_events = WaitingListUser.objects\
                .select_related('event', 'user')\
                .filter(event__in=all_events, user=self.request.user)\
                .values_list('event__id', flat=True)
            context['booked_events'] = booked_events
            context['auto_cancelled_events'] = auto_cancelled_events
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

        if not self.request.user.is_anonymous:
            context['disclaimer'] = has_active_disclaimer(self.request.user)
            context['expired_disclaimer'] = has_expired_disclaimer(
                self.request.user
            )

        # paginate each queryset
        tab = self.request.GET.get('tab', 0)
        context['tab'] = tab

        if not tab or tab == '0':
            page = self.request.GET.get('page', 1)
        else:
            page = 1
        all_paginator = Paginator(all_events, 30)

        queryset = all_paginator.get_page(page)

        location_events = [{
            'index': 0,
            'queryset': queryset,
            'location': 'All locations'
        }]
        for i, location in enumerate([lc[0] for lc in Event.LOCATION_CHOICES], 1):
            location_qs = all_events.filter(location=location)
            location_paginator = Paginator(location_qs, 30)
            if tab and int(tab) == i:
                page = self.request.GET.get('page', 1)
            else:
                page = 1
            queryset = location_paginator.get_page(page)

            location_obj = {
                'index': i,
                'queryset': queryset,
                'location': location
            }
            location_events.append(location_obj)
        context['location_events'] = location_events

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
