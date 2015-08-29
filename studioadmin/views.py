import urllib.parse
import ast
import logging

from datetime import datetime
from functools import wraps


from django.db.utils import IntegrityError
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Permission

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template.loader import get_template
from django.template import Context
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, HttpResponse, redirect, \
    render, get_object_or_404
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Event, Booking, Block, BlockType, WaitingListUser, \
    BookingError
from booking import utils
from booking.email_helpers import send_support_email, send_waiting_list_email

from timetable.models import Session
from studioadmin.forms import BookingStatusFilter, ConfirmPaymentForm, \
    EventFormSet, \
    EventAdminForm, SimpleBookingRegisterFormSet, StatusFilter, \
    TimetableSessionFormSet, SessionAdminForm, DAY_CHOICES, \
    UploadTimetableForm, EmailUsersForm, ChooseUsersFormSet, UserFilterForm, \
    BlockStatusFilter, UserBookingFormSet, UserBlockFormSet, \
    ActivityLogSearchForm

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


def staff_required(func):
    def decorator(request, *args, **kwargs):
        if request.user.is_staff:
            return func(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
    return wraps(func)(decorator)


class StaffUserMixin(object):

    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_staff:
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(StaffUserMixin, self).dispatch(request, *args, **kwargs)


class ConfirmPaymentView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_payment.html'
    success_message = 'Payment status changed to {}. An update email ' \
                      'has been sent to user {}.'
    form_class = ConfirmPaymentForm

    def get_initial(self):
        return {
            'payment_confirmed': self.object.payment_confirmed
        }

    def form_valid(self, form):
        if form.has_changed():
            booking = form.save(commit=False)

            if booking.payment_confirmed and 'payment_confirmed' \
                    in form.changed_data:
                # if user leaves paid unchecked but checks payment confirmed
                # as true, booking should be marked as paid
                booking.paid = True
                booking.date_payment_confirmed = timezone.now()

            if not booking.paid and 'paid' in form.changed_data:
                # if booking is changed to unpaid, reset payment_confirmed to
                # False too
                booking.payment_confirmed = False
            booking.save()

            if booking.paid and booking.payment_confirmed:
                payment_status = 'paid and confirmed'
            elif booking.paid:
                payment_status = "paid - payment not confirmed yet"
            else:
                payment_status = 'not paid'

            messages.success(
                self.request,
                self.success_message.format(payment_status, booking.user.username)
            )

            ctx = Context({
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST')),
                'payment_status': payment_status
            })
            try:
                send_mail(
                    '{} Payment status updated for {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                    get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [self.request.user.email],
                    html_message=get_template(
                        'studioadmin/email/confirm_payment.html').render(ctx),
                    fail_silently=False)
            except Exception as e:
                logger.error(
                        'EXCEPTION "{}"" while sending email for booking '
                        'id {}'.format(e, booking.id)
                        )

            ActivityLog(log='Payment status for booking id {} for event {}, '
                'user {} has been updated by admin user {}'.format(
                booking.id, booking.event, booking.user.username,
                self.request.user.username
                )
            )
        else:
            messages.info(
                self.request, "No changes made to the payment "
                              "status for {}'s booking for {}.".format(
                    self.object.user.username, self.object.event)
            )

        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')

class ConfirmRefundView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    model = Booking
    template_name = 'studioadmin/confirm_refunded.html'
    success_message = "Refund of payment for {}'s booking for {} has been " \
                      "confirmed.  An update email has been sent to {}."
    fields = ('id',)


    def form_valid(self, form):
        booking = form.save(commit=False)

        if 'confirmed' in self.request.POST:
            booking.paid = False
            booking.payment_confirmed = False
            booking.date_payment_confirmed = None
            booking.save()

            messages.success(
                self.request,
                self.success_message.format(booking.user.username,
                                            booking.event,
                                            booking.user.username)
            )

            ctx = Context({
                'event': booking.event,
                'host': 'http://{}'.format(self.request.META.get('HTTP_HOST'))

            })

            send_mail(
                '{} Payment refund confirmed for {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event),
                get_template('studioadmin/email/confirm_refund.txt').render(ctx),
                settings.DEFAULT_FROM_EMAIL,
                [self.request.user.email],
                html_message=get_template(
                    'studioadmin/email/confirm_refund.html').render(ctx),
                fail_silently=False)

            ActivityLog(
                log='Payment refund for booking id {} for event {}, '
                    'user {} has been updated by admin user {}'.format(
                    booking.id, booking.event, booking.user.username,
                    self.request.user.username
                )
            )

        if 'cancelled' in self.request.POST:
            messages.info(
                self.request,
                "Cancelled; no changes to payment status for {}'s booking "
                "for {}".format(booking.user.username, booking.event)
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:users')


@login_required
@staff_required
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
                for form in formset:
                    booking = form.save(commit=False)
                    if form.has_changed():
                        if booking.block:
                            booking.paid = True
                        booking.save()
                        messages.success(
                            request,
                            "Register updated for user {}".format(
                                booking.user.username
                            )
                        )
                        ActivityLog(
                            log='Booking id {} for event {}, user {} has been '
                                'updated by admin user {}'.format(
                                booking.id, booking.event,
                                booking.user.username,
                                request.user.username
                            )
                        )
                    for error in form.errors:
                        messages.error(request,mark_safe("{}".format(error)))
                formset.save()

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
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in formset.errors]
                        )
                    )
                )
            )


    else:
        if status_choice == 'ALL':
            queryset = Booking.objects.all()
        else:
            queryset = Booking.objects.filter(status=status_choice)

        formset = SimpleBookingRegisterFormSet(
            instance=event,
            queryset=queryset
        )

    status_filter = StatusFilter(initial={'status_choice': status_choice})

    if status_choice == 'CANCELLED':
        extra_lines = 0
    elif event.max_participants:
        extra_lines = event.spaces_left()
    elif event.bookings.count() < 15:
        open_bookings = [
            event for event in event.bookings.all() if event.status == 'OPEN'
        ]
        extra_lines = 15 - len(open_bookings)
    else:
        extra_lines = 2

    template = 'studioadmin/register.html'
    if print_view:
        template = 'studioadmin/register_print.html'

    sidenav_selection = 'events_register'
    if event.event_type.event_type == 'CL':
        sidenav_selection = 'lessons_register'

    available_block_type = [
        block_type for block_type in
        BlockType.objects.filter(event_type=event.event_type)
    ]

    return TemplateResponse(
        request, template, {
            'formset': formset, 'event': event, 'status_filter': status_filter,
            'extra_lines': extra_lines, 'print': print_view,
            'status_choice': status_choice,
            'available_block_type': True if available_block_type else False,
            'sidenav_selection': sidenav_selection
        }
    )


