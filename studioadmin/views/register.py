# -*- coding: utf-8 -*-
import logging

from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.template.loader import render_to_string
from django.shortcuts import HttpResponse, HttpResponseRedirect, get_object_or_404, render
from django.views.generic import CreateView, ListView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods

from braces.views import LoginRequiredMixin

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.models import Event, Booking, Block, BlockType, WaitingListUser
from booking.views.views_utils import _get_active_user_block
from payments.models import PaypalBookingTransaction
from studioadmin.forms import SimpleBookingRegisterFormSet, StatusFilter, \
    RegisterDayForm, AddRegisterBookingForm
from studioadmin.views.helpers import is_instructor_or_staff, \
    InstructorOrStaffUserMixin

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@is_instructor_or_staff
def register_view(request, event_slug, status_choice='OPEN', print_view=False):
    event = get_object_or_404(Event, slug=event_slug)

    if request.method == 'POST':

        if request.POST.get("print"):
            print_view = True

        status_choice = request.POST.getlist('status_choice')[0]

        formset = SimpleBookingRegisterFormSet(
            request.POST,
            instance=event,
        )
        if formset.is_valid():
            if not formset.has_changed() and \
                    request.POST.get('formset_submitted'):
                messages.info(request, "No changes were made")
            else:
                attended_checked = []
                attended_unchecked = []
                no_show_checked = []
                no_show_unchecked = []
                deposit_updates = {}
                paid_updates = {}
                # for messages; show separate message if booking created or
                # reopened; show combined message for other updates; show
                # additional payment info in log (but not messages)
                updated = []

                for form in formset:
                    booking = form.save(commit=False)

                    if form.has_changed():
                        if 'attended' in form.changed_data:
                            attended_checked.append(booking.user.username) \
                                if booking.attended \
                                else attended_unchecked.append(booking.user.username)
                        if 'no_show' in form.changed_data:
                            no_show_checked.append(booking.user.username) \
                                if booking.no_show \
                                else no_show_unchecked.append(booking.user.username)
                        # new booking
                        if 'user' in form.changed_data:

                            try:
                                new_booking = Booking.objects\
                                    .select_related('event', 'user').get(
                                        user=booking.user, event=booking.event,
                                        status='CANCELLED'
                                    )
                                new = False
                            except Booking.DoesNotExist:
                                new = True
                                booking.save()

                            if new:
                                ActivityLog.objects.create(
                                    log='(Register) Booking id {} for event '
                                        '{}, user {} created by admin '
                                        'user {} '.format(
                                        booking.id, booking.event,
                                        booking.user.username,
                                        request.user.username
                                    )
                                )
                                messages.success(
                                    request,
                                    "Booking created for user {}".format(
                                        booking.user.username
                                    )
                                )
                            else:
                                new_booking.status = 'OPEN'
                                new_booking.attended = booking.attended
                                new_booking.save()

                                ActivityLog.objects.create(
                                    log='(Register) Cancelled booking id {} '
                                        'for event {}, user {} reopened by '
                                        'admin user {}'.format(
                                        new_booking.id, new_booking.event,
                                        new_booking.user.username,
                                        request.user.username
                                    )
                                )
                                messages.success(
                                    request,
                                    "Cancelled booking reopened for user "
                                    "{}".format(
                                        booking.user.username
                                    )
                                )

                        elif 'block' in form.changed_data:
                            booking.paid = bool(booking.block)
                            booking.payment_confirmed = bool(booking.block)
                            booking.save()

                            ActivityLog.objects.create(
                                log='(Register) Block {} for booking id {} for '
                                    'event {}, user {} by admin user {}'.format(
                                    'added' if booking.block else 'removed',
                                    booking.id, booking.event,
                                    booking.user.username,
                                    request.user.username
                                )
                            )
                            updated.append(booking)

                        else:
                            # add to updated list if something more than just
                            # attended checkbox has changed
                            booking.save()
                            if form.changed_data != ['attended']:
                                updated.append(booking)

                            # activity logs for changed to payment status
                            if 'deposit_paid' in form.changed_data:
                                change = 'yes' if booking.deposit_paid else 'no'
                                deposit_updates[booking.user.username] = change

                            if 'paid' in form.changed_data:
                                if booking.paid:
                                    change = 'yes'
                                    booking.payment_confirmed = True
                                    booking.save()
                                else:
                                    change = 'no'
                                paid_updates[booking.user.username] = change

                if deposit_updates:
                    ActivityLog.objects.create(
                        log='(Register) Deposit paid updated for user{} {} for '
                            'event {} by admin user {}'.format(
                                's' if len(deposit_updates) > 1 else '',
                                ', '.join(
                                    ['{} ({})'.format(k, v)
                                     for k, v in deposit_updates.items()]
                                ),
                                booking.event,
                                request.user.username
                            )
                        )

                if paid_updates:
                    ActivityLog.objects.create(
                        log='(Register) Fully paid updated for user{} {} for '
                            'event {} by admin user {}'.format(
                                's' if len(paid_updates) > 1 else '',
                                ', '.join(
                                    ['{} ({})'.format(k, v)
                                     for k, v in paid_updates.items()]
                                ),
                                booking.event,
                                request.user.username
                            )
                        )

                if updated:
                    messages.success(
                        request,
                        "Booking updated for user{} {}".format(
                            's' if len(updated) > 1 else '',
                            ', '.join([bk.user.username for bk in updated])
                        )
                    )
                if attended_checked:
                    messages.success(
                        request,
                        "Booking changed to attended for user{} {}".format(
                            's' if len(attended_checked) > 1 else '',
                            ', '.join(attended_checked)
                        )
                    )
                    ActivityLog.objects.create(
                        log="(Register) User{} {} marked as attended for "
                            "event {} by admin user {}".format(
                            's' if len(attended_checked) > 1 else '',
                            ', '.join(attended_checked),
                            booking.event, request.user.username
                        )
                    )

                if attended_unchecked:
                    messages.success(
                        request,
                        "Booking changed to unattended for user{} {}".format(
                            's' if len(attended_unchecked) > 1 else '',
                            ', '.join(attended_unchecked)
                        )
                    )
                    ActivityLog.objects.create(
                        log="(Register) User{} {} marked as unattended for "
                            "event {} by admin user {}".format(
                            's' if len(attended_unchecked) > 1 else '',
                            ', '.join(attended_unchecked),
                            booking.event, request.user.username
                        )
                    )
                if no_show_checked:
                    messages.success(
                        request,
                        "Booking changed to 'no-show' for user{} {}".format(
                            's' if len(no_show_checked) > 1 else '',
                            ', '.join(no_show_checked)
                        )
                    )
                    ActivityLog.objects.create(
                        log="(Register) User{} {} marked as no-show for event "
                            "{} by admin user {}".format(
                            's' if len(no_show_checked) > 1 else '',
                            ', '.join(no_show_checked),
                            booking.event, request.user.username
                        )
                    )

                if no_show_unchecked:
                    messages.success(
                        request,
                        "Booking changed to not no-show for user{} {}".format(
                            's' if len(no_show_unchecked) > 1 else '',
                            ', '.join(no_show_unchecked)
                        )
                    )
                    ActivityLog.objects.create(
                        log="(Register) User{} {} unmarked as no-show for "
                            "event {} by admin user {}".format(
                            's' if len(no_show_unchecked) > 1 else '',
                            ', '.join(no_show_unchecked),
                            booking.event, request.user.username
                        )
                    )

            register_url = 'studioadmin:event_register_old'
            if print_view:
                register_url = 'studioadmin:event_register_print'

            return HttpResponseRedirect(
                reverse(register_url,
                        kwargs={'event_slug': event.slug,
                                'status_choice': status_choice}
                        )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "Please correct the following errors:{}{}".format(
                        ''.join(["{}".format(error) for error in formset.errors]),
                        ''.join(["{}".format(err)
                                 for err in formset.non_form_errors()])
                    )
                )
            )

    else:
        if status_choice == 'ALL':
            queryset = Booking.objects\
                .select_related('event', 'user', 'event__event_type').all()
        else:
            queryset = Booking.objects\
                .select_related('event', 'user', 'event__event_type')\
                .filter(status=status_choice)

        formset = SimpleBookingRegisterFormSet(
            instance=event,
            queryset=queryset
        )

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    if status_choice == 'CANCELLED':
        extra_lines = 0
    elif event.max_participants:
        extra_lines = event.spaces_left
    elif event.bookings.count() < 15:
        open_bookings = Booking.objects.filter(
            event=event, status='OPEN', no_show=False
        )
        extra_lines = 15 - open_bookings.count()
    else:
        extra_lines = 2

    template = 'studioadmin/register.html'
    if print_view:
        template = 'studioadmin/register_print.html'

    sidenav_selection = 'lessons_register'
    if event.event_type.event_type == 'EV':
        sidenav_selection = 'events_register'

    available_block_type = BlockType.objects.filter(event_type=event.event_type)
    users_with_online_disclaimers = OnlineDisclaimer.objects.filter(
        user__in=Booking.objects.filter(event=event).values_list('user__id', flat=True)
    ).values_list('user__id', flat=True)
    users_with_print_disclaimers = PrintDisclaimer.objects.filter(
        user__in=Booking.objects.filter(event=event).values_list('user__id', flat=True)
    ).values_list('user__id', flat=True)

    bookings_paid_by_paypal = PaypalBookingTransaction.objects.filter(
        booking__event=event, transaction_id__isnull=False
    ).values_list('booking__id', flat=True)

    return TemplateResponse(
        request, template, {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines, 'print': print_view,
            'status_choice': status_choice,
            'available_block_type': bool(available_block_type),
            'sidenav_selection': sidenav_selection,
            'users_with_online_disclaimers': users_with_online_disclaimers,
            'users_with_print_disclaimers': users_with_print_disclaimers,
            'bookings_paid_by_paypal': bookings_paid_by_paypal,
        }
    )


