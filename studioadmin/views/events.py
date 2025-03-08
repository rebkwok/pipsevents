import logging

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.urls import reverse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.views.generic import CreateView, UpdateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin
from dateutil.relativedelta import relativedelta

from booking.models import Block, BlockType, Booking, Event, FilterCategory
from booking.email_helpers import send_support_email
from studioadmin.forms import EventAdminForm, OnlineTutorialAdminForm
from studioadmin.views.email_helpers import send_new_classes_email_to_members
from studioadmin.views.helpers import staff_required, StaffUserMixin, set_cloned_name, get_page
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


EVENT_TYPE_PARAM_MAPPING = {
    "event": {"abbr": "EV", "name": "event", "sidenav": "event", "sidenav_plural": "events"},
    "events": {"abbr": "EV", "name": "event", "sidenav": "event", "sidenav_plural": "events"},
    "room_hire": {"abbr": "RH", "name": "room hire", "sidenav": "room_hire", "sidenav_plural": "room_hires"},
    "room_hires": {"abbr": "RH", "name": "room hire", "sidenav": "room_hire", "sidenav_plural": "room_hires"},
    "online_tutorial": {"abbr": "OT", "name": "online tutorial", "sidenav": "online_tutorial", "sidenav_plural": "online_tutorials"},
    "online_tutorials": {"abbr": "OT", "name": "online tutorial", "sidenav": "online_tutorial", "sidenav_plural": "online_tutorials"},
    "lesson": {"abbr": "CL", "name": "class", "sidenav": "lesson", "sidenav_plural": "lessons"},
    "lessons": {"abbr": "CL", "name": "class", "sidenav": "lesson", "sidenav_plural": "lessons"}
}

def _get_events(ev_type, request, past, page=None):
    event_type = EVENT_TYPE_PARAM_MAPPING[ev_type]["abbr"]
    nonpag_events = Event.objects.select_related('event_type').filter(
            event_type__event_type=event_type
        )

    if past:
        nonpag_events = nonpag_events.filter(date__lt=timezone.now())\
            .order_by('-date', 'name')
    else:
        nonpag_events = nonpag_events.filter(
            date__gte=timezone.now() - timedelta(hours=1)
        ).order_by('date', "name")
    paginator = Paginator(nonpag_events, 30)
    event_page = get_page(request, paginator, page)
    events = event_page.object_list
    return events, event_page


@login_required
@staff_required
def event_admin_list(request, ev_type):
    ev_type_text = EVENT_TYPE_PARAM_MAPPING[ev_type]["name"]

    page = request.GET.get('page', None) or request.POST.get('page', None)
    if request.method == 'POST':
        show_past = "past" in request.POST
        if "past" in request.POST or "upcoming" in request.POST:
            # clear the page number if we're switching btwn past and upcoming
            events, ev_page = _get_events(
                ev_type, request, show_past, page=1
            )
        else:
            #  get events and page, keep existing queryset
            events, ev_page = _get_events(
                ev_type, request, show_past, page
            )

    else:  # GET; default to upcoming
        show_past = request.GET.get('past', False)
        events, ev_page = _get_events(
            ev_type, request, show_past, page
        )

    return TemplateResponse(
        request, 'studioadmin/admin_events.html', {
            'type': ev_type,
            'events': events,
            'event_page': ev_page,
            'paginator_range': ev_page.paginator.get_elided_page_range(ev_page.number),
            'sidenav_selection': ev_type,
            'show_past': show_past,
            }
    )


class EventAdminMixin:

    def add_new_category(self, form):
        event = form.save()
        new_category = form.cleaned_data.get("new_category")
        if new_category:
            new_category = FilterCategory.objects.create(category=new_category)
            event.categories.add(new_category)
        return event


class EventAdminUpdateView(LoginRequiredMixin, StaffUserMixin, EventAdminMixin, UpdateView):

    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_class(self):
        return OnlineTutorialAdminForm if self.kwargs["ev_type"] == "online_tutorial" else EventAdminForm

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["abbr"]
        return form_kwargs

    def get_object(self):
        queryset = Event.objects.all()
        return get_object_or_404(queryset, slug=self.kwargs['slug'])

    def get_context_data(self, **kwargs):
        context = super(EventAdminUpdateView, self).get_context_data(**kwargs)
        context['type'] = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["name"]
        context['sidenav_selection'] = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["sidenav_plural"]
        return context

    def form_valid(self, form):
        if not form.has_changed():
            messages.info(self.request, 'No changes made')
        else:
            event = self.add_new_category(form)
            msg_ev_type = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["name"].title()
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


        url = self.get_success_url()
        if 'from_page' in self.request.POST:
            url += '?page=' + self.request.POST['from_page']
        return HttpResponseRedirect(url)

    def get_success_url(self):
        return reverse(f'studioadmin:{EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["sidenav_plural"]}')


