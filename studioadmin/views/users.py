from datetime import datetime
from datetime import timezone as dt_timezone

import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.urls import reverse
from django.db.models import Count, Q
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, \
    get_object_or_404, render
from django.views.generic import CreateView, ListView, UpdateView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from booking.models import AllowedGroup, Booking,  Block, BlockType, EventType, WaitingListUser
from booking.email_helpers import send_support_email,  send_waiting_list_email

from common.mailchimp_utils import update_mailchimp
from common.views import _set_pagination_context

from studioadmin.forms import AddBookingForm, EditPastBookingForm, \
    EditBookingForm, UserBlockFormSet,  UserListSearchForm, AttendanceSearchForm

from studioadmin.views.helpers import InstructorOrStaffUserMixin,  \
    staff_required, StaffUserMixin, get_page
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


NAME_FILTERS = (
    'All', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
)


def _get_name_filter_available(queryset):
    names_list = queryset.distinct().values_list('first_name', flat=True)
    letter_set = set([name[0].lower() for name in names_list if name])

    name_filter_options = []
    for option in NAME_FILTERS:
        if option == "All":
            name_filter_options.append({'value': 'All',  'available': True})
        else:
            name_filter_options.append(
                {
                    'value': option,
                    'available': option.lower() in letter_set
                }
            )
    return name_filter_options


class UserListView(LoginRequiredMixin,  InstructorOrStaffUserMixin,  ListView):

    model = User
    template_name = 'studioadmin/user_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        reset = self.request.GET.get('reset')
        if reset:
            queryset = User.objects.all().order_by('first_name')
        else:
            search_text = self.request.GET.get('search')
            filter = self.request.GET.get('filter', self.request.GET.get('pfilter'))
            group_name = self.request.GET.get('group_filter', self.request.GET.get('pgroup_filter'))

            if group_name and group_name.lower() != 'all' and not reset:
                try:
                    group = Group.objects.get(name__iexact=group_name)
                    queryset = group.user_set.all().order_by('first_name')
                except Group.DoesNotExist:
                    queryset = User.objects.all().order_by('first_name')
            else:
                queryset = User.objects.all().order_by('first_name')

            if search_text:
                queryset = queryset.filter(
                    Q(first_name__icontains=search_text) |
                    Q(last_name__icontains=search_text) |
                    Q(username__icontains=search_text)
                )

            if filter and filter.lower() != 'all':
                queryset = queryset.filter(first_name__istartswith=filter)

        return queryset

    def get_context_data(self):
        context = super(UserListView,  self).get_context_data()
        queryset = self.get_queryset()
        paginator = Paginator(queryset, 30)

        page = get_page(self.request, paginator)
        context["page_obj"] = page
        context["users"] = page.object_list
        _set_pagination_context(context)

        context['sidenav_selection'] = 'users'
        context['search_submitted'] = self.request.GET.get('search_submitted')

        search_text = self.request.GET.get('search',  '')
        reset = self.request.GET.get('reset')
        context['filter_options'] = _get_name_filter_available(queryset)

        if reset:
            search_text = ''
            context['active_filter'] = "All"
            context['active_group'] = "All"
        else:
            context['active_filter'] = self.request.GET.get('filter', self.request.GET.get('pfilter', "All"))
            context['active_group'] = self.request.GET.get('group_filter', self.request.GET.get('pgroup_filter', "All"))

        form = UserListSearchForm(initial={'search': search_text})
        context['form'] = form
        num_results = queryset.count()
        total_users = User.objects.count()
        context['num_results'] = num_results
        context['total_users'] = total_users

        context["allowed_groups"] = AllowedGroup.objects.exclude(id=AllowedGroup.default_group().id)
        return context


