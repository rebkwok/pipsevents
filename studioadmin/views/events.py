import logging

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.views.generic import CreateView, UpdateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Event
from booking.email_helpers import send_support_email
from studioadmin.forms import EventFormSet,  EventAdminForm
from studioadmin.views.helpers import staff_required, StaffUserMixin
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@staff_required
def event_admin_list(request, ev_type):

    if ev_type == 'events':
        ev_type_text = 'event'
        queryset = Event.objects.filter(
            event_type__event_type='EV',
            date__gte=timezone.now() - timedelta(hours=1)
        ).order_by('date')
    else:
        ev_type_text = 'class'
        queryset = Event.objects.filter(
            date__gte=timezone.now() - timedelta(hours=1)
        ).exclude(event_type__event_type='EV').order_by('date')

    events = True if queryset.count() > 0 else False
    show_past = False

    if request.method == 'POST':
        if "past" in request.POST:

            if ev_type == 'events':
                queryset = Event.objects.filter(
                    event_type__event_type='EV',
                    date__lte=timezone.now()
                ).order_by('date')
            else:
                queryset = Event.objects.filter(
                    date__lte=timezone.now()
                ).exclude(event_type__event_type='EV').order_by('date')
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

    return TemplateResponse(
        request, 'studioadmin/admin_events.html', {
            'eventformset': eventformset,
            'type': ev_type,
            'events': events,
            'sidenav_selection': ev_type,
            'show_past': show_past,
            }
    )


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
def cancel_event_view(request, slug):
    event = get_object_or_404(Event, slug=slug)
    ev_type = 'class' if event.event_type.event_type == 'CL' else 'event'

    open_bookings = [
        booking for booking in event.bookings.all() if booking.status == 'OPEN'
        ]

    open_direct_paid_bookings = [
        booking for booking in open_bookings if
        (booking.paid or booking.deposit_paid) and
        not booking.block and not booking.free_class
    ]

    if request.method == 'POST':
        if 'confirm' in request.POST:
            for booking in open_bookings:

                block_paid = bool(booking.block)
                direct_paid = booking in open_direct_paid_bookings

                if booking.block:
                    booking.block = None
                    booking.paid = False
                    booking.payment_confirmed = False
                elif booking.free_class:
                    booking.free_class = False
                    booking.paid = False
                    booking.payment_confirmed = False

                booking.status = "CANCELLED"
                booking.save()

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                    # send email to studio
                    ctx = {
                          'host': host,
                          'event_type': ev_type,
                          'block': block_paid,
                          'direct_paid': direct_paid,
                          'event': event,
                          'user': booking.user,
                    }
                    send_mail('{} {} has been cancelled'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, ev_type.title(),
                        ),
                        get_template(
                            'studioadmin/email/event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [booking.user.email],
                        html_message=get_template(
                            'studioadmin/email/event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel event - "
                        "send notification email to user"
                    )

            event.cancelled = True
            event.booking_open = False
            event.payment_open = False
            event.save()

            if open_direct_paid_bookings:
                # email studio with links for confirming refunds

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                    # send email to studio
                    ctx = {
                          'host': host,
                          'event_type': ev_type,
                          'open_direct_paid_bookings': open_direct_paid_bookings,
                          'event': event,
                    }
                    send_mail('{} Refunds due for cancelled {}'.format(
                        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, ev_type.title(),
                        ),
                        get_template(
                            'studioadmin/email/to_studio_event_cancelled.txt'
                        ).render(ctx),
                        settings.DEFAULT_FROM_EMAIL,
                        [settings.DEFAULT_STUDIO_EMAIL],
                        html_message=get_template(
                            'studioadmin/email/to_studio_event_cancelled.html'
                            ).render(ctx),
                        fail_silently=False)
                except Exception as e:
                    # send mail to tech support with Exception
                    send_support_email(
                        e, __name__, "cancel event - "
                        "send refund notification email to tudio"
                    )

            if open_bookings:
                booking_cancelled_msg = 'open ' \
                                        'booking(s) for {} have been cancelled ' \
                                        'and notification emails have been ' \
                                        'sent to {}.'.format(
                    ev_type,
                    ', '.join(
                        ['{} {}'.format(booking.user.first_name,
                                        booking.user.last_name)
                         for booking in open_bookings]
                        )
                    )
            else:
                booking_cancelled_msg = 'there were ' \
                                        'no open bookings for this {}'.format(
                    ev_type
                )
            messages.info(
                request,
                '{} has been cancelled; '.format(ev_type.title()) + booking_cancelled_msg
            )

            ActivityLog.objects.create(
                log="{} {} has been cancelled by admin user {}; {}".format(
                    ev_type.title(), event, request.user.username,
                    booking_cancelled_msg
                )
            )

            return HttpResponseRedirect(
                reverse('studioadmin:{}'.format(
                    'events' if ev_type == 'event' else 'lessons'
                ))
            )
        elif 'cancel' in request.POST:
            return HttpResponseRedirect(
                reverse('studioadmin:{}'.format(
                    'events' if ev_type == 'event' else 'lessons'
                ))
            )

    context = {
        'event': event,
        'event_type': ev_type,
        'open_bookings': open_bookings,
        'open_direct_paid_bookings': open_direct_paid_bookings
    }

    return TemplateResponse(
        request, 'studioadmin/cancel_event.html', context
    )
