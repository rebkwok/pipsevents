# -*- coding: utf-8 -*-
import logging

from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.template.response import TemplateResponse
from django.template.loader import render_to_string
from django.shortcuts import HttpResponse, get_object_or_404, render
from django.views.generic import ListView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from braces.views import LoginRequiredMixin

from booking.email_helpers import send_waiting_list_email
from booking.models import Event, Booking, Block, BlockType, WaitingListUser
from studioadmin.forms import StatusFilter,  RegisterDayForm, AddRegisterBookingForm
from studioadmin.views.helpers import is_instructor_or_staff, \
    InstructorOrStaffUserMixin
from .events import EVENT_TYPE_PARAM_MAPPING
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@is_instructor_or_staff
def register_view(request, event_slug):

    event = get_object_or_404(Event, slug=event_slug)
    status_choice = request.GET.get('status_choice', 'OPEN')
    if status_choice == 'LATE_CANCELLATIONS':
        # late cancellations are no-shows not confirmed by instructor
        bookings = event.bookings.filter(
            status="OPEN", no_show=True, instructor_confirmed_no_show=False
        ).order_by('date_booked')
    elif status_choice == "CANCELLED":
        # all cancelled including late cancelled (no-show, not confirmed by instructor)
        bookings = event.bookings.filter(
            Q(status="CANCELLED") | Q(status="OPEN", no_show=True, instructor_confirmed_no_show=False)
        ).order_by('date_booked')
    elif status_choice == "NO_SHOWS":
        # real no-shows, confirmed by instructor
        bookings = event.bookings.filter(
            status="OPEN", no_show=True, instructor_confirmed_no_show=True
        ).order_by('date_booked')
    elif status_choice == "OPEN":
        # always show confirmed no-shows
        bookings = event.bookings.filter(
            Q(status="OPEN", no_show=False) | Q(instructor_confirmed_no_show=True)
        ).order_by('date_booked')
    else:
        # ALL bookings
        bookings = event.bookings.all().order_by('date_booked')

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    template = 'studioadmin/register.html'

    sidenav_selection = 'lessons_register'
    if event.event_type.event_type == 'EV':
        sidenav_selection = 'events_register'
    elif event.event_type.event_type == 'OT':
        sidenav_selection = 'online_tutorials_register'

    available_block_type = BlockType.objects.filter(event_type=event.event_type)

    return TemplateResponse(
        request, template, {
            'event': event, 'bookings': bookings, 'status_filter': status_filter,
            'can_add_more': event.spaces_left > 0,
            'status_choice': status_choice,
            'available_block_type': bool(available_block_type),
            'sidenav_selection': sidenav_selection,
        }
    )