@login_required
@staff_required
def event_admin_list(request, ev_type):

    ev_type_abbreviation = 'EV' if ev_type == 'events' else 'CL'
    ev_type_text = 'event' if ev_type == 'events' else 'class'

    queryset = Event.objects.filter(
        event_type__event_type=ev_type_abbreviation,
        date__gte=timezone.now()
    ).order_by('date')
    events = True if queryset.count() > 0 else False
    show_past = False

    if request.method == 'POST':
        if "past" in request.POST:
            queryset = Event.objects.filter(
                event_type__event_type=ev_type_abbreviation,
                date__lte=timezone.now()
            ).order_by('date')
            events = True if queryset.count() > 0 else False
            show_past = True
            eventformset = EventFormSet(queryset=queryset)
        elif "upcoming" in request.POST:
            queryset = queryset
            show_past = False
            eventformset = EventFormSet(queryset=queryset)
        else:
            eventformset = EventFormSet(request.POST)

            if eventformset.is_valid():
                if not eventformset.has_changed():
                    messages.info(request, "No changes were made")
                else:
                    for form in eventformset:
                        if form.has_changed():
                            if 'DELETE' in form.changed_data:
                                messages.success(
                                    request, mark_safe(
                                        '{} <strong>{}</strong> has been deleted!'.format(
                                            ev_type_text.title(), form.instance,
                                        )
                                    )
                                )
                                ActivityLog.objects.create(
                                    log='{} {} (id {}) deleted by admin user {}'.format(
                                        ev_type_text.title(), form.instance,
                                        form.instance.id, request.user.username
                                    )
                                )
                            else:
                                for field in form.changed_data:
                                    messages.success(
                                        request, mark_safe(
                                            "<strong>{}</strong> updated for "
                                            "<strong>{}</strong>".format(
                                                field.title().replace("_", " "),
                                                form.instance))
                                    )

                                    ActivityLog.objects.create(
                                        log='{} {} (id {}) updated by admin user {}: field_changed: {}'.format(
                                            ev_type_text.title(),
                                            form.instance, form.instance.id,
                                            request.user.username, field.title().replace("_", " ")
                                        )
                                    )

                            form.save()

                        for error in form.errors:
                            messages.error(request, mark_safe("{}".format(error)))
                    eventformset.save()
                return HttpResponseRedirect(
                    reverse('studioadmin:{}'.format(ev_type),)
                )
            else:
                messages.error(
                    request,
                    mark_safe(
                        "There were errors in the following fields:\n{}".format(
                            '\n'.join(
                                ["{}".format(error) for error in eventformset.errors]
                            )
                        )
                    )
                )

    else:
        eventformset = EventFormSet(queryset=queryset)

    return render(
        request, 'studioadmin/admin_events.html', {
            'eventformset': eventformset,
            'type': ev_type,
            'events': events,
            'sidenav_selection': ev_type,
            'show_past': show_past,
            }
    )


class EventRegisterListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Event
    template_name = 'studioadmin/events_register_list.html'
    context_object_name = 'events'

    def get_queryset(self):
        ev_type_abbreviation = 'EV' if self.kwargs["ev_type"] == 'events' \
            else 'CL'

        return Event.objects.filter(
            event_type__event_type=ev_type_abbreviation,
            date__gte=timezone.now()
        ).order_by('date')

    def get_context_data(self, **kwargs):
        context = super(EventRegisterListView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs['ev_type']
        context['sidenav_selection'] = '{}_register'.format(
            self.kwargs['ev_type'])
        return context


class EventAdminUpdateView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    form_class = EventAdminForm
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(EventAdminUpdateView, self).get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = 'EV' if self.kwargs["ev_type"] == 'event' \
            else 'CL'
        return form_kwargs

    def get_object(self):
        queryset = Event.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(EventAdminUpdateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"]
        if self.kwargs["ev_type"] == "lesson":
            context['type'] = "class"
        context['sidenav_selection'] = self.kwargs['ev_type'] + 's'

        return context

    def form_valid(self, form):
        if form.has_changed():
            event = form.save()
            msg_ev_type = 'Event' if self.kwargs["ev_type"] == 'event' else 'Class'
            msg = '<strong>{} {}</strong> has been updated!'.format(
                msg_ev_type, event.name
            )
            ActivityLog.objects.create(
                log='{} {} (id {}) updated by admin user {}'.format(
                    msg_ev_type, event, event.id,
                    self.request.user.username
                )
            )
        else:
            msg = 'No changes made'
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"] + 's'))


class EventAdminCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = EventAdminForm
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super(EventAdminCreateView, self).get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = 'EV' if self.kwargs["ev_type"] == 'event' \
            else 'CL'
        return form_kwargs

    def get_context_data(self, **kwargs):
        context = super(EventAdminCreateView, self).get_context_data(**kwargs)
        context['type'] = self.kwargs["ev_type"]
        if self.kwargs["ev_type"] == "lesson":
            context['type'] = "class"
        context['sidenav_selection'] = 'add_{}'.format(self.kwargs['ev_type'])
        return context

    def form_valid(self, form):
        event = form.save()
        msg_ev_type = 'Event' if self.kwargs["ev_type"] == 'event' else 'Class'
        messages.success(self.request, mark_safe('<strong>{} {}</strong> has been '
                                    'created!'.format(msg_ev_type, event.name)))
        ActivityLog.objects.create(
            log='{} {} (id {}) created by admin user {}'.format(
                msg_ev_type, event, event.id, self.request.user.username
            )
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:{}'.format(self.kwargs["ev_type"] + 's'))


@login_required
@staff_required
def timetable_admin_list(request):

    if request.method == 'POST':
        sessionformset = TimetableSessionFormSet(request.POST)

        if sessionformset.is_valid():
            if not sessionformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in sessionformset:
                    if form.has_changed():
                        if 'DELETE' in form.changed_data:
                            messages.success(
                                request, mark_safe(
                                    'Session <strong>{} {} {}</strong> has been deleted!'.format(
                                    form.instance.name,
                                    DAY_CHOICES[form.instance.day],
                                    form.instance.time.strftime('%H:%M')
                                ))
                            )
                            ActivityLog.objects.create(
                                log='Session {} (id {}) deleted by admin '
                                    'user {}'.format(
                                    form.instance, form.instance.id,
                                    request.user.username
                                )
                            )
                        else:
                            for field in form.changed_data:
                                messages.success(
                                    request, mark_safe(
                                        "<strong>{}</strong> updated for "
                                        "<strong>{}</strong>".format(
                                            field.title().replace("_", " "),
                                            form.instance
                                            )
                                    )
                                )
                                ActivityLog.objects.create(
                                    log='Session {} (id {}) updated by admin '
                                        'user {}'.format(
                                        form.instance, form.instance.id,
                                        request.user.username
                                    )
                                )
                        form.save()

                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))
                sessionformset.save()
            return HttpResponseRedirect(
                reverse('studioadmin:timetable')
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in sessionformset.errors]
                        )
                    )
                )
            )

    else:
        sessionformset = TimetableSessionFormSet(
            queryset=Session.objects.all().order_by('day')
        )

    return render(
        request, 'studioadmin/timetable_list.html', {
            'sessionformset': sessionformset,
            'sidenav_selection': 'timetable'
            }
    )