@login_required
@is_instructor_or_staff
def register_view_new(request, event_slug):
    event = get_object_or_404(Event, slug=event_slug)
    status_choice = request.GET.get('status_choice', 'OPEN')
    if status_choice == 'ALL':
        bookings = event.bookings.all()
    else:
        bookings = event.bookings.filter(status=status_choice)

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    template = 'studioadmin/register_new.html'

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
        if self.kwargs["ev_type"] == 'events':
            queryset = Event.objects.filter(
                event_type__event_type='EV',
                date__gte=timezone.now() - timedelta(hours=1)
            ).order_by('date')
        else:
            queryset = Event.objects.filter(
                date__gte=timezone.now() - timedelta(hours=1)
            ).exclude(event_type__event_type='EV').order_by('date')
        return queryset

    def get_context_data(self, **kwargs):
        context = super(EventRegisterListView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs['ev_type']
        context['sidenav_selection'] = '{}_register'.format(
            self.kwargs['ev_type'])

        location_events = [{
            'index': 0,
            'queryset': self.get_queryset(),
            'location': 'All locations'
        }]
        for i, location in enumerate(
                [lc[0] for lc in Event.LOCATION_CHOICES], 1
        ):
            location_obj = {
                'index': i,
                'queryset': self.get_queryset().filter(location=location),
                'location': location
            }
            if location_obj['queryset']:
                location_events.append(location_obj)
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
    if form.is_valid():
        if form.has_changed():
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
                if active_block:
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

    else:
        messages.info(request, 'No changes made')


@login_required
@is_instructor_or_staff
def ajax_assign_block(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    # Allow get for post-success call after updating block status
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
            booking.block = available_block
            booking.paid = True
            booking.payment_confirmed = True
            booking.save()
            alert_msg = {
                    'status': 'success', 'msg': 'Block assigned.'
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
        booking.paid = not booking.paid
        booking.payment_confirmed = not booking.paid

        if initial_state is True:
            if booking.block:
                booking.block = None
                alert_msg = {'status': 'warning', 'msg': 'Booking set to unpaid and block unassigned.'}
            else:
                alert_msg = {'status': 'success', 'msg': 'Booking set to unpaid.'}
        else:
            has_available_block = _get_active_user_block(booking.user, booking)
            if has_available_block:
                alert_msg = {'status': 'warning', 'msg': 'Booking set to paid.  Availale block NOT assigned.'}
            else:
                alert_msg = {'status': 'success', 'msg': 'Booking set to paid.'}

        booking.save()

    return JsonResponse({'paid': booking.paid, 'alert_msg': alert_msg})


@login_required
@is_instructor_or_staff
@require_http_methods(['POST'])
def ajax_toggle_attended(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    attendance = request.POST['attendance']

    alert_msg = None
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

    return JsonResponse({'attended': booking.attended, 'alert_msg': alert_msg})
