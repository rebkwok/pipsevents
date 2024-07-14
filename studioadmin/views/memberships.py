from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.template.response import TemplateResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from booking.models import Membership
from studioadmin.forms import MembershipAddEditForm, MembershipItemFormset
from studioadmin.views.helpers import staff_required


@login_required
@staff_required
def memberships_list(request):
    memberships = Membership.objects.annotate(purchased=Count("membership_items"))
    return TemplateResponse(request, "studioadmin/memberships.html", {"sidenav_selection": "memberships", "memberships": memberships})


@login_required
@staff_required
def membership_edit(request, pk):
    membership = get_object_or_404(Membership, pk=pk)

    if request.method == "POST":
        form = MembershipAddEditForm(request.POST, instance=membership)        
        if form.is_valid():
            membership = form.save()
            formset =  MembershipItemFormset(request.POST, instance=membership)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Membership configuration saved")
                return HttpResponseRedirect(reverse("studioadmin:memberships_list"))            
    else:
        form = MembershipAddEditForm(instance=membership)
        formset = MembershipItemFormset(instance=membership)

    return TemplateResponse(
        request, 
        "studioadmin/membership_create_update.html", 
        {"sidenav_selection": "memberships", "membership": membership, "form": form, "formset": formset}
    )


@login_required
@staff_required
def membership_add(request):
    if request.method == "POST":
        form = MembershipAddEditForm(request.POST)        
        if form.is_valid():
            membership = form.save()
            formset =  MembershipItemFormset(request.POST, instance=membership)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Membership configuration saved")
                return HttpResponseRedirect(reverse("studioadmin:memberships_list"))            
    else:
        form = MembershipAddEditForm()
        formset = MembershipItemFormset()

    return TemplateResponse(
        request, 
        "studioadmin/membership_create_update.html", 
        {"sidenav_selection": "memberships", "form": form, "formset": formset}
    )



@login_required
@staff_required
@require_POST
def membership_delete(request, pk):
    membership = get_object_or_404(Membership, pk=pk)
    if membership.membership_items.exists():
        messages.error(request, "Cannot delete membership configuration with purchased memberships")
    else:
        membership.delete()
    return HttpResponseRedirect(reverse("studioadmin:memberships_list"))