class TimetableSessionUpdateView(
    LoginRequiredMixin, StaffUserMixin, UpdateView
):

    form_class = SessionAdminForm
    model = Session
    template_name = 'studioadmin/session_create_update.html'
    context_object_name = 'session'

    def get_object(self):
        queryset = Session.objects.all()
        return get_object_or_404(queryset, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super(
            TimetableSessionUpdateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'timetable'
        context['session_day'] = DAY_CHOICES[self.object.day]

        return context

    def form_valid(self, form):
        if form.has_changed():
            session = form.save()
            msg = 'Session <strong>{} {} {}</strong> has been updated!'.format(
                session.name, DAY_CHOICES[session.day],
                session.time.strftime('%H:%M')
            )
            ActivityLog.objects.create(
                log='Session {} (id {}) updated by admin user {}'.format(
                    session, session.id, self.request.user.username
                )
            )
        else:
            msg = 'No changes made'
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:timetable')


class TimetableSessionCreateView(
    LoginRequiredMixin, StaffUserMixin, CreateView
):

    form_class = SessionAdminForm
    model = Session
    template_name = 'studioadmin/session_create_update.html'
    context_object_name = 'session'

    def get_context_data(self, **kwargs):
        context = super(
            TimetableSessionCreateView, self
        ).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_session'
        return context

    def form_valid(self, form):
        session = form.save()
        msg = 'Session <strong>{} {} {}</strong> has been created!'.format(
            session.name, DAY_CHOICES[session.day],
            session.time.strftime('%H:%M')
        )
        ActivityLog.objects.create(
            log='Session {} (id {}) created by admin user {}'.format(
                session, session.id, self.request.user.username
            )
        )
        messages.success(self.request, mark_safe(msg))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:timetable')


@login_required
@staff_required
def upload_timetable_view(request,
                          template_name="studioadmin/upload_timetable_form.html"):

    if request.method == 'POST':
        form = UploadTimetableForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            created_classes, existing_classes = \
                utils.upload_timetable(start_date, end_date, request.user)
            context = {'start_date': start_date,
                       'end_date': end_date,
                       'created_classes': created_classes,
                       'existing_classes': existing_classes,
                       'sidenav_selection': 'upload_timetable'}
            return render(
                request, 'studioadmin/upload_timetable_confirmation.html',
                context
            )
    else:
        form = UploadTimetableForm()
    return render(request, template_name,
                  {'form': form, 'sidenav_selection': 'upload_timetable'})


class UserListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = User
    template_name = 'studioadmin/user_list.html'
    context_object_name = 'users'
    queryset = User.objects.all().order_by('first_name')

    def get(self, request, *args, **kwargs):
        if 'change_user' in self.request.GET:
            change_user_id = self.request.GET.getlist('change_user')[0]
            user_to_change = User.objects.get(id=change_user_id)
            is_regular_student = user_to_change.has_perm('booking.is_regular_student')
            perm = Permission.objects.get(codename='is_regular_student')
            if is_regular_student:
                user_to_change.user_permissions.remove(perm)
                if user_to_change.is_superuser:
                    messages.error(
                        request,
                        "{} {} ({}) is a superuser; you cannot remove "
                        "permissions".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username
                        )
                    )
                else:
                    messages.success(
                        request,
                        "'Regular student' status has been removed for "
                        "{} {} ({})".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username
                        )
                    )
                    ActivityLog.objects.create(
                        log="'Regular student' status has been removed for "
                        "{} {} ({}) by admin user {}".format(
                            user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username,
                            request.user.username
                        )
                    )

            else:
                user_to_change.user_permissions.add(perm)
                messages.success(
                    request,
                    "{} {} ({}) has been given 'regular student' "
                    "status".format(
                        user_to_change.first_name,
                        user_to_change.last_name,
                        user_to_change.username
                    )
                )
                ActivityLog.objects.create(
                    log="{} {} ({}) has been given 'regular student' "
                    "status by admin user {}".format(
                        user_to_change.first_name,
                            user_to_change.last_name,
                            user_to_change.username,
                            request.user.username
                        )
                )
            user_to_change.save()
        return super(UserListView, self).get(request, *args, **kwargs)

    def get_context_data(self):
        context = super(UserListView, self).get_context_data()
        context['sidenav_selection'] = 'users'
        return context


class BlockListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Block
    template_name = 'studioadmin/block_list.html'
    context_object_name = 'blocks'
    default_sort_params = ('block_type', 'asc')

    def get_queryset(self):
        block_status = self.request.GET.get('block_status', 'current')
        all_blocks = Block.objects.all()
        if block_status == 'all':
            return all_blocks
        elif block_status == 'current':
            current = (block.id for block in all_blocks
                      if not block.expired and not block.full)
            return Block.objects.filter(id__in=current)
        elif block_status == 'active':
            active = (block.id for block in all_blocks if block.active_block())
            return Block.objects.filter(id__in=active)
        elif block_status == 'unpaid':
            unpaid = (block.id for block in all_blocks
                      if not block.expired and not block.paid
                      and not block.full)
            return Block.objects.filter(id__in=unpaid)
        elif block_status == 'expired':
            expired = (block.id for block in all_blocks if block.expired or block.full)
            return Block.objects.filter(id__in=expired)

    def get_context_data(self):
        context = super(BlockListView, self).get_context_data()
        context['sidenav_selection'] = 'blocks'

        block_status = self.request.GET.get('block_status', 'current')
        form = BlockStatusFilter(initial={'block_status': block_status})
        context['form'] = form
        context['block_status'] = block_status

        return context


@login_required
@staff_required
def choose_users_to_email(request,
                          template_name='studioadmin/choose_users_form.html'):

    initial_userfilterdata={'events': [''], 'lessons': ['']}

    if 'filter' in request.POST:
        event_ids = request.POST.getlist('filter-events')
        lesson_ids = request.POST.getlist('filter-lessons')

        if event_ids == ['']:
            if request.session.get('events'):
                del request.session['events']
            event_ids = []
        else:
            request.session['events'] = event_ids
            initial_userfilterdata['events'] = event_ids

        if lesson_ids == ['']:
            if request.session.get('lessons'):
                del request.session['lessons']
            lesson_ids = []
        else:
            request.session['lessons'] = lesson_ids
            initial_userfilterdata['lessons'] = lesson_ids

        if not event_ids and not lesson_ids:
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.all().order_by('username'))
        else:
            event_and_lesson_ids = event_ids + lesson_ids
            bookings = Booking.objects.filter(event__id__in=event_and_lesson_ids)
            user_ids = set([booking.user.id for booking in bookings
                            if booking.status == 'OPEN'])
            usersformset = ChooseUsersFormSet(
                queryset=User.objects.filter(id__in=user_ids).order_by('username')
            )

    elif request.method == 'POST':
        usersformset = ChooseUsersFormSet(request.POST)

        if usersformset.is_valid():

            event_ids = request.session.get('events', [])
            lesson_ids = request.session.get('lessons', [])
            users_to_email = []

            for form in usersformset:
                # check checkbox value to determine if that user is to be
                # emailed; add user_id to list
                if form.is_valid():
                    if form.cleaned_data.get('email_user'):
                        users_to_email.append(form.instance.id)
                else:
                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))

            request.session['users_to_email'] = users_to_email

            return HttpResponseRedirect(url_with_querystring(
                reverse('studioadmin:email_users_view'), events=event_ids, lessons=lesson_ids)
            )

        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in usersformset.errors]
                        )
                    )
                )
            )

    else:
        usersformset = ChooseUsersFormSet(
            queryset=User.objects.all().order_by('username'),
        )

    userfilterform = UserFilterForm(prefix='filter', initial=initial_userfilterdata)

    return TemplateResponse(
        request, template_name, {
            'usersformset': usersformset,
            'userfilterform': userfilterform,
            'sidenav_selection': 'email_users',
            }
    )


def url_with_querystring(path, **kwargs):
    return path + '?' + urllib.parse.urlencode(kwargs)


