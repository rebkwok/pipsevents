from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
 
from django.contrib import messages
from django.db.models import Count
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from activitylog.models import ActivityLog
from booking.models import Membership, UserMembership
from booking.views.membership_views import ensure_subscription_up_to_date
from common.email import send_email
from stripe_payments.utils import StripeConnector
from studioadmin.forms import MembershipAddEditForm, MembershipItemFormset
from studioadmin.views.helpers import staff_required, url_with_querystring


@login_required
@staff_required
def memberships_list(request):
    memberships = Membership.objects.annotate(purchased=Count("user_memberships"))
    for membership in memberships:
        active_memberships = membership.active_user_memberships()
        membership.ongoing_membership_count = len(active_memberships["ongoing"])
        membership.cancelling_membership_count = len(active_memberships["cancelling"])
    return TemplateResponse(request, "studioadmin/memberships.html", {"sidenav_selection": "memberships", "memberships": memberships})


def _process_membership_create_or_update(request, membership=None):
    context = {
        "sidenav_selection":  "memberships" if membership is not None else "membership_add",
        "membership": membership
    }
    if request.method == "POST":
        updating = membership is not None
        form = MembershipAddEditForm(request.POST, instance=membership)   
        if form.is_valid():
            membership = form.save()
            formset =  MembershipItemFormset(request.POST, instance=membership)
            if formset.is_valid():
                formset.save()
                action = "updated" if updating else "created"
                ActivityLog.objects.create(log=f"Membership config ({membership.name}) {action} by admin user {request.user.username}")
                messages.success(request, "Membership configuration saved")
                return HttpResponseRedirect(reverse("studioadmin:memberships_list")) 
        else:
            formset = MembershipItemFormset(request.POST, instance=membership)
    else:
        form = MembershipAddEditForm(instance=membership)
        formset = MembershipItemFormset(instance=membership)

    return TemplateResponse(
        request, 
        "studioadmin/membership_create_update.html", 
        {**context, "form": form, "formset": formset}
    )

@login_required
@staff_required
def membership_edit(request, pk):
    membership = get_object_or_404(Membership, pk=pk)
    return _process_membership_create_or_update(request, membership=membership)


@login_required
@staff_required
def membership_add(request):
    return _process_membership_create_or_update(request)



@login_required
@staff_required
@require_POST
def membership_delete(request, pk):
    membership = get_object_or_404(Membership, pk=pk)
    if membership.user_memberships.exists():
        messages.error(request, "Cannot delete membership configuration with purchased memberships")
    else:
        membership.delete()
        ActivityLog.objects.create(log=f"Membership config ({membership.name}) deleted by admin user {request.user.username}")
    return HttpResponseRedirect(reverse("studioadmin:memberships_list"))


@login_required
@staff_required
def membership_deactivate(request, pk):
    membership = get_object_or_404(Membership, pk=pk)

    if request.method == "POST":
        client = StripeConnector()
        membership.active = False
        membership.save()
        ActivityLog.objects.create(log=f"Membership {membership} deactivated by admin user {request.user}")

        for user_membership in membership.active_user_memberships()["ongoing"]:
            # make sure each usermembership is up to date
            subscription = client.get_subscription(user_membership.subscription_id)
            user_membership = ensure_subscription_up_to_date(user_membership, subscription)

        # Fetch again to ensure we don't try to cancel any already cancelled subscriptions
        for user_membership in membership.active_user_memberships()["ongoing"]:
            cancel_immediately = not user_membership.payment_has_started()
            client.cancel_subscription(subscription_id=user_membership.subscription_id, cancel_immediately=cancel_immediately)
            ActivityLog.objects.create(log=f"User membership for user {user_membership.user} cancelled for deactivated membership")

            # send email to user
            send_email(
                'Your membership has been cancelled',
                txt_template='studioadmin/email/membership_cancelled.txt',
                html_template='studioadmin/email/membership_cancelled.html',
                to_email=[user_membership.user.email],
                extra_ctx={'user_membership': user_membership}
            )

        messages.success(
            request, "Membership has been deactivated"
        )
        return redirect(reverse("studioadmin:memberships_list"))

    return TemplateResponse(request, "studioadmin/membership_deactivate.html", {"membership": membership})


@login_required
@staff_required
def membership_users(request, pk):
    membership = get_object_or_404(Membership, pk=pk)
    return TemplateResponse(request, "studioadmin/membership_users.html", {"membership": membership, "sidenav_selection": "memberships"})


@login_required
@staff_required
def email_members(request, pk):
    membership = get_object_or_404(Membership, pk=pk)
    active_users = list({
        user_membership.user.id for user_membership in membership.active_user_memberships()["all"]
    })
    request.session['users_to_email'] = active_users

    return HttpResponseRedirect(
        url_with_querystring(
            reverse('studioadmin:email_users_view'), membership=membership.id
        )
    )


@login_required
@staff_required
def email_all_members(request):
    active_users = UserMembership.active_member_ids()
    request.session['users_to_email'] = list(active_users)
    return HttpResponseRedirect(reverse('studioadmin:email_users_view'))