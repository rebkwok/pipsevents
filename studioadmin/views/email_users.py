import ast
import csv
import logging

from math import ceil

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User

from django.contrib import messages
from django.core.mail.message import EmailMultiAlternatives
from django.urls import reverse
from django.http import HttpResponse
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, render
from django.utils.encoding import smart_str
from django.utils.safestring import mark_safe

from booking.models import Event, Booking, Membership
from booking.email_helpers import send_support_email

from studioadmin.forms import EmailUsersForm, ChooseUsersFormSet, \
    UserFilterForm
from studioadmin.views.helpers import staff_required, url_with_querystring

from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@staff_required
def choose_users_to_email(
        request, template_name='studioadmin/choose_users_form.html'
):
    userfilterform = UserFilterForm(prefix='filter')
    showing_students = False

    if 'filter' in request.POST:
        showing_students = True
        event_ids = request.POST.getlist('filter-events')
        lesson_ids = request.POST.getlist('filter-lessons')
        student_ids = request.POST.getlist('filter-students')
        if not event_ids:
            if request.session.get('events'):
                del request.session['events']
            event_ids = []
        else:
            request.session['events'] = event_ids

        if not lesson_ids:
            if request.session.get('lessons'):
                del request.session['lessons']
            lesson_ids = []
        else:
            request.session['lessons'] = lesson_ids

        if not event_ids and not lesson_ids and not student_ids:
            usersformset = ChooseUsersFormSet(queryset=User.objects.none())
        else:
            event_and_lesson_ids = event_ids + lesson_ids
            bookings = Booking.objects.filter(event__id__in=event_and_lesson_ids)
            user_ids_from_bookings = [booking.user.id for booking in bookings
                            if booking.status == 'OPEN']
            selected_student_ids = list(User.objects.filter(id__in=student_ids).values_list('id', flat=True))
            user_ids = set(user_ids_from_bookings + selected_student_ids)

            usersformset = ChooseUsersFormSet(
                queryset=User.objects.filter(id__in=user_ids)
                .order_by('first_name', 'last_name')
            )
            userfilterform = UserFilterForm(
                prefix='filter',
                initial={'events': event_ids, 'lessons': lesson_ids}
            )

    elif request.method == 'POST':
        userfilterform = UserFilterForm(prefix='filter', data=request.POST)
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

            request.session['users_to_email'] = users_to_email

            return HttpResponseRedirect(url_with_querystring(
                reverse('studioadmin:email_users_view'),
                events=event_ids, lessons=lesson_ids)
            )

    else:
        # for a new GET, remove any event/lesson session data
        if request.session.get('events'):
            del request.session['events']
        if request.session.get('lessons'):
            del request.session['lessons']
        usersformset = ChooseUsersFormSet(queryset=User.objects.none())

    return TemplateResponse(
        request, template_name, {
            'usersformset': usersformset,
            'userfilterform': userfilterform,
            'sidenav_selection': 'email_users',
            'showing_students': showing_students
            }
    )