@login_required
@staff_required
def email_users_view(request,
                     template_name='studioadmin/email_users_form.html'):

        users_to_email = User.objects.filter(id__in=request.session['users_to_email'])

        if request.method == 'POST':

            form = EmailUsersForm(request.POST)

            if form.is_valid():
                subject = '{} {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,
                    form.cleaned_data['subject'])
                from_address = form.cleaned_data['from_address']
                message = form.cleaned_data['message']
                cc = form.cleaned_data['cc']

                # do this per email address so recipients are not visible to
                # each
                email_addresses = [user.email for user in users_to_email]
                if cc:
                    email_addresses.append(from_address)
                for email_address in email_addresses:
                    try:
                        send_mail(subject, message, from_address,
                              [email_address],
                              html_message=get_template(
                                  'studioadmin/email/email_users.html').render(
                                  Context({
                                      'subject': subject,
                                      'message': message})
                              ),
                              fail_silently=False)
                    except Exception as e:
                        # send mail to tech support with Exception
                        send_support_email(e, __name__, "Bulk Email to students")
                        ActivityLog.objects.create(log="Possible error with "
                            "sending bulk email; notification sent to tech support")
                ActivityLog.objects.create(
                    log='Bulk email with subject "{}" sent to users {} by '
                        'admin user {}'.format(
                        subject, email_addresses, request.user.username
                    )
                )

                return render(request,
                    'studioadmin/email_users_confirmation.html')

            else:
                event_ids = request.session.get('events')
                lesson_ids = request.session.get('lessons')
                events = Event.objects.filter(id__in=event_ids)
                lessons = Event.objects.filter(id__in=lesson_ids)
                totaleventids = event_ids + lesson_ids
                totalevents = Event.objects.filter(id__in=totaleventids)
                messages.error(request, mark_safe("Please correct errors in form: {}".format(form.errors)))
                form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        else:
            event_ids = ast.literal_eval(request.GET.get('events'))
            events = Event.objects.filter(id__in=event_ids)
            lesson_ids = ast.literal_eval(request.GET.get('lessons'))
            lessons = Event.objects.filter(id__in=lesson_ids)
            totaleventids = event_ids + lesson_ids
            totalevents = Event.objects.filter(id__in=totaleventids)
            form = EmailUsersForm(initial={'subject': "; ".join((str(event) for event in totalevents))})

        return TemplateResponse(
            request, template_name, {
                'form': form,
                'users_to_email': users_to_email,
                'sidenav_selection': 'email_users',
                'events': events,
                'lessons': lessons
            }
        )