class EventAdminCreateView(LoginRequiredMixin, StaffUserMixin, EventAdminMixin, CreateView):
    model = Event
    template_name = 'studioadmin/event_create_update.html'
    context_object_name = 'event'

    def get_form_class(self):
        return OnlineTutorialAdminForm if self.kwargs["ev_type"] == "online_tutorial" else EventAdminForm

    def get_form_kwargs(self, **kwargs):
        form_kwargs = super().get_form_kwargs(**kwargs)
        form_kwargs['ev_type'] = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["abbr"]
        return form_kwargs

    def get_context_data(self, **kwargs):
        context = super(EventAdminCreateView, self).get_context_data(**kwargs)
        context['type'] = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["name"]
        context['sidenav_selection'] = 'add_{}'.format(EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["sidenav"])
        return context

    def form_valid(self, form):
        event = self.add_new_category(form)
        msg_ev_type = EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["name"].title()
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
        return reverse(f'studioadmin:{EVENT_TYPE_PARAM_MAPPING[self.kwargs["ev_type"]]["sidenav_plural"]}')


@login_required
@staff_required
def cancel_event_view(request, slug):
    event = get_object_or_404(Event, slug=slug)
    ev_type = event.event_type.readable_name.lower()

    all_open_bookings = event.bookings.filter(status='OPEN')
    open_bookings = [bk for bk in all_open_bookings if not bk.no_show]
    no_shows_all = [bk for bk in all_open_bookings if bk.no_show]
    no_shows = [bk for bk in no_shows_all if bk.paid or bk.deposit_paid]
    open_block_bookings = [
        bk for bk in open_bookings if bk.block and not bk.free_class and not bk.block.expired
    ]
    open_membership_bookings = [
        bk for bk in open_bookings if bk.membership
    ]
    open_expired_block_bookings = [
        bk for bk in open_bookings if bk.block and not bk.free_class and bk.block.expired
    ]
    open_unpaid_bookings = [
        bk for bk in open_bookings if not bk.deposit_paid and not bk.paid
    ]
    open_free_non_block = [
        bk for bk in open_bookings if bk.free_class and not bk.block
    ]
    open_free_block = [bk for bk in open_bookings if bk.free_class and bk.block]
    open_direct_paid_deposit_only = [
        bk for bk in open_bookings if not bk.block
        and not bk.free_class and bk.deposit_paid and not bk.paid
    ]
    open_direct_paid = [
        bk for bk in open_bookings if not bk.block and not bk.membership
        and not bk.free_class and bk.paid
    ]

    if request.method == 'POST':
        if 'confirm' in request.POST:
            transfer_direct_paid = request.POST.get('direct_paid_action') == 'transfer'

            for booking in open_bookings:
                transfer_block_created = False
                block_expires_soon = False
                block_paid = booking in open_block_bookings
                membership_paid = booking in open_membership_bookings
                free_block = booking in open_free_block
                expired_block = booking in open_expired_block_bookings
                direct_paid = booking in open_direct_paid or \
                              booking in open_free_non_block
                deposit_only_paid = booking in open_direct_paid_deposit_only
                block_expiry_date = booking.block.expiry_date.strftime('%d %b %Y') \
                    if booking.block else None

                if booking.membership:
                    booking.membership = None
                    booking.paid = False
                    booking.payment_confirmed = False

                elif booking.block and not booking.block.expired:
                    one_month_ahead = timezone.now() + relativedelta(months=1)
                    if booking.block.expiry_date < one_month_ahead:
                        block_expires_soon = True

                    booking.block = None
                    booking.deposit_paid = False
                    booking.paid = False
                    booking.payment_confirmed = False
                    # in case this was paid with a free class block
                    booking.free_class = False

                elif (direct_paid and transfer_direct_paid) \
                        or (booking.block and booking.block.expired):
                    # direct paid = paypal and free non-block paid
                    # create transfer block and make this booking unpaid
                    if booking.event.event_type.event_type != 'EV':
                        block_type = BlockType.get_transfer_block_type(booking.event.event_type)
                        Block.objects.create(
                            block_type=block_type, user=booking.user,
                            transferred_booking_id=booking.id
                        )
                        transfer_block_created = True

                        booking.block = None  # need to reset block if booked
                        # with block that's now expired
                        booking.deposit_paid = False
                        booking.paid = False
                        booking.payment_confirmed = False
                        booking.free_class = False

                booking.status = "CANCELLED"
                booking.save()

                try:
                    # send notification email to user
                    host = 'http://{}'.format(request.get_host())
                    ctx = {
                        'host': host,
                        'event_type': ev_type,
                        'block_paid': block_paid,
                        'membership_paid': membership_paid,
                        'direct_paid': direct_paid or deposit_only_paid,
                        'free_block': free_block,
                        'expired_block': expired_block,
                        'block_expires_soon': block_expires_soon,
                        'block_expiry_date': block_expiry_date,
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
                host = 'http://{}'.format(request.get_host())
                # send email to studio
                ctx = {
                    'host': host,
                    'event_type': ev_type,
                    'transfer_direct_paid': transfer_direct_paid,
                    'open_bookings': open_bookings,
                    'open_membership_bookings': open_membership_bookings,
                    'open_direct_paid_bookings': open_direct_paid,
                    'open_block_bookings': open_block_bookings,
                    'open_expired_block_bookings': open_expired_block_bookings,
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
        'open_membership_bookings': open_membership_bookings,
        'open_expired_block_bookings': open_expired_block_bookings,
        'open_deposit_only_paid_bookings': open_direct_paid_deposit_only,
        'open_unpaid_bookings': open_unpaid_bookings,
        'open_free_non_block_bookings': open_free_non_block,
        'open_free_block_bookings': open_free_block,
        'no_shows': no_shows
    }

    return TemplateResponse(
        request, 'studioadmin/cancel_event.html', context
    )


@login_required
@staff_required
def clone_event(request, slug):
    event = get_object_or_404(Event, slug=slug)
    original_id = event.id
    cloned_event = event
    cloned_event.id = None
    set_cloned_name(Event, event, clone_event)

    cloned_event.name = f"[CLONED] {event.name}"
    split_name = cloned_event.name.rsplit("_", 1)
    base_name = split_name[0]
    try:
        counter = int(split_name[1])
    except (ValueError, IndexError):
        counter = 1
    while Event.objects.filter(name=cloned_event.name).exists():
        cloned_event.name = f"{base_name}_{counter}"
        counter += 1
    # set defaults for cloned event
    cloned_event.slug = None
    cloned_event.cancelled = False
    cloned_event.visible_on_site = False
    cloned_event.booking_open = False
    cloned_event.payment_open = False
    cloned_event.save()

    original_event = Event.objects.get(id=original_id)
    cloned_event.categories.add(*original_event.categories.all())
    event_type_string, = {event_type["sidenav_plural"] for event_type in EVENT_TYPE_PARAM_MAPPING.values() if event_type["abbr"] == event.event_type.event_type}
    messages.success(request, f"{original_event.name} cloned to {cloned_event.name}; booking/payment not open yet")
    return HttpResponseRedirect(reverse(f"studioadmin:{event_type_string}"))


@login_required
@staff_required
def open_all_events(request, event_type):
    event_type_abbr = EVENT_TYPE_PARAM_MAPPING[event_type]["abbr"]
    suffix = 'es' if event_type_abbr == "CL" else "s"
    event_type_plural = EVENT_TYPE_PARAM_MAPPING[event_type]["name"] + suffix
    events_to_open = Event.objects.filter(
        event_type__event_type=event_type_abbr, date__gte=timezone.now(), cancelled=False
    )
    newly_visible = list(events_to_open.filter(visible_on_site=False))
    events_to_open.update(booking_open=True, payment_open=True, visible_on_site=True)
    messages.info(request, f"All upcoming {event_type_plural} are now visible and open for booking and payments")
    ActivityLog.objects.create(log=f"All upcoming {event_type_plural} opened by admin user {request.user.username}")
    
    # email members
    if newly_visible:
        send_new_classes_email_to_members(request, newly_visible)

    return HttpResponseRedirect(reverse(f"studioadmin:{event_type}"))