@login_required
@staff_required
def email_users_view(request, mailing_list=False,
                     template_name='studioadmin/email_users_form.html'):

    if mailing_list:
        subscribed, _ = Group.objects.get_or_create(name='subscribed')
        users_to_email = subscribed.user_set.all()
    else:
        users_to_email = User.objects.filter(
            id__in=request.session['users_to_email']
        )

    if request.method == 'POST':

        form = EmailUsersForm(request.POST)
        test_email = request.POST.get('send_test', False)

        if form.is_valid():
            subject = '{}{}'.format(
                form.cleaned_data['subject'],
                ' [TEST EMAIL]' if test_email else ''
            )
            from_address = form.cleaned_data['from_address']
            message = mark_safe(form.cleaned_data['message'])
            cc = form.cleaned_data['cc']

            # bcc recipients
            email_addresses = [user.email for user in users_to_email]
            email_count = len(email_addresses)
            number_of_emails = ceil(email_count / 99)

            if test_email:
                email_lists = [[from_address]]
            else:
                email_lists = [email_addresses]  # will be a list of lists
                # split into multiple emails of 99 bcc plus 1 cc
                if email_count > 99:
                    email_lists = [
                        email_addresses[i : i + 99]
                        for i in range(0, email_count, 99)
                        ]

            host = 'http://{}'.format(request.META.get('HTTP_HOST'))

            try:
                for i, email_list in enumerate(email_lists):
                    ctx = {
                                'subject': subject,
                                'message': message,
                                'number_of_emails': number_of_emails,
                                'email_count': email_count,
                                'is_test': test_email,
                                'mailing_list': mailing_list,
                                'host': host,
                            }
                    msg = EmailMultiAlternatives(
                        subject,
                        get_template(
                            'studioadmin/email/email_users.txt').render(
                                ctx
                            ),
                        bcc=email_list,
                        cc=[from_address]
                        if (i == 0 and cc and not test_email) else [],
                        reply_to=[from_address]
                        )
                    msg.attach_alternative(
                        get_template(
                            'studioadmin/email/email_users.html').render(
                                ctx
                            ),
                        "text/html"
                    )
                    msg.send(fail_silently=False)

                    if not test_email:
                        ActivityLog.objects.create(
                            log='{} email with subject "{}" sent to users {} by'
                                ' admin user {}'.format(
                                    'Mailing list' if mailing_list else 'Bulk',
                                    subject, ', '.join(email_list),
                                    request.user.username
                                )
                        )
            except Exception as e:
                # send mail to tech support with Exception
                send_support_email(
                    e, __name__, "Bulk Email to students"
                )
                ActivityLog.objects.create(
                    log="Possible error with sending {} email; "
                        "notification sent to tech support".format(
                            'mailing list' if mailing_list else 'bulk'
                    )
                )

                if not test_email:
                    ActivityLog.objects.create(
                        log='{} email error '
                            '(email subject "{}"), sent by '
                            'by admin user {}'.format(
                                'Mailing list' if mailing_list else 'Bulk',
                                subject, request.user.username
                            )
                    )

            if not test_email:
                messages.success(
                    request,
                    '{} email with subject "{}" has been sent to '
                    'users'.format(
                        'Mailing list' if mailing_list else 'Bulk',
                        subject
                    )
                )
                return HttpResponseRedirect(reverse('studioadmin:users'))
            else:
                messages.success(
                    request, 'Test email has been sent to {} only. Click '
                                '"Send Email" below to send this email to '
                                'users.'.format(
                                from_address
                                )
                )



        # Do this if form not valid OR sending test email
        event_ids = request.session.get('events', [])
        lesson_ids = request.session.get('lessons', [])
        events = Event.objects.filter(id__in=event_ids)
        lessons = Event.objects.filter(id__in=lesson_ids)

        if form.errors:
            totaleventids = event_ids + lesson_ids
            totalevents = Event.objects.filter(id__in=totaleventids)
            messages.error(
                request,
                mark_safe(
                    "Please correct errors in form: {}".format(form.errors)
                )
            )
            form = EmailUsersForm(
                initial={
                    'subject': "; ".join(
                        (str(event) for event in totalevents)
                    )
                }
            )

        if test_email:
            form = EmailUsersForm(request.POST)

    else:
        event_ids = ast.literal_eval(request.GET.get('events', '[]'))
        events = Event.objects.filter(id__in=event_ids)
        lesson_ids = ast.literal_eval(request.GET.get('lessons', '[]'))
        lessons = Event.objects.filter(id__in=lesson_ids)
        membership_id = request.GET.get("membership")
        totaleventids = event_ids + lesson_ids 
        subject = ""
        if totaleventids:
            totalevents = Event.objects.filter(id__in=totaleventids)
            subject = "; ".join((str(event) for event in totalevents))
        elif membership_id:
            try:
                membership = Membership.objects.get(id=int(membership_id))
                subject = f"Membership: {membership.name}"
            except (ValueError, Membership.DoesNotExist):
                ...
                
        form = EmailUsersForm(initial={'subject': subject})

    return TemplateResponse(
            request, template_name, {
                'form': form,
                'users_to_email': users_to_email,
                'sidenav_selection': 'mailing_list'
                if mailing_list else 'email_users',
                'events': events,
                'lessons': lessons,
                'mailing_list': mailing_list
            }
        )


@login_required
@staff_required
def export_mailing_list(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="mailing_list.csv"'

    subscribed, _ = Group.objects.get_or_create(name='subscribed')
    mailing_list_users = subscribed.user_set.all()

    wr = csv.writer(response)

    wr.writerow([
        smart_str(u"Email Address"),
        smart_str(u"First Name"),
        smart_str(u"Last Name")
    ])

    for user in mailing_list_users:
        wr.writerow([
            smart_str(user.email),
            smart_str(user.first_name),
            smart_str(user.last_name)
        ])

    return response
