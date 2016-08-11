import logging

from datetime import timedelta

from django.db.models import Q
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.views.generic import CreateView, UpdateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import Block, BlockType, Booking, Event
from booking.email_helpers import send_support_email
from studioadmin.forms import EventFormSet,  EventAdminForm
from studioadmin.views.helpers import staff_required, StaffUserMixin
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


def _get_past_events(ev_type, request):
    if ev_type == 'events':
        nonpag_events = Event.objects.filter(
            event_type__event_type='EV',
            date__lte=timezone.now()
        ).order_by('-date')
    else:
        nonpag_events = Event.objects.filter(
            date__lte=timezone.now()
        ).exclude(event_type__event_type='EV').order_by('-date')

    paginator = Paginator(nonpag_events, 20)
    page = request.GET.get('page')
    try:
        events = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        events = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        events = paginator.page(paginator.num_pages)
    page_query = nonpag_events.filter(id__in=[obj.id for obj in events])
    eventformset = EventFormSet(queryset=page_query)
    return events, eventformset


@login_required
@staff_required
def event_admin_list(request, ev_type):

    if ev_type == 'events':
        ev_type_text = 'event'
        events = Event.objects.select_related('event_type').filter(
            event_type__event_type='EV',
            date__gte=timezone.now() - timedelta(hours=1)
        ).order_by('date')
    else:
        ev_type_text = 'class'
        events = Event.objects.select_related('event_type').filter(
            date__gte=timezone.now() - timedelta(hours=1)
        ).exclude(event_type__event_type='EV').order_by('date')

    show_past = False

    if request.method == 'POST':
        if "past" in request.POST:
            show_past = True
            events, eventformset = _get_past_events(ev_type, request)
        elif "upcoming" in request.POST:
            show_past = False
            eventformset = EventFormSet(queryset=events)
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
                    eventformset.save()
                return HttpResponseRedirect(
                    reverse('studioadmin:{}'.format(ev_type),)
                )
            else:  # pragma: no cover
                # currently only boolean fields, this is left here in case of
                # future additional fields
                messages.error(
                    request,
                    mark_safe(
                        "There were errors in the following fields:\n{}".format(
                            '\n'.join(
                                [
                                    "{}".format(error)
                                    for error in eventformset.errors
                                    ]
                            )
                        )
                    )
                )

    else:
        page = request.GET.get('page')  # only past is paginated
        if page:
            show_past = True
            events, eventformset = _get_past_events(ev_type, request)
        else:
            eventformset = EventFormSet(queryset=events)

    non_deletable_events = Booking.objects.select_related('event').filter(event__in=events).distinct().values_list('event__id', flat=True)

    return TemplateResponse(
        request, 'studioadmin/admin_events.html', {
            'eventformset': eventformset,
            'type': ev_type,
            'events': events,
            'sidenav_selection': ev_type,
            'show_past': show_past,
            'non_deletable_events': non_deletable_events
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
            messages.success(self.request, mark_safe(msg))
            ActivityLog.objects.create(
                log='{} {} (id {}) updated by admin user {}'.format(
                    msg_ev_type, event, event.id,
                    self.request.user.username
                )
            )

            if 'paypal_email' in form.changed_data and \
                event.paypal_email != settings.DEFAULT_PAYPAL_EMAIL:
                messages.warning(
                    self.request,
                    mark_safe(
                        "You have changed the paypal receiver email. If you "
                        "haven't used this email before, "
                        "it is strongly recommended that you test the email "
                        "address "
                        "<a href='/studioadmin/test-paypal-email?email={}'>"
                        "here</a>".format(event.paypal_email)
                    )
                )

        else:
            messages.info(self.request, 'No changes made')
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
        if event.paypal_email != settings.DEFAULT_PAYPAL_EMAIL:
            messages.warning(
                self.request,
                mark_safe(
                    "You have changed the paypal receiver email from the "
                    "default value. If you haven't used this email before, "
                    "it is strongly recommended that you test the email "
                    "address "
                    "<a href='/studioadmin/test-paypal-email?email={}'>"
                    "here</a>".format(event.paypal_email)
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

    open_bookings = Booking.objects.filter(
        event=event, status='OPEN', no_show=False
    )
    no_shows_all = Booking.objects.filter(
        event=event, status='OPEN', no_show=True
    )
    no_shows = [bk for bk in no_shows_all if bk.paid or bk.deposit_paid]
    open_block_bookings = [
        bk for bk in open_bookings if bk.block and not bk.free_class
        ]
    open_unpaid_bookings = [
        bk for bk in open_bookings if not bk.deposit_paid and not bk.paid]
    open_free_non_block = [
        bk for bk in open_bookings if bk.free_class and not bk.block
        ]
    open_free_block = [bk for bk in open_bookings if bk.free_class and bk.block]
    open_direct_paid_deposit_only = [
        bk for bk in open_bookings if not bk.block
        and not bk.free_class and bk.deposit_paid and not bk.paid
    ]
    open_direct_paid = [
        bk for bk in open_bookings if not bk.block
        and not bk.free_class and bk.paid
    ]

    if request.method == 'POST':
        if 'confirm' in request.POST:
            transfer_direct_paid = request.POST.get('direct_paid_action') == 'transfer'

            for booking in open_bookings:
                transfer_block_created = False
                block_paid = bool(booking.block)  # block paid and free blocks
                free_block = bool(booking.block and booking.free_class)
                direct_paid = booking in open_direct_paid or \
                              booking in open_free_non_block
                deposit_only_paid = booking in open_direct_paid_deposit_only

                if booking.block:
                    booking.block = None
                    booking.deposit_paid = False
                    booking.paid = False
                    booking.payment_confirmed = False
                    # in case this was paid with a free class block
                    booking.free_class = False
                elif direct_paid and transfer_direct_paid:
                    # direct paid = paypal and free non-block paid
                    # create transfer block and make this booking unpaid
                    if booking.event.event_type.event_type != 'EV':
                        booking.deposit_paid = False
                        booking.paid = False
                        booking.payment_confirmed = False
                        booking.free_class = False
                        block_type, _ = BlockType.objects.get_or_create(
                            event_type=booking.event.event_type,
                            size=1, cost=0, duration=1,
                            identifier='transferred',
                            active=False
                        )
                        Block.objects.create(
                            block_type=block_type, user=booking.user,
                            transferred_booking_id=booking.id
                        )
                        transfer_block_created = True

                booking.status = "CANCELLED"
                booking.save()

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                    ctx = {
                        'host': host,
                        'event_type': ev_type,
                        'block_paid': block_paid,
                        'direct_paid': direct_paid or deposit_only_paid,
                        'free_block': free_block,
                        'transfer_block_created': transfer_block_created,
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

            # email studio with links for confirming refunds
            # direct paid (full and deposit only) and free non-block
            # if action selected is not transfer, otherwise just email for
            # deposits as we don't create
            # transfer blocks for deposit-only
            try:
                host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                # send email to studio
                ctx = {
                    'host': host,
                    'event_type': ev_type,
                    'transfer_direct_paid': transfer_direct_paid,
                    'open_bookings': open_bookings,
                    'open_direct_paid_bookings': open_direct_paid,
                    'open_block_bookings': open_block_bookings,
                    'open_deposit_only_paid_bookings': open_direct_paid_deposit_only,
                    'open_unpaid_bookings': open_unpaid_bookings,
                    'open_free_non_block_bookings': open_free_non_block,
                    'open_free_block_bookings': open_free_block,
                    'no_shows': no_shows,
                    'event': event,
                }
                send_mail(
                    '{} {} has been cancelled - please review for refunds '
                    'required'.format(
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
                    "send refund notification email to studio"
                )

            if open_bookings:
                booking_cancelled_msg = 'open ' \
                                        'booking(s) have been cancelled{} ' \
                                        'Notification emails have been ' \
                                        'sent to {}.'.format(
                    ' and transfer blocks created for direct paid bookings.'
                    if request.POST.get('direct_paid_action') == 'transfer'
                    else '.',
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
                '{} has been cancelled; '.format(
                    ev_type.title()
                ) + booking_cancelled_msg
            )

            ActivityLog.objects.create(
                log="{} {} cancelled by admin user {}; {}".format(
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
        'open_bookings': bool(open_bookings),
        'open_direct_paid_bookings': open_direct_paid,
        'open_block_bookings': open_block_bookings,
        'open_deposit_only_paid_bookings': open_direct_paid_deposit_only,
        'open_unpaid_bookings': open_unpaid_bookings,
        'open_free_non_block_bookings': open_free_non_block,
        'open_free_block_bookings': open_free_block,
        'no_shows': no_shows
    }

    return TemplateResponse(
        request, 'studioadmin/cancel_event.html', context
    )
