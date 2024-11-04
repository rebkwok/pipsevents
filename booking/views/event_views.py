from datetime import datetime, timedelta

import logging

from django.core.paginator import Paginator
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import (
    ListView, DetailView
)
from django.utils import timezone
from braces.views import LoginRequiredMixin

from accounts.models import has_active_disclaimer, has_expired_disclaimer
from booking.models import Booking, Event, WaitingListUser
from booking.forms import EventFilter, LessonFilter, RoomHireFilter, OnlineTutorialFilter
import booking.context_helpers as context_helpers
from booking.views.views_utils import DataPolicyAgreementRequiredMixin

logger = logging.getLogger(__name__)


class EventListView(DataPolicyAgreementRequiredMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'booking/events.html'

    event_data_by_ev_type = {
        "events": {"abbr": "EV", "form_class": EventFilter},
        "lessons": {"abbr": "CL", "form_class": LessonFilter},
        "online_tutorials": {"abbr": "OT", "form_class": OnlineTutorialFilter},
        "room_hires": {"abbr": "RH", "form_class": RoomHireFilter},
    }

    def __init__(self):
        super().__init__()
        self._queryset = None

    def get_filter_form_initial(self):
        name = self.request.GET.get('name', '')
        date_selection = self.request.GET.get('date_selection', '')
        spaces_only = self.request.GET.get('spaces_only')
        if spaces_only and spaces_only.lower() in ["true", "on", "1"]:
            spaces_only = True
        return name, date_selection, spaces_only

    def get_queryset(self):
        if self._queryset is None:
            ev_abbr = self.event_data_by_ev_type[self.kwargs["ev_type"]]["abbr"]
            name, date_selection, spaces_only = self.get_filter_form_initial()
            cutoff_time = timezone.now() - timedelta(minutes=10)

            events = Event.objects.select_related('event_type').filter(
                visible_on_site=True,
                event_type__event_type=ev_abbr,
                date__gte=cutoff_time,
                cancelled=False
            ).order_by('date')

            if name and name not in ['', 'all']:
                if ev_abbr == "CL":
                    events = events.filter(categories__category=name)
                else:
                    events = events.filter(name=name)

            if date_selection:
                date_selection = date_selection.split(",")
                selected_dates = []
                for datestring in date_selection:
                    try:
                        selected_dates.append(datetime.strptime(datestring.strip(), "%d-%b-%Y").date())
                    except ValueError:
                        pass
                events = events.filter(date__date__in=selected_dates)

            if spaces_only:
                if self.request.user.is_anonymous:
                    event_ids = [
                        event.id for event in events if event.spaces_left > 0
                    ]
                else:
                    event_ids = [
                        event.id for event in events
                        if (
                            # show if there are spaces
                            event.spaces_left > 0
                            # or if the user has an open booking
                            or event.bookings.filter(user=self.request.user, status='OPEN', no_show=False).exists())
                    ]
                events = events.filter(id__in=event_ids)
            self._queryset = events
        return self._queryset

    def get_context_data(self, **kwargs):
        all_events = self.get_queryset()

        # Call the base implementation first to get a context
        context = super(EventListView, self).get_context_data(**kwargs)

        if not self.request.user.is_anonymous:
            # Add in the booked_events
            user_bookings = self.request.user.bookings.filter(event__id__in=all_events)
            user_booking_dict = {booking.event.id: booking for booking in user_bookings}
            booked_events = user_bookings.filter(status='OPEN', no_show=False).values_list('event__id', flat=True)
            auto_cancelled_events = user_bookings.filter(status='CANCELLED', auto_cancelled=True).values_list('event__id', flat=True)
            waiting_list_events = self.request.user.waitinglists.filter(event__in=all_events).values_list('event__id', flat=True)
            context['user_bookings'] = user_booking_dict
            context['booked_events'] = booked_events
            context['auto_cancelled_events'] = auto_cancelled_events
            context['waiting_list_events'] = waiting_list_events
        context['events_exist'] = all_events.exists()
        context['ev_type_for_url'] = self.kwargs['ev_type']

        event_name, date_selection, spaces_only = self.get_filter_form_initial()
        form_class = self.event_data_by_ev_type[self.kwargs["ev_type"]]["form_class"]
        form = form_class(
            initial={'name': event_name, "date_selection": date_selection, "spaces_only": spaces_only}
        )
        context['form'] = form

        if not self.request.user.is_anonymous:
            context['disclaimer'] = has_active_disclaimer(self.request.user)
            context['expired_disclaimer'] = has_expired_disclaimer(
                self.request.user
            )

        # NOTE: Tabbed querysets not currently used
        # paginate each queryset
        # tab = self.request.GET.get('tab', 0)

        # try:
        #     tab = int(tab)
        # except ValueError:  # value error if tab is not an integer, default to 0
        #     tab = 0

        # context['tab'] = str(tab)

        # if not tab or tab == 0:
        #     page = self.request.GET.get('page', 1)
        # else:
        #     page = 1
        page = self.request.GET.get('page', 1)
        all_paginator = Paginator(all_events, 30)

        queryset = all_paginator.get_page(page)
        location_events = [{
            'index': 0,
            'queryset': queryset,
            'location': 'All locations',
            'paginator_range': queryset.paginator.get_elided_page_range(queryset.number)
        }]
        # NOTE: this is unnecessary since we only have one location; leaving it in in case there is ever another studio to add
        # for i, location in enumerate([lc[0] for lc in Event.LOCATION_CHOICES], 1):
        #     location_qs = all_events.filter(location=location)
        #     if location_qs:
        #         # Don't add the location tab if there are no events to display
        #         location_paginator = Paginator(location_qs, 30)
        #         if tab and tab == i:
        #             page = self.request.GET.get('page', 1)
        #         else:
        #             page = 1
        #         queryset = location_paginator.get_page(page)
        #
        #         location_obj = {
        #             'index': i,
        #             'queryset': queryset,
        #             'location': location
        #         }
        #         location_events.append(location_obj)
        context['location_events'] = location_events

        return context


class EventDetailView(DetailView):

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
        queryset = Event.objects.filter(visible_on_site=True, event_type__event_type=ev_abbr)

        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data()
        event = self.object
        return context_helpers.get_event_context(
            context, event, self.request.user
        )


class OnlineTutorialListView(EventListView):
    model = Event
    template_name = 'booking/online_tutorials.html'

    def get_queryset(self):
        name = self.request.GET.get('name')
        events = Event.objects.select_related('event_type').filter(
            event_type__event_type="OT",
            date__gte=timezone.now(),
            cancelled=False,
            visible_on_site=True,
        ).order_by('date')

        if name and name not in ['', 'all']:
            events = events.filter(name=name)
        return events


class OnlineTutorialDetailView(EventDetailView):
    model = Event
    context_object_name = 'tutorial'
    template_name = 'booking/tutorial.html'

    def get_object(self):
        queryset = Event.objects.filter(event_type__event_type="OT", visible_on_site=True)
        return get_object_or_404(queryset, slug=self.kwargs['slug'])