@login_required
@staff_required
def users_status(request):
    date_format = '%d %b %Y'
    if request.method == "POST":
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
    else:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

    if not start_date_str:
        # default to beginning of current month
        start_date = timezone.now().date().replace(day=1)
        start_date_str = start_date.strftime(date_format)
    else:
        start_date = datetime.strptime(start_date_str, date_format).replace(tzinfo=dt_timezone.utc)

    if not end_date_str:
        # default to now
        end_date = timezone.now()
        end_date_str = end_date.strftime(date_format)
    else:
        end_date = datetime.strptime(end_date_str, date_format).replace(hour=23, minute=59, tzinfo=dt_timezone.utc)
        
    form = AttendanceSearchForm(
        {"start_date": start_date_str, "end_date": end_date_str}
    )
    bookings = Booking.objects \
        .filter(event__date__gte=start_date, attended=True)\
        .filter(event__date__lte=end_date)

    users_with_bookings = bookings.distinct("user_id")
    subtype_order = {
        "Pole level class": 1,
        "Pole practice": 2,
        "Private": 3
    }
    event_subtypes = list(
        bookings.distinct("event__event_type__subtype")
        .values_list("event__event_type__subtype", flat=True)
    )
    event_subtypes.sort(key=lambda x: subtype_order.get(x, 9))
    default_user_dict = {subtype: 0 for subtype in event_subtypes}

    counts_by_user = {}
    for booking in users_with_bookings:
        user = booking.user
        counts = bookings.filter(user_id=user.id) \
            .values("event__event_type__subtype") \
            .annotate(count=Count("event__event_type__subtype"))
        user_dict = {**default_user_dict}
        for count_item in counts:
            user_dict[count_item["event__event_type__subtype"]] = count_item["count"]
        counts_by_user[user] = user_dict

    sorted_counts = dict(
        sorted(
            counts_by_user.items(),
            key=lambda x: tuple(x[1][subtype] for subtype in event_subtypes),
            reverse=True
        )
    )

    paginator = Paginator(list(sorted_counts.items()), 100)
    page = get_page(request, paginator)

    context = {
        "user_counts": dict(page.object_list),
        "event_subtypes": event_subtypes,
        "number_of_subtypes": len(event_subtypes),
        "form": form,
        'page_obj': page,
        'is_paginated': paginator.num_pages > 1,
        'sidenav_selection': 'attendance'
    }
    _set_pagination_context(context)
    return render(
        request,
        "studioadmin/users_attendance.html",
        context
    )


@login_required
@staff_required
def toggle_subscribed(request,  user_id):
    user_to_change = User.objects.get(id=user_id)
    group, _ = Group.objects.get_or_create(name='subscribed')
    if user_to_change.subscribed():
        group.user_set.remove(user_to_change)
        ActivityLog.objects.create(
            log="User {} {} ({}) unsubscribed from mailing list by "
                "admin user {}".format(
                user_to_change.first_name,
                user_to_change.last_name,
                user_to_change.username,
                request.user.username
            )
        )
        update_mailchimp(user_to_change, 'unsubscribe')
        ActivityLog.objects.create(
            log='User {} {} ({}) has been unsubscribed from MailChimp'.format(
                user_to_change.first_name, user_to_change.last_name,
                user_to_change.username
            )
        )
    else:
        group.user_set.add(user_to_change)
        ActivityLog.objects.create(
            log="User {} {} ({}) subscribed to mailing list by "
                "admin user {}".format(
                user_to_change.first_name,
                user_to_change.last_name,
                user_to_change.username,
                request.user.username
            )
        )
        update_mailchimp(user_to_change, 'subscribe')
        ActivityLog.objects.create(
            log='User {} {} ({}) has been subscribed to MailChimp'.format(
                user_to_change.first_name, user_to_change.last_name,
                user_to_change.username
            )
        )
    return render(
        request,
        "studioadmin/includes/subscribed_button.html",
        {"user": user_to_change}
    )


