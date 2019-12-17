# -*- coding: utf-8 -*-
import logging

from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseBadRequest
from django.template.response import TemplateResponse
from django.template.loader import render_to_string
from django.shortcuts import HttpResponse, HttpResponseRedirect, get_object_or_404, render
from django.views.generic import CreateView, ListView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from braces.views import LoginRequiredMixin

from booking.email_helpers import send_waiting_list_email
from booking.models import Event, Booking, Block, BlockType, WaitingListUser
from booking.views.views_utils import _get_active_user_block
from studioadmin.forms import StatusFilter,  RegisterDayForm, AddRegisterBookingForm
from studioadmin.views.helpers import is_instructor_or_staff, \
    InstructorOrStaffUserMixin

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@is_instructor_or_staff
def register_view(request, event_slug):

    event = get_object_or_404(Event, slug=event_slug)
    status_choice = request.GET.get('status_choice', 'OPEN')
    if status_choice == 'ALL':
        bookings = event.bookings.all().order_by('date_booked')
    else:
        bookings = event.bookings.filter(status=status_choice).order_by('date_booked')

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    template = 'studioadmin/register.html'

    sidenav_selection = 'lessons_register'
    if event.event_type.event_type == 'EV':
        sidenav_selection = 'events_register'

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
                ).replace(tzinfo=timezone.utc),
                date__lt=datetime.combine(
                    register_date, time(hour=23, minute=59)
                ).replace(tzinfo=timezone.utc),
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
                date__gt=datetime.now().replace(hour=0, minute=0, tzinfo=timezone.utc),
                date__lt=datetime.now().replace(hour=23, minute=59, tzinfo=timezone.utc),
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
        if self.kwargs["ev_type"] == 'events':
            queryset = Event.objects.filter(event_type__event_type='EV', date__gte=today).order_by('date')
        else:
            queryset = Event.objects.filter(date__gte=today).exclude(event_type__event_type='EV').order_by('date')
        return queryset

    def get_context_data(self, **kwargs):
        context = super(EventRegisterListView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs['ev_type']
        context['sidenav_selection'] = '{}_register'.format(
            self.kwargs['ev_type'])

        page = self.request.GET.get('page', 1)
        all_paginator = Paginator(self.get_queryset(), 20)
        queryset = all_paginator.get_page(page)

        location_events = [{
            'index': 0,
            'queryset': queryset,
            'location': 'All locations'
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
            action = 'reopened'

        if not booking.block:  # reopened no-show could already have block
            active_block = _get_active_user_block(booking.user, booking)
            if booking.has_available_block:
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
@require_http_methods(['GET', 'POST'])
def ajax_assign_block(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    # Allow get for post-success call after updating paid status
    alert_msg = {}

    if request.method == 'POST':
        if booking.paid:
            if not booking.block:
                alert_msg = {
                    'status': 'error', 'msg': 'Booking is already marked as paid; uncheck "Paid" checkbox and try again.'
                }
            else:
                alert_msg = {
                    'status': 'warning', 'msg': 'Block already assigned.'
                }
        else:
            available_block = _get_active_user_block(booking.user, booking)
            if available_block:
                booking.block = available_block
                booking.paid = True
                booking.payment_confirmed = True
                booking.save()
                alert_msg = {
                        'status': 'success', 'msg': 'Block assigned.'
                    }
            else:
                alert_msg = {
                    'status': 'error',
                    'msg': 'No available block to assign.'
                }

    context = {
        'booking': booking, 'alert_msg': alert_msg,
        'available_block_type': True  # always True if we're calling this view
    }

    return render(request, 'studioadmin/includes/register_block.html', context)


@login_required
@is_instructor_or_staff
@require_http_methods(['GET', 'POST'])
def ajax_toggle_paid(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    # Allow get for post-success call after updating block status
    alert_msg = {}

    if request.method == 'POST':
        initial_state = booking.paid
        booking.paid = not initial_state
        booking.payment_confirmed = not initial_state

        if initial_state is True:

            if booking.free_class:
                booking.free_class = False

            if booking.block:
                booking.block = None
                alert_msg = {'status': 'warning', 'msg': 'Booking set to unpaid and block unassigned.'}
            else:
                alert_msg = {'status': 'success', 'msg': 'Booking set to unpaid.'}
        else:
            if booking.has_available_block:
                alert_msg = {'status': 'warning', 'msg': 'Booking set to paid. Available block NOT assigned.'}
            else:
                alert_msg = {'status': 'success', 'msg': 'Booking set to paid.'}

        booking.save()

    return JsonResponse(
        {
            'paid': booking.paid,
            'has_available_block': not booking.paid and booking.has_available_block,
            'alert_msg': alert_msg
        }
    )


@login_required
@is_instructor_or_staff
@require_http_methods(['POST'])
def ajax_toggle_attended(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    attendance = request.POST.get('attendance')
    if not attendance or attendance not in ['attended', 'no-show']:
        return HttpResponseBadRequest('No attendance data')

    alert_msg = None
    event_was_full = booking.event.spaces_left == 0
    if attendance == 'attended':
        if (booking.no_show or booking.status == 'CANCELLED') and booking.event.spaces_left == 0:
            ev_type = 'Class' if booking.event.event_type.event_type == 'CL' else 'Event'
            alert_msg = '{} is now full, cannot reopen booking.'.format(ev_type)
        else:
            booking.status = 'OPEN'
            booking.attended = True
            booking.no_show = False
    elif attendance == 'no-show':
        booking.attended = False
        booking.no_show = True
    booking.save()

    if event_was_full and attendance == 'no-show' and booking.event.date > (timezone.now() + timedelta(hours=1)):
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
    return JsonResponse({'attended': booking.attended, 'alert_msg': alert_msg})