@login_required
@is_instructor_or_staff
def register_print_day(request):
    '''
    link to print all registers for a specific day GET --> form with date selector
    POST sends selected date in querystring
    get date from querystring
    find all events for that date
    for each event, create formset as above; only for open bookings
    in template, iterate over events and create print version of register for each
    '''

    if request.method == 'POST':
        form = RegisterDayForm(request.POST)

        if form.is_valid():
            register_date = form.cleaned_data['register_date']
            register_format = form.cleaned_data['register_format']
            exclude_ext_instructors = form.cleaned_data['exclude_ext_instructor']

            events = Event.objects.filter(
                date__gt=datetime.combine(
                    register_date, time(hour=0, minute=0)
                ).replace(tzinfo=dt_timezone.utc),
                date__lt=datetime.combine(
                    register_date, time(hour=23, minute=59)
                ).replace(tzinfo=dt_timezone.utc),
            ).order_by('date')

            new_form = RegisterDayForm(
                initial={'register_date': register_date,
                         'exclude_ext_instructor': exclude_ext_instructors,
                         'register_format': register_format},
                events=events
            )
            ctx = {'form': new_form, 'sidenav_selection': 'register_day'}

            if not events:
                messages.info(request, 'There are no classes/workshops/events on the date selected')
                return TemplateResponse(
                    request, "studioadmin/register_day_form.html", ctx
                )

            if 'print' in request.POST:

                if 'select_events' in request.POST:
                    event_ids = form.cleaned_data['select_events']
                    events = Event.objects.filter(
                        id__in=event_ids
                    ).order_by('date')
                else:
                    messages.info(request, 'Please select at least one register to print')
                    form = RegisterDayForm(
                        initial={'register_date': register_date,
                                 'exclude_ext_instructor': exclude_ext_instructors,
                                 'register_format': register_format,
                                 'select_events': []},
                        events=events
                    )
                    return TemplateResponse(
                        request, "studioadmin/register_day_form.html",
                        {'form': form, 'sidenav_selection': 'register_day'}
                    )

                eventlist = []
                for event in events:
                    bookings = [
                        booking for booking in Booking.objects.filter(event=event, status='OPEN')
                        ]

                    bookinglist = []
                    for i, booking in enumerate(bookings):
                        available_block = [
                            block for block in
                            Block.objects.filter(user=booking.user) if
                            block.active_block() and
                            block.block_type.event_type == event.event_type
                        ]
                        available_block = booking.block or (
                            available_block[0] if available_block else None
                        )
                        booking_ctx = {'booking': booking, 'index': i+1, 'available_block': available_block}
                        bookinglist.append(booking_ctx)

                    if event.max_participants:
                        extra_lines = event.spaces_left
                    elif event.bookings.count() < 15:
                        open_bookings = [
                            event for event in event.bookings.all() if event.status == 'OPEN'
                        ]
                        extra_lines = 15 - len(open_bookings)
                    else:
                        extra_lines = 2

                    available_block_type = [
                        block_type for block_type in
                        BlockType.objects.filter(event_type=event.event_type)
                    ]

                    event_ctx = {
                        'event': event,
                        'bookings': bookinglist,
                        'available_block_type': available_block_type,
                        'extra_lines': extra_lines,
                    }
                    eventlist.append(event_ctx)

                context = {
                    'date': register_date, 'events': eventlist,
                    'sidenav_selection': 'register_day',
                    'register_format': register_format
                }
                template = 'studioadmin/print_multiple_registers.html'
                return TemplateResponse(request, template, context)

            else:
                return TemplateResponse(
                    request, "studioadmin/register_day_form.html", ctx
                )

        else:

            messages.error(
                request,
                mark_safe('Please correct the following errors: {}'.format(
                    form.errors
                ))
            )
            return TemplateResponse(
                    request, "studioadmin/register_day_form.html",
                    {'form': form, 'sidenav_selection': 'register_day'}
                    )

    events = Event.objects.filter(
                date__gt=datetime.now().replace(hour=0, minute=0, tzinfo=dt_timezone.utc),
                date__lt=datetime.now().replace(hour=23, minute=59, tzinfo=dt_timezone.utc),
            ).order_by('date')
    form = RegisterDayForm(events=events)

    return TemplateResponse(
        request, "studioadmin/register_day_form.html",
        {'form': form, 'sidenav_selection': 'register_day'}
    )