@login_required
@staff_required
def user_bookings_view(request, user_id, booking_status='future'):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        booking_status = request.POST.getlist('booking_status')[0]
        userbookingformset = UserBookingFormSet(
            request.POST, instance=user, user=user,
        )
        if userbookingformset.is_valid():
            if not userbookingformset.has_changed() and \
                    request.POST.get('formset_submitted'):
                messages.info(request, "No changes were made")
            else:
                for form in userbookingformset:
                    if form.is_valid():
                        if form.has_changed():
                            if form.changed_data == ['send_confirmation']:
                                messages.info(
                                    request, "'Send confirmation' checked for '{}' "
                                    "but no changes were made; email has not been "
                                    "sent to user.".format(form.instance.event))
                            else:
                                booking = form.save(commit=False)
                                event_was_full = booking.event.spaces_left() == 0
                                action = 'updated' if form.instance.id else 'created'
                                if 'status' in form.changed_data and action == 'updated':
                                    if booking.status == 'CANCELLED':
                                        booking.paid = False
                                        booking.payment_confirmed = False
                                        booking.block = None
                                        action = 'cancelled'
                                    elif booking.status == 'OPEN':
                                        action = 'reopened'

                                if booking.block:
                                    booking.paid = True
                                    booking.payment_confirmed = True
                                elif 'block' in form.changed_data:
                                    booking.block = None
                                    booking.paid = False
                                    booking.payment_confirmed = False

                                if 'paid' in form.changed_data:
                                    if booking.paid:
                                        # assume that if booking is being done via
                                        # studioadmin, marking paid also means payment
                                        # is confirmed
                                        booking.payment_confirmed = True
                                    else:
                                        booking.payment_confirmed = False
                                try:
                                    booking.save()
                                except BookingError:
                                    messages.error(request,
                                        mark_safe('<span class="cancel-warning">'
                                        'ERROR:</span> Booking cannot'
                                        ' be made for fully booked event '
                                        '{}'.format(booking.event))
                                    )
                                else:
                                    set_as_free = 'free_class' in form.changed_data and booking.free_class
                                    if 'send_confirmation' in form.changed_data:
                                        try:
                                            # send confirmation email
                                            host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                                            # send email to studio
                                            ctx = Context({
                                                  'host': host,
                                                  'event': booking.event,
                                                  'user': booking.user,
                                                  'action': action,
                                                  'set_as_free': set_as_free
                                            })
                                            send_mail('{} Your booking for {} has been {}'.format(
                                                settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event, action
                                                ),
                                                get_template(
                                                    'studioadmin/email/booking_change_confirmation.txt'
                                                ).render(ctx),
                                                settings.DEFAULT_FROM_EMAIL,
                                                [booking.user.email],
                                                html_message=get_template(
                                                    'studioadmin/email/booking_change_confirmation.html'
                                                    ).render(ctx),
                                                fail_silently=False)
                                            send_confirmation_msg = "and confirmation " \
                                            "email sent to user"
                                        except Exception as e:
                                            # send mail to tech support with Exception
                                            send_support_email(
                                                e, __name__, "user_booking_list - "
                                                "send confirmation email"
                                            )
                                            send_confirmation_msg = ". There was a " \
                                            "problem sending the confirmation email to the " \
                                            "user.  Tech support has been notified."
                                    else:
                                        send_confirmation_msg = ""

                                    messages.success(
                                        request,
                                        'Booking for {} has been {} {}'.format(
                                            booking.event, action, send_confirmation_msg
                                        )
                                    )
                                    ActivityLog.objects.create(
                                        log='Booking id {} (user {}) for "{}" {} '
                                                'by admin user {} {}'.format(
                                            booking.id, booking.user.username, booking.event,
                                            action, request.user.username,
                                            "and marked as free class" if set_as_free else ""
                                        )
                                    )

                                    if action == 'reopened':
                                        messages.info(
                                            request, mark_safe(
                                                'Note: this booking was previously '
                                                'cancelled and has now been reopened. '
                                                '<span class="cancel-warning">Payment '
                                                'status has not been automatically '
                                                'updated. Please review the booking '
                                                'and update if paid '
                                                'and/or block used.</span>'
                                            )
                                        )
                                    elif action == 'cancelled':
                                        messages.info(
                                            request, 'Note: this booking has been '
                                            'cancelled.  The booking has automatically '
                                            'been marked as unpaid (refunded) and, if '
                                            'applicable, the block used has been updated.')

                                        if event_was_full:
                                            waiting_list_users = WaitingListUser.objects.filter(
                                                event=booking.event
                                            )
                                            if waiting_list_users:
                                                try:
                                                    send_waiting_list_email(
                                                        booking.event,
                                                        [wluser.user for \
                                                            wluser in waiting_list_users],
                                                        host='http://{}'.format(
                                                            request.META.get('HTTP_HOST')
                                                        )
                                                    )
                                                    ActivityLog.objects.create(
                                                        log='Waiting list email sent to '
                                                        'user(s) {} for event {}'.format(
                                                            ', '.join(
                                                                [wluser.user.username \
                                                                    for wluser in \
                                                                    waiting_list_users]
                                                            ),
                                                            booking.event
                                                        )
                                                    )
                                                except Exception as e:
                                                    # send mail to tech support with Exception
                                                    send_support_email(
                                                        e, __name__, "Automatic cancel job - waiting list email"
                                                    )

                                    if action == 'created' or action == 'reopened':
                                        try:
                                            waiting_list_user = WaitingListUser.objects.get(
                                                user=booking.user, event=booking.event
                                            )
                                            waiting_list_user.delete()
                                            ActivityLog.objects.create(
                                                log='User {} has been removed from the '
                                                'waiting list for {}'.format(
                                                    booking.user.username,
                                                    booking.event
                                                )
                                            )
                                        except WaitingListUser.DoesNotExist:
                                            pass
                    else:
                        for error in form.errors:
                            messages.error(request, mark_safe("{}".format(error)))

                    userbookingformset.save(commit=False)

            return HttpResponseRedirect(
                reverse(
                    'studioadmin:user_bookings_list',
                    kwargs={
                        'user_id': user.id,
                        'booking_status': booking_status
                    }
                )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in userbookingformset.errors]
                        )
                    )
                )
            )
    else:
        all_bookings = Booking.objects.filter(user=user)

        if booking_status == 'past':
            queryset = all_bookings.filter(
                event__date__lt=timezone.now()
            ).order_by('event__date')
            userbookingformset = UserBookingFormSet(
                queryset=queryset, instance=user, user=user,
            )
        else:
            # 'future' by default
            queryset = all_bookings.filter(
                event__date__gte=timezone.now()
            ).order_by('event__date')
            userbookingformset = UserBookingFormSet(
                queryset=queryset, instance=user, user=user,
            )

        userbookingformset = UserBookingFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    booking_status_filter = BookingStatusFilter(
        initial={'booking_status': booking_status}
    )

    template = 'studioadmin/user_booking_list.html'
    return TemplateResponse(
        request, template, {
            'userbookingformset': userbookingformset, 'user': user,
            'sidenav_selection': 'users',
            'booking_status_filter': booking_status_filter,
            'booking_status': booking_status
        }
    )


