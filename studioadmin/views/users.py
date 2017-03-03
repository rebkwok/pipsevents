import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User,  Permission
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render_to_response
from django.views.generic import ListView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.core.mail import send_mail

from braces.views import LoginRequiredMixin

from accounts.models import PrintDisclaimer

from booking.models import Booking,  Block, BlockType, WaitingListUser
from booking.email_helpers import send_support_email,  send_waiting_list_email

from studioadmin.forms import UserBookingFormSet,  \
    UserBlockFormSet,  UserListSearchForm

from studioadmin.views.helpers import InstructorOrStaffUserMixin,  \
    staff_required, StaffUserMixin
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
    paginate_by = 30

    def get_queryset(self):
        queryset = User.objects.all().order_by('first_name')
        reset = self.request.GET.get('reset')
        search_submitted = self.request.GET.get('search_submitted')
        search_text = self.request.GET.get('search')
        filter = self.request.GET.get('filter')

        if reset or (search_submitted and not search_text) or \
                (not reset and not search_submitted and not filter):
            queryset = queryset
        elif search_text:
            queryset = queryset.filter(
                Q(first_name__icontains=search_text) |
                Q(last_name__icontains=search_text) |
                Q(username__icontains=search_text)
            )

        if filter and filter != 'All':
            queryset = queryset.filter(first_name__istartswith=filter)

        return queryset

    def get_context_data(self):
        queryset = self.get_queryset()
        context = super(UserListView,  self).get_context_data()
        context['sidenav_selection'] = 'users'
        context['search_submitted'] = self.request.GET.get('search_submitted')
        context['active_filter'] = self.request.GET.get('filter',  'All')
        search_text = self.request.GET.get('search',  '')
        reset = self.request.GET.get('reset')
        context['filter_options'] = _get_name_filter_available(queryset)

        num_results = queryset.count()
        total_users = User.objects.count()

        if reset:
            search_text = ''
        form = UserListSearchForm(
            initial={
                'search': search_text})
        context['form'] = form
        context['num_results'] = num_results
        context['total_users'] = total_users
        return context


@login_required
@staff_required
def toggle_regular_student(request,  user_id):
    user_to_change = User.objects.get(id=user_id)
    perm = Permission.objects.get(codename='is_regular_student')
    if not user_to_change.is_superuser:
        if user_to_change.is_regular_student():
            user_to_change.user_permissions.remove(perm)
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
            ActivityLog.objects.create(
                log="{} {} ({}) has been given 'regular student' "
                "status by admin user {}".format(
                    user_to_change.first_name,
                        user_to_change.last_name,
                        user_to_change.username,
                        request.user.username
                    )
            )
    # get the user again, otherwise permissions are cached
    return render_to_response(
        "studioadmin/includes/regular_student_button.txt",
        {"user": User.objects.get(id=user_to_change.id)}
    )


