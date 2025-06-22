# -*- coding: utf-8 -*-
import logging

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.template.response import TemplateResponse

from braces.views import LoginRequiredMixin

from booking.models import BlockVoucher, EventVoucher, UsedBlockVoucher, \
    UsedEventVoucher, StripeSubscriptionVoucher
from studioadmin.forms import BlockVoucherStudioadminForm, MembershipVoucherForm, \
    VoucherStudioadminForm
from studioadmin.views.helpers import StaffUserMixin
from activitylog.models import ActivityLog
from common.views import _set_pagination_context
from stripe_payments.utils import StripeConnector


logger = logging.getLogger(__name__)


class VoucherListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = EventVoucher
    template_name = 'studioadmin/vouchers.html'
    context_object_name = 'vouchers'
    queryset = EventVoucher.objects.filter(is_gift_voucher=False).order_by('-start_date')
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super(VoucherListView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'event_vouchers'
        _set_pagination_context(context)
        return context


class VoucherUpdateView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    form_class = VoucherStudioadminForm
    model = EventVoucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super(VoucherUpdateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'event_vouchers'
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
    model = EventVoucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super(VoucherCreateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_event_voucher'
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


class BlockVoucherListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = BlockVoucher
    template_name = 'studioadmin/block_vouchers.html'
    context_object_name = 'vouchers'
    queryset = BlockVoucher.objects.filter(is_gift_voucher=False).order_by('-start_date')
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super(BlockVoucherListView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'block_vouchers'
        _set_pagination_context(context)
        return context


class GiftVoucherListView(LoginRequiredMixin, StaffUserMixin, ListView):
    template_name = 'studioadmin/gift_vouchers.html'
    context_object_name = 'vouchers'

    def get_queryset(self):
        return EventVoucher.objects.filter(is_gift_voucher=True).order_by('-start_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        block_vouchers = BlockVoucher.objects.filter(is_gift_voucher=True).order_by('-start_date')
        all_vouchers = sorted(list(context["vouchers"]) + list(block_vouchers), key=lambda x: x.start_date, reverse=True)
        paginator = Paginator(all_vouchers, 20)
        page = self.request.GET.get('page', 1)
        vouchers = paginator.get_page(page)

        context['vouchers'] = context['page_obj'] = vouchers
        context['sidenav_selection'] = 'gift_vouchers'
        _set_pagination_context(context)
        return context


class BlockVoucherUpdateView(LoginRequiredMixin, StaffUserMixin, UpdateView):

    form_class = BlockVoucherStudioadminForm
    model = BlockVoucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super(BlockVoucherUpdateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'block_vouchers'
        context['is_block_voucher'] = True
        return context

    def form_valid(self, form):
        if form.has_changed():
            voucher = form.save()
            msg = 'Block Voucher with code <strong>{}</strong> has been updated!'.format(
                voucher.code
            )
            messages.success(self.request, mark_safe(msg))
            ActivityLog.objects.create(
                log='Block Voucher code {} (id {}) updated by admin user {}'.format(
                    voucher.code, voucher.id,
                    self.request.user.username
                )
            )
        else:
            messages.info(self.request, 'No changes made')
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:edit_block_voucher', args=[self.object.pk])


class BlockVoucherCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = BlockVoucherStudioadminForm
    model = EventVoucher
    template_name = 'studioadmin/voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super(BlockVoucherCreateView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_block_voucher'
        context['is_block_voucher'] = True
        return context

    def form_valid(self, form):
        voucher = form.save()
        msg = 'Block Voucher with code <strong>{}</strong> has been created!'.format(
            voucher.code
        )
        messages.success(self.request, mark_safe(msg))
        ActivityLog.objects.create(
            log='Block Voucher with code {} (id {}) created by admin user {}'.format(
                voucher.code, voucher.id,
                self.request.user.username
            )
        )
        return HttpResponseRedirect(self.get_success_url(voucher.id))

    def get_success_url(self, voucher_id):
        return reverse('studioadmin:edit_block_voucher', args=[voucher_id])


class EventVoucherDetailView(LoginRequiredMixin, StaffUserMixin, DetailView):
    model = EventVoucher
    template_name = 'studioadmin/voucher_uses.html'
    context_object_name = 'voucher'

    def get_used_vouchers(self):
        return UsedEventVoucher.objects.filter(voucher=self.object)

    def get_item_ids(self, vouchers):
        return vouchers.values_list("booking_id", flat=True)

    def get_context_data(self, **kwargs):
        context = super(EventVoucherDetailView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'event_vouchers'
        user_list = []

        used_vouchers = self.get_used_vouchers()\
            .order_by('user__first_name', 'user__last_name')
        user_ids = used_vouchers.values_list('user', flat=True).distinct()
        for user_id in user_ids:
            vouchers = used_vouchers.filter(user__id=user_id)
            user_list.append(
                {
                    'user': User.objects.get(id=user_id),
                    "item_ids": ", ".join(str(item_id) for item_id in self.get_item_ids(vouchers)),
                    'count': vouchers.count()}
            )
        context['user_list'] = user_list
        return context


class BlockVoucherDetailView(EventVoucherDetailView):
    model = BlockVoucher
    template_name = 'studioadmin/voucher_uses.html'
    context_object_name = 'voucher'

    def get_used_vouchers(self):
        return UsedBlockVoucher.objects.filter(voucher=self.object)

    def get_item_ids(self, vouchers):
        return vouchers.values_list("block_id", flat=True)

    def get_context_data(self, **kwargs):
        context = super(BlockVoucherDetailView, self).get_context_data(**kwargs)
        context['sidenav_selection'] = 'block_vouchers'
        context['is_block_voucher'] = True
        return context


class MembershipVoucherListView(LoginRequiredMixin, StaffUserMixin, ListView):
    model = StripeSubscriptionVoucher
    template_name = 'studioadmin/membership_vouchers.html'
    context_object_name = 'vouchers'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidenav_selection'] = 'membership_vouchers'
        _set_pagination_context(context)
        return context


class MembershipVoucherCreateView(LoginRequiredMixin, StaffUserMixin, CreateView):

    form_class = MembershipVoucherForm
    model = StripeSubscriptionVoucher
    template_name = 'studioadmin/membership_voucher_create_update.html'
    context_object_name = 'voucher'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sidenav_selection'] = 'add_membership_voucher'
        return context

    def form_valid(self, form):
        voucher = form.save()
        try:
            voucher.create_stripe_code()
        except Exception as err:
            logger.error("Error creating stripe promo code %s", err)
            messages.error(self.request, f"Stripe promo code could not be created: {err}")
            voucher.delete()
        else:
            voucher.save()
            msg = 'Membership Voucher with code <strong>{}</strong> has been created!'.format(
                voucher.code
            )
            messages.success(self.request, mark_safe(msg))
            ActivityLog.objects.create(
                log=f'Membership Voucher with code {voucher.code} created by admin user {self.request.user}'
            )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('studioadmin:membership_vouchers')



def membership_voucher_toggle_active(request, pk):
    voucher = get_object_or_404(StripeSubscriptionVoucher, pk=pk)
    voucher.active = not voucher.active
    voucher.save()
    return render(request, "studioadmin/includes/toggle_voucher_active_button.html", {"voucher": voucher})


def membership_voucher_detail(request, code):
    voucher = get_object_or_404(StripeSubscriptionVoucher, code=code)
    client = StripeConnector()
    promo_code = client.get_promo_code(voucher.promo_code_id)
    voucher.times_used = promo_code.times_redeemed
    return TemplateResponse(
        request, 
        "studioadmin/membership_voucher_detail.html", 
        {"voucher": voucher, 'sidenav_selection': 'membership_vouchers'}
    )