class EventRegisterListView(
    LoginRequiredMixin, InstructorOrStaffUserMixin, ListView
):

    model = Event
    template_name = 'studioadmin/events_register_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        today = timezone.now().replace(hour=0, minute=0)
        event_type = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["abbr"]
        if event_type == "CL":
            queryset = Event.objects.filter(event_type__event_type__in=["CL", "RH"], date__gte=today, cancelled=False).order_by('date')
        else:
            queryset = Event.objects.filter(event_type__event_type=event_type, date__gte=today, cancelled=False).order_by('date')
        return queryset

    def get_context_data(self, **kwargs):
        context = super(EventRegisterListView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs['ev_type']
        context['sidenav_selection'] = '{}_register'.format(EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["sidenav_plural"])

        page = self.request.GET.get('page', 1)
        all_paginator = Paginator(self.get_queryset(), 20)
        queryset = all_paginator.get_page(page)

        location_events = [{
            'index': 0,
            'queryset': queryset,
            'location': 'All locations',
            'paginator_range': queryset.paginator.get_elided_page_range(queryset.number)
        }]
        # TODO: NOTE: this is unnecessary since we only have one location; leaving it in in case there is ever another studio to add
        # TODO: If we do add it, the pagination will need to be updated too (see bookings event list view)
        # for i, location in enumerate(
        #         [lc[0] for lc in Event.LOCATION_CHOICES], 1
        # ):
        #     location_obj = {
        #         'index': i,
        #         'queryset': self.get_queryset().filter(location=location),
        #         'location': location
        #     }
        #     if location_obj['queryset']:
        #         location_events.append(location_obj)
        context['location_events'] = location_events

        return context


@login_required
@is_instructor_or_staff
def booking_register_add_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'GET':
        form = AddRegisterBookingForm(event=event)

    else:
        form = AddRegisterBookingForm(request.POST, event=event)
        if event.spaces_left > 0:
            if form.is_valid():
                process_event_booking_updates(form, event, request)
                return HttpResponse(
                    render_to_string(
                        'studioadmin/includes/register-booking-add-success.html'
                    )
                )
        else:
            ev_type = 'Class' if event.event_type.event_type == 'CL' else 'Event'
            form.add_error(
                '__all__',
                '{} is now full, booking could not be created. '
                'Please close this window and refresh register page.'.format(ev_type)
            )

    context = {'form_event': event, 'form': form}
    return TemplateResponse(
        request, 'studioadmin/includes/register-booking-add-modal.html', context
    )


def process_event_booking_updates(form, event, request):
        extra_msg = ''
        user_id = int(form.cleaned_data['user'])
        booking, created = Booking.objects.get_or_create(user_id=user_id, event=event)
        if created:
            action = 'created'
        elif booking.status == 'OPEN' and not booking.no_show:
            messages.info(request, 'Open booking for this user already exists')
            return
        else:
            booking.status = 'OPEN'
            booking.no_show = False
            booking.instructor_confirmed_no_show = False
            action = 'reopened'

        if not booking.block:  # reopened no-show could already have block
            active_block = booking.get_next_active_block()
            if active_block is not None:
                booking.block = active_block
                booking.paid = True
                booking.payment_confirmed = True

        if booking.block:  # check after assignment
            extra_msg = "Available block assigned."

        booking.save()

        messages.success(
            request,
            'Booking for {} has been {}. {}'.format(booking.event,  action, extra_msg)
        )

        ActivityLog.objects.create(
            log='Booking id {} (user {}) for "{}" {} by admin user {}. {}'.format(
                booking.id,  booking.user.username,  booking.event,
                action,  request.user.username, extra_msg
            )
        )

        try:
            waiting_list_user = WaitingListUser.objects.get(
                user=booking.user,  event=booking.event
            )
            waiting_list_user.delete()
            ActivityLog.objects.create(
                log='User {} has been removed from the waiting list for {}'.format(
                    booking.user.username,  booking.event
                )
            )
        except WaitingListUser.DoesNotExist:
            pass


@login_required
@is_instructor_or_staff
@require_http_methods(['POST'])
def ajax_toggle_attended(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    attendance = request.POST.get('attendance')
    if not attendance or attendance not in ['attended', 'no-show']:
        return HttpResponseBadRequest('No attendance data')

    alert_msg = None
    if attendance == 'attended':
        if booking.attended:
            # booking was already attended and clicked attended again; reset status
            booking.attended = False
            attendance = "unset"
        elif (booking.no_show or booking.status == 'CANCELLED') and booking.event.spaces_left == 0:
            ev_type = 'Class' if booking.event.event_type.event_type == 'CL' else 'Event'
            alert_msg = '{} is now full, cannot reopen booking.'.format(ev_type)
        else:
            booking.status = 'OPEN'
            booking.attended = True
            booking.no_show = False
            booking.instructor_confirmed_no_show = False
    elif attendance == 'no-show':
        if booking.no_show:
            # booking was already no-show and clicked no-show again; reset status
            booking.no_show = False
            booking.instructor_confirmed_no_show = False
            attendance = "unset"
        else:
            booking.attended = False
            booking.no_show = True
            if abs(booking.event.date - timezone.now()) < timedelta(seconds=60*60):
                # only mark as instructor-no-shows if within an hour of the event time
                booking.instructor_confirmed_no_show = True
    booking.save()

    if attendance == "unset":
        action = "unset"
    elif attendance == "no-show" and not booking.instructor_confirmed_no_show:
        action = "late cancellation"
    else:
        action = attendance
    
    if attendance != "unset":
        ActivityLog.objects.create(
            log=f'User {booking.user.username} marked as {action} for {booking.event} '
            f'by admin user {request.user.username}'
        )

        if attendance == 'no-show' and booking.event.date > (timezone.now() + timedelta(hours=1)):
            # Only send waiting list emails if marking booking as no-show more than 1 hr before the event start
            waiting_list_users = WaitingListUser.objects.filter(event=booking.event)
            if waiting_list_users:
                send_waiting_list_email(
                    booking.event,
                    [wluser.user for wluser in waiting_list_users],
                    host='http://{}'.format(request.META.get('HTTP_HOST'))
                )
                ActivityLog.objects.create(
                    log='Waiting list email sent to user(s) {} for event {}'.format(
                        ',  '.join([wluser.user.username for wluser in waiting_list_users]),
                        booking.event
                    )
                )

    if booking.instructor_confirmed_no_show:
        status_text = "No-show"
    elif booking.no_show:
        status_text = "Late cancellation"
    else:
        status_text = booking.status.title()

    return JsonResponse(
        {'attended': booking.attended, 'unset': action == "unset", 'status_text': status_text, 'alert_msg': alert_msg})