@login_required
@staff_required
def toggle_print_disclaimer(request,  user_id):
    user_to_change = User.objects.get(id=user_id)
    disclaimer = PrintDisclaimer.objects.filter(user=user_to_change)
    if disclaimer:
        disclaimer.delete()
        ActivityLog.objects.create(
            log="Print disclaimer has been removed for "
            "{} {} ({}) by admin user {}".format(
                user_to_change.first_name,
                user_to_change.last_name,
                user_to_change.username,
                request.user.username
            )
        )
    else:
        PrintDisclaimer.objects.create(user=user_to_change)
        ActivityLog.objects.create(
            log="Print disclaimer recorded for {} {} ({}) "
            "by admin user {}".format(
                user_to_change.first_name,
                    user_to_change.last_name,
                    user_to_change.username,
                    request.user.username
                )
        )
    return render_to_response(
        "studioadmin/includes/print_disclaimer_button.txt",
        {"user": user_to_change}
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
    return render_to_response(
        "studioadmin/includes/subscribed_button.txt",
        {"user": user_to_change}
    )


@login_required
@staff_required
def user_bookings_view(request,  user_id):
    user = get_object_or_404(User,  id=user_id)

    if request.method == 'POST':
        userbookingformset = UserBookingFormSet(
            request.POST.copy(),  instance=user,  user=user, 
        )
        if userbookingformset.is_valid():
            if not userbookingformset.has_changed() and \
                    request.POST.get('formset_submitted'):
                messages.info(request,  "No changes were made")
            else:
                for form in userbookingformset:
                    if form.is_valid():
                        if form.has_changed():
                            if form.changed_data == ['send_confirmation']:
                                messages.info(
                                    request,  "'Send confirmation' checked for '{}' "
                                    "but no changes were made; email has not been "
                                    "sent to user.".format(form.instance.event))
                            else:
                                extra_msgs = [] # these will be displayed as a list in the email to the user

                                booking = form.save(commit=False)
                                event_was_full = booking.event.spaces_left == 0
                                action = 'updated' if form.instance.id else 'created'
                                transfer_block_created = False
                                block_removed = False

                                if 'status' in form.changed_data and action == 'updated':
                                    if booking.status == 'CANCELLED':
                                        if booking.block:
                                            booking.block = None
                                            block_removed = True
                                        elif booking.paid \
                                                and booking.event.event_type.event_type != 'EV':
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
                                        booking.deposit_paid = False
                                        booking.paid = False
                                        booking.payment_confirmed = False
                                        booking.free_class = False
                                        action = 'cancelled'
                                    elif booking.status == 'OPEN':
                                        action = 'reopened'

                                    extra_msgs.append("Booking status changed "
                                                      "to {}".format(action)
                                                      )

                                elif 'no_show' in form.changed_data \
                                    and action == 'updated' \
                                        and booking.status == 'OPEN':
                                    action = 'cancelled' if booking.no_show \
                                        else 'reopened'
                                    extra_msgs.append(
                                        "Booking {} as 'no-show'".format(action)
                                    )

                                if booking.block:
                                    booking.paid = True
                                    booking.payment_confirmed = True
                                elif 'block' in form.changed_data:
                                    booking.block = None
                                    booking.paid = False
                                    booking.payment_confirmed = False

                                # check for existence of free child block on pre-saved booking
                                has_free_block_pre_save = False
                                if booking.block and booking.block.children.exists():
                                    has_free_block_pre_save = True

                                if 'deposit_paid' in form.changed_data:
                                    if booking.deposit_paid:
                                        extra_msgs.append(
                                            "Booking payment status changed to "
                                            "'deposit paid'"
                                        )

                                if 'paid' in form.changed_data:
                                    if booking.paid:
                                        # assume that if booking is being done via
                                        # studioadmin,  marking paid also means payment
                                        # is confirmed
                                        booking.payment_confirmed = True
                                        extra_msgs.append(
                                            "Booking payment status changed to "
                                            "'fully paid and confirmed'"
                                        )
                                    else:
                                        booking.payment_confirmed = False

                                booking.save()

                                set_as_free = 'free_class' in \
                                              form.changed_data and \
                                              booking.free_class
                                if 'send_confirmation' in form.changed_data:
                                    try:
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
                                            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX,  booking.event,  action
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
                                            e,  __name__,  "user_booking_list - "
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
                                    log='Booking id {} (user {}) for "{}" {} '
                                            'by admin user {} {}'.format(
                                        booking.id,  booking.user.username,  booking.event, 
                                        action,  request.user.username, 
                                       extra_msg
                                    )
                                )

                                if not booking.block \
                                         and 'block' in form.changed_data:
                                     messages.info(
                                         request, 
                                         'Block removed for {}; booking is '
                                         'now marked as unpaid'.format(
                                             booking.event
                                         ), 
                                     )

                                if action == 'reopened':
                                    messages.info(
                                        request,  mark_safe(
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
                                    if transfer_block_created:
                                        messages.info(
                                            request,
                                            mark_safe("Note: this booking has been "
                                            "cancelled. The booking has "
                                            "automatically been marked as "
                                            "unpaid and a transfer block "
                                            "has been created as credit.  If you wish to "
                                            "refund the user instead, go "
                                            "to the <a href={}>user's blocks</a> "
                                            "and delete "
                                            "the transfer block first.".format(
                                                reverse(
                                                    'studioadmin:user_blocks_list',
                                                    args=[booking.user.id]
                                                )
                                            ))
                                        )
                                    elif block_removed:
                                        messages.info(
                                            request,
                                            'Note: this booking has been '
                                            'cancelled. The booking has '
                                            'automatically been marked as '
                                            'unpaid and the block '
                                            'used has been updated.'
                                        )
                                    else:
                                        messages.info(
                                            request,  'Note: this booking has been '
                                            'cancelled. The booking has automatically '
                                            'been marked as unpaid (refunded).')

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
                                                        ',  '.join(
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
                                                    e,  __name__, 
                                                    "Studioadmin user booking list - waiting list email"
                                                )

                                if action == 'created' or action == 'reopened':
                                    try:
                                        waiting_list_user = WaitingListUser.objects.get(
                                            user=booking.user,  event=booking.event
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

                                if booking.block and not booking.block.active_block():
                                    if booking.block.children.exists() \
                                            and not has_free_block_pre_save:
                                         messages.info(
                                             request, 
                                            'You have added the last booking '
                                            'to a 10 class block; free class '
                                            'block has been created.'
                                         )

                    userbookingformset.save(commit=False)

            return HttpResponseRedirect(
                reverse(
                    'studioadmin:user_bookings_list', 
                    kwargs={'user_id': user.id}
                )
            )
        else:
            messages.error(
                request, 
                mark_safe(
                    "Please correct the following errors:\n{}".format(
                        '\n'.join(
                            [
                                "{}".format(error)
                                for error in userbookingformset.errors
                            ]
                        )
                    )
                )
            )
    else:
        all_bookings = Booking.objects.select_related('event', 'user')\
            .filter(
                user=user, event__date__gte=timezone.now()
            ).order_by('event__date')

        userbookingformset = UserBookingFormSet(
            instance=user, 
            queryset=all_bookings,
            user=user
        )

    template = 'studioadmin/user_booking_list.html'
    return TemplateResponse(
        request,  template,  {
            'userbookingformset': userbookingformset,  'user': user, 
            'sidenav_selection': 'users', 
            'booking_status': 'future'
        }
    )


@login_required
@staff_required
def user_past_bookings_view(request,  user_id):
    user = get_object_or_404(User,  id=user_id)

    all_bookings = Booking.objects.select_related('event', 'user')\
        .filter(
            user=user, event__date__lt=timezone.now()
        ).order_by('-event__date')

    paginator = Paginator(all_bookings, 20)
    page = request.GET.get('page')
    try:
        page = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        page = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        page = paginator.page(paginator.num_pages)
    bookings = page.object_list

    # TODO
    # include edit link for each booking? Edit on separate page or show ajax

    template = 'studioadmin/user_booking_list.html'
    return TemplateResponse(
        request,  template,  {
            'bookings': bookings,  'page': page, 'user': user,
            'sidenav_selection': 'users',
            'booking_status': 'past',
            'total_count': paginator.count,
            'current_count': bookings.count()
        }
    )



@login_required
@staff_required
def user_blocks_view(request,  user_id):

    user = get_object_or_404(User,  id=user_id)

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
    page = request.GET.get('page')
    try:
        page = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        page = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        page = paginator.page(paginator.num_pages)

    queryset = queryset.filter(id__in=[obj.id for obj in page])
    userblockformset = UserBlockFormSet(
        instance=user,
        queryset=queryset,
        user=user
    )

    template = 'studioadmin/user_block_list.html'
    return TemplateResponse(
        request,  template,  {
            'userblockformset': userblockformset,  'user': user, 
            'sidenav_selection': 'users', 'page': page
        }
    )


class MailingListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = User
    template_name = 'studioadmin/mailing_list.html'
    context_object_name = 'users'

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
    return HttpResponseRedirect(reverse('studioadmin:mailing_list'))