@login_required
@staff_required
def user_blocks_view(request, user_id):

    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        userblockformset = UserBlockFormSet(
            request.POST,
            instance=user,
            user=user
        )
        if userblockformset.is_valid():
            if not userblockformset.has_changed():
                messages.info(request, "No changes were made")
            else:
                for form in userblockformset:
                    if form.has_changed():

                        block = form.save(commit=False)

                        if 'DELETE' in form.changed_data:
                            messages.success(
                                request, mark_safe(
                                    'Block <strong>{}</strong> has been '
                                    'deleted!  Any bookings made with this '
                                    'block have been changed to unpaid.  '
                                    'Please inform user {} ({})'.format(
                                        block, block.user.username,
                                        block.user.email
                                    )
                                )
                            )
                            ActivityLog.objects.create(
                                log='Block {} (id {}) deleted by admin user {}'.format(
                                form.instance, form.instance.id, request.user.username)
                            )
                            block.delete()
                        else:
                            new = False if form.instance.id else True
                            msg = 'created' if new else 'updated'

                            messages.success(
                                request,
                                'Block for {} has been {}'.format(
                                    block.block_type.event_type, msg
                                )
                            )
                            block.save()
                            ActivityLog.objects.create(
                                log='Block id {} ({}), user {}, has been {}'
                                        ' by admin user {}'.format(
                                    block.id, block.block_type,
                                    block.user.username, msg,
                                    request.user.username
                                )
                            )
                    for error in form.errors:
                        messages.error(request, mark_safe("{}".format(error)))
                userblockformset.save(commit=False)

            return HttpResponseRedirect(
                reverse('studioadmin:user_blocks_list',
                        kwargs={'user_id': user.id}
                        )
            )
        else:
            messages.error(
                request,
                mark_safe(
                    "There were errors in the following fields:\n{}".format(
                        '\n'.join(
                            ["{}".format(error) for error in userblockformset.errors]
                        )
                    )
                )
            )
    else:
        queryset = Block.objects.filter(
            user=user).order_by('start_date')
        userblockformset = UserBlockFormSet(
            instance=user,
            queryset=queryset,
            user=user
        )

    template = 'studioadmin/user_block_list.html'
    return TemplateResponse(
        request, template, {
            'userblockformset': userblockformset, 'user': user,
            'sidenav_selection': 'users'
        }
    )


class ActivityLogListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = ActivityLog
    template_name = 'studioadmin/activitylog.html'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):

        empty_text = [
            'email_warnings job run; no unpaid booking warnings to send',
            'cancel_unpaid_bookings job run; no bookings to cancel'
        ]
        queryset = ActivityLog.objects.exclude(
            log__in=empty_text
        ).order_by('-timestamp')

        reset = self.request.GET.get('reset')
        search_submitted =  self.request.GET.get('search_submitted')
        search_text = self.request.GET.get('search')
        search_date = self.request.GET.get('search_date')
        hide_empty_cronjobs = self.request.GET.get('hide_empty_cronjobs')

        if reset or (not (search_text or search_date) and hide_empty_cronjobs) or (not reset and not search_submitted):
            return queryset

        if not hide_empty_cronjobs:
            queryset = ActivityLog.objects.all().order_by('-timestamp')

        if search_date:
            try:
                search_date = datetime.strptime(search_date, '%d-%b-%Y')
                start_datetime = search_date
                end_datetime = search_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                queryset = queryset.filter(
                    Q(timestamp__gte=start_datetime) & Q(timestamp__lte=end_datetime)
                ).order_by('-timestamp')
            except ValueError:
                messages.error(
                    self.request, 'Invalid search date format.  Please select '
                    'from datepicker or enter using the format dd-Mmm-YYYY'
                )
                return queryset

        if search_text:
            queryset = queryset.filter(
                log__contains=search_text).order_by('-timestamp')

        return queryset

    def get_context_data(self):
        context = super(ActivityLogListView, self).get_context_data()
        context['sidenav_selection'] = 'activitylog'

        search_submitted =  self.request.GET.get('search_submitted')
        hide_empty_cronjobs = self.request.GET.get('hide_empty_cronjobs') \
        if search_submitted else 'on'

        search_text = self.request.GET.get('search', '')
        search_date = self.request.GET.get('search_date', None)
        reset = self.request.GET.get('reset')
        if reset:
            hide_empty_cronjobs = 'on'
            search_text = ''
            search_date = None
        form = ActivityLogSearchForm(
            initial={
                'search': search_text, 'search_date': search_date,
                'hide_empty_cronjobs': hide_empty_cronjobs
            })
        context['form'] = form

        return context


@login_required
@staff_required
def event_waiting_list_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    waiting_list_users = WaitingListUser.objects.filter(
        event__id=event_id).order_by('user__username')
    ev_type = 'lessons' if event.event_type.event_type == 'CL' else 'events'

    template = 'studioadmin/event_waiting_list.html'
    return TemplateResponse(
        request, template, {
            'waiting_list_users': waiting_list_users, 'event': event,
            'sidenav_selection': '{}_register'.format(ev_type)
        }
    )