@login_required
@staff_required
def user_modal_bookings_view(request, user_id, past=False):
    user = get_object_or_404(User,  id=user_id)

    if past:
        all_bookings = Booking.objects.select_related('event', 'user')\
            .filter(
                user=user, event__date__lt=timezone.now()
            ).order_by('-event__date')
    else:
        all_bookings = Booking.objects.select_related('event', 'user')\
        .filter(
            user=user, event__date__gt=timezone.now()
        ).order_by('event__date')

    paginator = Paginator(all_bookings, 20)
    page = get_page(request, paginator)
    bookings = page.object_list

    template = 'studioadmin/user_booking_list.html'
    return TemplateResponse(
        request,  template,  {
            'bookings': bookings,  'page_obj': page, 
            "paginator_range": page.paginator.get_elided_page_range(page.number),
            'user': user,
            'sidenav_selection': 'users',
            'booking_status': 'past' if past else 'future',
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
                messages.info(request,  "No changes were made")
            else:
                for form in userblockformset:
                    if form.has_changed():

                        block = form.save(commit=False)
                        if not block.start_date:
                            block.start_date = timezone.now().replace()

                        if 'DELETE' in form.changed_data:
                            messages.success(
                                request,  mark_safe(
                                    'Block <strong>{}</strong> has been '
                                    'deleted!  Any bookings made with this '
                                    'block have been changed to unpaid.  '
                                    'Please inform user {} ({})'.format(
                                        block,  block.user.username, 
                                        block.user.email
                                    )
                                )
                            )
                            ActivityLog.objects.create(
                                log='Block {} (id {}) deleted by admin user {}'.format(
                                form.instance,  form.instance.id,  request.user.username)
                            )
                            block.delete()
                        else:
                            new = False if form.instance.id else True
                            msg = 'created' if new else 'updated'

                            messages.success(
                                request, 
                                'Block for {} has been {}'.format(
                                    block.block_type.event_type,  msg
                                )
                            )
                            block.save()
                            ActivityLog.objects.create(
                                log='Block id {} ({}),  user {},  {}'
                                        ' by admin user {}'.format(
                                    block.id,  block.block_type, 
                                    block.user.username,  msg, 
                                    request.user.username
                                )
                            )

                userblockformset.save(commit=False)

            return HttpResponseRedirect(
                reverse('studioadmin:user_blocks_list', 
                        kwargs={'user_id': user.id}
                        ) + '?page=' + request.POST.get('page', '')
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

    queryset = Block.objects.filter(
        user=user).order_by('-start_date')

    paginator = Paginator(queryset, 10)
    page = get_page(request, paginator)
    userblockformset = UserBlockFormSet(
        instance=user,
        queryset=queryset.filter(id__in=page.object_list.values_list("id", flat=True)),
        user=user
    )
    template = 'studioadmin/user_block_list.html'
    return TemplateResponse(
        request,  template,  {
            'userblockformset': userblockformset,  'user': user, 
            'sidenav_selection': 'users', 'page_obj': page,
            "paginator_range": page.paginator.get_elided_page_range(page.number)
        }
    )


class MailingListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = User
    template_name = 'studioadmin/mailing_list.html'
    context_object_name = 'users'
    paginate_by = 30

    def get_context_data(self):
        context_data = super().get_context_data()
        context_data['sidenav_selection'] = 'mailing_list'
        _set_pagination_context(context_data)
        return context_data

    def get_queryset(self, **kwargs):
        group, _ = Group.objects.get_or_create(name='subscribed')
        return group.user_set.all().order_by('first_name', 'last_name')


def unsubscribe(request, user_id):
    user_to_change = User.objects.get(id=user_id)
    group = Group.objects.get(name='subscribed')
    group.user_set.remove(user_to_change)
    messages.success(
        request,
        "User {} {} ({}) unsubscribed from mailing list.".format(
            user_to_change.first_name,
            user_to_change.last_name,
            user_to_change.username
        )
    )
    ActivityLog.objects.create(
        log="User {} {} ({}) unsubscribed from mailing list by "
            "admin user {}".format(
            user_to_change.first_name,
            user_to_change.last_name,
            user_to_change.username,
            request.user.username
            )
    )
    user_to_change.save()
    update_mailchimp(user_to_change, 'unsubscribe')
    ActivityLog.objects.create(
        log='User {} {} ({}) has been unsubscribed from MailChimp'.format(
            user_to_change.first_name, user_to_change.last_name,
            user_to_change.username
        )
    )
    return HttpResponseRedirect(reverse('studioadmin:mailing_list'))


class BookingEditPastView(UpdateView):

    model = Booking
    template_name = 'studioadmin/user_booking_add_edit.html'
    form_class = EditPastBookingForm

    def form_valid(self, form):
        booking = form.save(commit=False)
        if form.has_changed():
            messages.success(self.request, 'Saved!')
            booking.save()
        else:
            messages.success(self.request, 'No changes made')
        return HttpResponseRedirect(reverse("studioadmin:user_past_bookings_list", args=(booking.user.id,)))


class BookingEditView(BookingEditPastView):
    form_class = EditBookingForm

    def form_valid(self, form):
        booking = process_user_booking_updates(form, self.request)
        return HttpResponseRedirect(reverse("studioadmin:user_upcoming_bookings_list", args=(booking.user.id,)))


class BookingAddView(CreateView):

    model = Booking
    template_name = 'studioadmin/user_booking_add_edit.html'
    form_class = AddBookingForm

    def get_form_user(self):
        return User.objects.get(id=self.kwargs['user_id'])

    def get_context_data(self, *args, **kwargs):
        context = super(BookingAddView, self).get_context_data(*args, **kwargs)
        context['form_user'] = self.get_form_user()
        context["new"] = True
        return context

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super(BookingAddView, self).get_form_kwargs(*args, **kwargs)
        kwargs['user'] = self.get_form_user()
        return kwargs

    def form_valid(self, form):
        booking = process_user_booking_updates(form, self.request)
        return HttpResponseRedirect(reverse("studioadmin:user_upcoming_bookings_list", args=(booking.user.id,)))


def process_user_booking_updates(form, request):
    # The form clean removes block/membership if status is cancelled
    pre_save_booking = Booking.objects.get(id=form.instance.id) if form.instance.id else None
    had_membership_or_block = pre_save_booking and (pre_save_booking.block or pre_save_booking.membership)
    booking = form.save(commit=False)
    if form.has_changed():
        if form.changed_data == ['send_confirmation']:
            messages.info(
                request,  "'Send confirmation' checked for '{}' "
                "but no changes were made; email has not been "
                "sent to user.".format(form.instance.event))
        else:
            extra_msgs = []  # these will be displayed as a list in the email to the user
            action = 'updated' if pre_save_booking else 'created'
            transfer_block_created = False

            if 'status' in form.changed_data and action == 'updated':
                if booking.status == 'CANCELLED':
                    if pre_save_booking.paid \
                            and booking.event.event_type.event_type != 'EV':
                        block_type = BlockType.get_transfer_block_type(booking.event.event_type)
                        Block.objects.create(
                            block_type=block_type, user=booking.user,
                            transferred_booking_id=booking.id
                        )
                        transfer_block_created = True
                    booking.deposit_paid = False
                    booking.paid = False
                    booking.payment_confirmed = False
                    booking.free_class = False
                    action = 'cancelled'
                elif booking.status == 'OPEN':
                    action = 'reopened'

                extra_msgs.append("Booking status changed to {}".format(action))

            elif 'no_show' in form.changed_data and action == 'updated' and pre_save_booking.status == 'OPEN':
                action = 'cancelled' if booking.no_show else 'reopened'
                extra_msgs.append("Booking {} as 'no-show'".format(action))

            if 'deposit_paid' in form.changed_data:
                if booking.deposit_paid:
                    extra_msgs.append("Booking payment status changed to 'deposit paid'")

            if 'paid' in form.changed_data:
                if booking.paid:
                    # assume that if booking is being done via studioadmin, marking paid also
                    # means payment is confirmed
                    booking.payment_confirmed = True
                    extra_msgs.append(
                        "Booking payment status changed to 'fully paid and confirmed'"
                    )
                else:
                    booking.payment_confirmed = False
            
            if not booking.block and 'block' in form.changed_data:
                if booking.membership:
                    messages.info(
                        request,
                        f'Payment method changed from block to membership for {booking.event}',
                    )
                else:
                    booking.paid = False
                    booking.payment_confirmed = False
                    messages.info(
                    request,
                    f'Block removed for {booking.event}; booking is now marked as unpaid'
                )
            
            if not booking.membership and 'membership' in form.changed_data:
                if booking.block:
                    messages.info(
                        request,
                        f'Payment method changed from membership to block for {booking.event}',
                    )
                else:
                    booking.paid = False
                    booking.payment_confirmed = False
                    messages.info(
                        request,
                        f'Membership removed for {booking.event}; booking is now marked as unpaid'
                    )

            booking.save()

            set_as_free = 'free_class' in form.changed_data and booking.free_class

            send_confirmation_msg = ""
            if 'send_confirmation' in form.changed_data:
                # send confirmation email
                host = 'http://{}'.format(request.META.get('HTTP_HOST'))
                # send email to studio
                ctx = {
                    'host': host,
                    'event': booking.event,
                    'user': booking.user,
                    'action': action,
                    'set_as_free': set_as_free,
                    'extra_msgs': extra_msgs
                }
                send_mail('{} Your booking for {} has been {}'.format(
                    settings.ACCOUNT_EMAIL_SUBJECT_PREFIX, booking.event, action
                    ),
                    get_template('studioadmin/email/booking_change_confirmation.txt').render(ctx),
                    settings.DEFAULT_FROM_EMAIL,
                    [booking.user.email],
                    html_message=get_template(
                        'studioadmin/email/booking_change_confirmation.html'
                        ).render(ctx),
                    fail_silently=False)
                send_confirmation_msg = "and confirmation email sent to user"

            messages.success(
                request,
                'Booking for {} has been {} {}'.format(
                    booking.event,  action,  send_confirmation_msg
                )
            )
            if set_as_free:
                extra_msg = "and marked as free class"
            elif transfer_block_created:
                extra_msg = "and transfer block created as credit"
            else:
                extra_msg = ''

            ActivityLog.objects.create(
                log='Booking id {} (user {}) for "{}" {} by admin user {} {}'.format(
                    booking.id,  booking.user.username,  booking.event,
                    action,  request.user.username, extra_msg
                )
            )

            if action == 'reopened':
                messages.info(
                    request,
                    mark_safe(
                        'Note: this booking was previously cancelled and has now been reopened. '
                        '<span class="cancel-warning">Payment status has not been automatically '
                        'updated. Please review the booking and update if paid.</span>'
                    )
                )
            elif action == 'cancelled':
                if transfer_block_created:
                    messages.info(
                        request,
                        mark_safe(
                            "Note: this booking has been cancelled. The booking has automatically been "
                            "marked as unpaid and a transfer block has been created as credit.  If you wish to "
                            "refund the user instead, go to the <a href={}>user's blocks</a> and delete "
                            "the transfer block first.".format(
                                reverse('studioadmin:user_blocks_list', args=[booking.user.id])
                            )
                        )
                    )
                elif had_membership_or_block:
                    messages.info(
                        request,
                        'Note: this booking has been cancelled. The booking has automatically been marked as '
                        'unpaid and the block/membership used has been updated.'
                    )
                else:
                    messages.info(
                        request,  'Note: this booking has been cancelled. The booking has automatically '
                        'been marked as unpaid (refunded).')

                waiting_list_users = WaitingListUser.objects.filter(
                    event=booking.event
                )
                if waiting_list_users:
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
                            ',  '.join(
                                [wluser.user.username \
                                    for wluser in \
                                    waiting_list_users]
                            ),
                            booking.event
                        )
                    )

            if action == 'created' or action == 'reopened':
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

    return booking


@login_required
@staff_required
def toggle_permission(request,  user_id, allowed_group_id):
    user_to_change = get_object_or_404(User, pk=user_id)
    allowed_group = get_object_or_404(AllowedGroup, pk=allowed_group_id)

    if allowed_group.has_permission(user_to_change):
        allowed_group.remove_user(user_to_change)
        ActivityLog.objects.create(
            log=f"User {user_to_change.username} removed from allowed group '{allowed_group}' by "
                f"admin user {request.user.username}"
        )
    else:
        allowed_group.add_user(user_to_change)
        ActivityLog.objects.create(
            log=f"User {user_to_change.username} added to allowed group {allowed_group} by "
                f"admin user {request.user.username}"
        )
        if allowed_group.group.name.lower() == "experienced":
            send_mail(
                "Account upgraded: important information",
                get_template('studioadmin/email/experienced_group_permission.txt').render(),
                settings.DEFAULT_FROM_EMAIL,
                [user_to_change.email],
                html_message=get_template('studioadmin/email/experienced_group_permission.html').render(),
                fail_silently=False
            )
            ActivityLog.objects.create(
                log=f"Room hire T&C email send to user {user_to_change.email}"
            )

    return render(
        request,
        "studioadmin/includes/toggle_permission_button.html",
        {"user": user_to_change, "allowed_group": allowed_group}
    )


def user_memberships_list(request, user_id):
    user = get_object_or_404(User,  id=user_id)
    template = 'studioadmin/user_memberships_list.html'
    return TemplateResponse(
        request,  template,  {
            'user': user, 
            'sidenav_selection': 'users',
        }
    )
