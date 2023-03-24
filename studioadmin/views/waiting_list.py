import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from django.contrib import messages
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import HttpResponseRedirect
from django.urls import reverse

from booking.models import Event, WaitingListUser

from studioadmin.views.helpers import is_instructor_or_staff
from studioadmin.views.helpers import url_with_querystring
from activitylog.models import ActivityLog


logger = logging.getLogger(__name__)


@login_required
@is_instructor_or_staff
def event_waiting_list_view(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    waiting_list_users = WaitingListUser.objects.filter(
        event__id=event_id).order_by('user__username')
    ev_type = 'lessons' if event.event_type.event_type == 'CL' else 'events'

    template = 'studioadmin/event_waiting_list.html'

    if request.method == 'POST' and 'remove_user' in request.POST:
        remove_wluser_id = request.POST.getlist('remove_user')[0]
        wl_user_to_remove = WaitingListUser.objects.get(id=remove_wluser_id)
        waiting_list_users.exclude(id=remove_wluser_id)
        user_to_remove = User.objects.get(id=wl_user_to_remove.user.id)
        wl_user_to_remove.delete()

        messages.success(
            request,
            "{} {} ({}) has been removed from the waiting list".format(
                user_to_remove.first_name,
                user_to_remove.last_name,
                user_to_remove.username
            )
        )
        ActivityLog.objects.create(
            log="{} {} ({}) removed from the waiting list "
                "by admin user {}".format(
                user_to_remove.first_name,
                user_to_remove.last_name,
                user_to_remove.username,
                request.user.username
            )
        )

    return TemplateResponse(
        request, template, {
            'waiting_list_users': waiting_list_users, 'event': event,
            'sidenav_selection': '{}_register'.format(ev_type)
        }
    )


@login_required
@is_instructor_or_staff
def email_waiting_list(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    waiting_list_users = WaitingListUser.objects.filter(
        event__id=event_id).values_list("user_id", flat=True)
    request.session['users_to_email'] = list(waiting_list_users)
    if event.event_type.event_type == "CL":
        lesson_ids = [event.id]
        event_ids = []
    else:
        event_ids = [event.id]
        lesson_ids = []

    return HttpResponseRedirect(
        url_with_querystring(
            reverse('studioadmin:email_users_view'),
            events=event_ids, lessons=lesson_ids)
        )
