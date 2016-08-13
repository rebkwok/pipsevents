# -*- coding: utf-8 -*-
import logging

from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.views.generic import ListView
from django.utils import timezone
from django.utils.safestring import mark_safe

from braces.views import LoginRequiredMixin

from accounts.models import OnlineDisclaimer, PrintDisclaimer
from booking.models import Event, Booking, Block, BlockType
from payments.models import PaypalBookingTransaction
from studioadmin.forms import SimpleBookingRegisterFormSet, StatusFilter, \
    RegisterDayForm
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

            register_url = 'studioadmin:event_register'
            if event.event_type.event_type == 'CL':
                register_url = 'studioadmin:class_register'
            if print_view:
                register_url = register_url + '_print'

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

            if not request.user.is_staff:
                events = events.exclude(event_type__event_type='EV')

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
    if not request.user.is_staff:
        events = events.exclude(event_type__event_type='EV')
    form = RegisterDayForm(events=events, initial={'exclude_ext_instructor': True})

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

    def get(self, request, *args, **kwargs):
        if not request.user.is_staff \
                and self.kwargs['ev_type'] == 'events':
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(EventRegisterListView, self).get(request, *args, **kwargs)

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
        return context
