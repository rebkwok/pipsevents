# -*- coding: utf-8 -*-

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import HttpResponseRedirect
from django.views.generic import CreateView, ListView, UpdateView
from django.utils.safestring import mark_safe

from braces.views import LoginRequiredMixin

from booking.models import Voucher
from studioadmin.forms import VoucherStudioadminForm
from studioadmin.views.helpers import StaffUserMixin
from activitylog.models import ActivityLog


class VoucherListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = Voucher
    template_name = 'studioadmin/vouchers.html'
    context_object_name = 'vouchers'

    def get_context_data(self, **kwargs):
        context = super(VoucherListView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'vouchers'
        return context


class VoucherUpdateView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    form_class = VoucherStudioadminForm
    model = Voucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super(VoucherUpdateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'vouchers'
        return context

    def form_valid(self, form):
        if form.has_changed():
            voucher = form.save()
            msg = 'Voucher with code <strong>{}</strong> has been updated!'.format(
                voucher.code
            )
            messages.success(self.request, mark_safe(msg))
            ActivityLog.objects.create(
                log='Voucher code {} (id {}) updated by admin user {}'.format(
                    voucher.code, voucher.id,
                    self.request.user.username
                )
            )
        else:
            messages.info(self.request, 'No changes made')
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:edit_voucher', args=[self.object.pk])


class VoucherCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = VoucherStudioadminForm
    model = Voucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'


    def get_context_data(self, **kwargs):
        context = super(VoucherCreateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_voucher'
        return context

    def form_valid(self, form):
        voucher = form.save()
        msg = 'Voucher with code <strong>{}</strong> has been created!'.format(
            voucher.code
        )
        messages.success(self.request, mark_safe(msg))
        ActivityLog.objects.create(
            log='Voucher with code {} (id {}) created by admin user {}'.format(
                voucher.code, voucher.id,
                self.request.user.username
            )
        )
        return HttpResponseRedirect(self.get_success_url(voucher.id))

    def get_success_url(self, voucher_id):
        return reverse('studioadmin:edit_voucher', args=[voucher_id])
