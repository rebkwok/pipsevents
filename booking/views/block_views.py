import logging

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.urls import reverse

from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, CreateView, DeleteView
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template.response import TemplateResponse
from braces.views import LoginRequiredMixin

from accounts.utils import has_active_disclaimer, has_expired_disclaimer
from payments.forms import PayPalPaymentsShoppingBasketForm
from booking.models import Block, BlockVoucher, UsedBlockVoucher
from booking.forms import BlockCreateForm, VoucherForm
import booking.context_helpers as context_helpers
from booking.views.shopping_basket_views import apply_voucher_to_unpaid_blocks
from booking.views.views_utils import (
    DisclaimerRequiredMixin, DataPolicyAgreementRequiredMixin, validate_block_voucher_code
)
from payments.helpers import create_multiblock_paypal_transaction

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class BlockCreateView(
    DisclaimerRequiredMixin, DataPolicyAgreementRequiredMixin,
    LoginRequiredMixin, CreateView
):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block added: {}'

    def dispatch(self, request, *args, **kwargs):
        # redirect if user already has active (paid or unpaid) blocks for all
        # blocktypes

        # remove cart items from session since we're getting a new block
        if self.request.session.get('cart_items'):
            del self.request.session['cart_items']

        if not context_helpers.get_blocktypes_available_to_book(
            self.request.user
        ):
            return HttpResponseRedirect(reverse('booking:block_list'))

        return super(BlockCreateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockCreateView, self).get_context_data(**kwargs)
        context['form'].fields['block_type'].queryset = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        context['block_types'] = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        return context

    def form_valid(self, form):
        block_type = form.cleaned_data['block_type']
        types_available = context_helpers.get_blocktypes_available_to_book(
            self.request.user)

        if block_type not in types_available:
            return HttpResponseRedirect(reverse('booking:has_active_block'))

        block = form.save(commit=False)
        block.user = self.request.user
        block.save()

        ActivityLog.objects.create(
            log='Block {} created; Block type: {}; by user: {}'.format(
                block.id, block.block_type, self.request.user.username
            )
        )

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))
        # send email to user
        ctx = {
                          'host': host,
                          'user': block.user,
                          'block_type': block.block_type,
                          'start_date': block.start_date,
                          'expiry_date': block.expiry_date,
                      }
        send_mail('{} Block created'.format(
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX),
            get_template('booking/email/block_booked.txt').render(ctx),
            settings.DEFAULT_FROM_EMAIL,
            [block.user.email],
            html_message=get_template(
                'booking/email/block_booked.html').render(ctx),
            fail_silently=False)

        messages.success(
            self.request, self.success_message.format(block.block_type)
            )
        return HttpResponseRedirect(block.get_absolute_url())


class BlockListView(
    DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView
):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'
    paginate_by = 10

    def post(self, request):
        if "apply_voucher" in request.POST:
            voucher_error = None
            code = request.POST['code'].strip()
            try:
                voucher = BlockVoucher.objects.get(code=code)
            except BlockVoucher.DoesNotExist:
                voucher = None
                voucher_error = 'Invalid code' if code else 'No code provided'

            if voucher:
                voucher_error = validate_block_voucher_code(
                    voucher, self.request.user
                )

            paginator, page_obj, blocks, _ = self.paginate_queryset(
                self.get_queryset(), self.paginate_by
            )
            context = {'blocks': blocks, 'paginator': paginator, 'page_obj': page_obj}
            extra_context = self.get_extra_context(
                context, voucher=voucher, voucher_error=voucher_error, code=code,
            )
            context.update(**extra_context)
            return TemplateResponse(self.request, self.template_name, context)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)
        extra_context = self.get_extra_context(context)
        context.update(**extra_context)
        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')

    def get_extra_context(self, context, **kwargs):
        context['disclaimer'] = has_active_disclaimer(self.request.user)
        context['expired_disclaimer'] = has_expired_disclaimer(
            self.request.user
        )

        types_available_to_book = context_helpers.\
            get_blocktypes_available_to_book(self.request.user)
        if types_available_to_book:
            context['can_book_block'] = True

        voucher = kwargs.get('voucher', None)
        voucher_error = kwargs.get('voucher_error', None)
        code = kwargs.get('code', None)
        context['voucher_form'] = VoucherForm(initial={'code': code})
        if voucher:
            context['voucher'] = voucher
        if voucher_error:
            context['voucher_error'] = voucher_error

        valid_voucher = voucher and not bool(voucher_error)
        context['valid_voucher'] = valid_voucher

        blockformlist = []

        unpaid_block_and_costs = [
            (block, block.block_type.cost)
            for block in self.get_queryset().filter(paid=False, paypal_pending=False)
            if not block.expired and not block.full
        ]
        unpaid_blocks, unpaid_block_costs = list(zip(*unpaid_block_and_costs)) \
            if unpaid_block_and_costs else ([], [0])

        if valid_voucher:
            times_used = UsedBlockVoucher.objects.filter(
                voucher=voucher, user=self.request.user
            ).count()
            context['times_voucher_used'] = times_used

            block_voucher_dict = apply_voucher_to_unpaid_blocks(
                    voucher, unpaid_blocks, times_used
                )

            context.update({
                'voucher_applied_items': block_voucher_dict['voucher_applied_blocks'],
                'total_cost': block_voucher_dict['total_unpaid_block_cost'],
                'voucher_msg': block_voucher_dict['block_voucher_msg'],
            })

        for block in context['blocks']:
            blockform = {
                'block': block,
                'block_cost': block.block_type.cost,
                'expired': block.expired or block.full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))

        if unpaid_blocks:
            context['has_unpaid_block'] = True
            invoice_id = create_multiblock_paypal_transaction(
                self.request.user, unpaid_blocks
            )
            item_ids_str = ','.join(str(block.id) for block in unpaid_blocks)
            custom = context_helpers.get_paypal_custom(
                item_type='block',
                item_ids=item_ids_str,
                voucher_code=voucher.code if context.get('valid_voucher') else '',
                user_email=self.request.user.email
            )
            context['paypalform'] = PayPalPaymentsShoppingBasketForm(
                initial=context_helpers.get_paypal_cart_dict(
                    host,
                    'block',
                    unpaid_blocks,
                    invoice_id,
                    custom,
                    voucher_applied_items=context.get('voucher_applied_items', []),
                    voucher=voucher,
                )
            )
            self.request.session['cart_items'] = custom
            if not context.get('total_cost'):
                # no voucher or invalid voucher
                context['total_cost'] = sum(unpaid_block_costs)

        else:
            if self.request.session.get('cart_items'):
                del self.request.session['cart_items']
        return context


class BlockDeleteView(LoginRequiredMixin, DisclaimerRequiredMixin, DeleteView):

    model = Block
    template_name = 'booking/delete_block.html'

    def dispatch(self, request, *args, **kwargs):
        # redirect if block is paid or has bookings
        self.block = get_object_or_404(Block, id=self.kwargs['pk'])
        if self.block.paid or self.block.bookings.exists():
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super(BlockDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BlockDeleteView, self).get_context_data(**kwargs)
        context['block_to_delete'] = self.block
        return context

    def delete(self, request, *args, **kwargs):
        block_id = self.block.id
        block_user = self.block.user.username
        block_type = self.block.block_type

        ActivityLog.objects.create(
            log='User {} deleted unpaid and unused block {} ({})'.format(
                block_user, block_id, block_type
            )
        )
        messages.success(self.request, 'Block has been deleted')

        super().delete(request, *args, **kwargs)

        next = request.POST.get('next', 'block_list')

        params = {}
        if request.POST.get('booking_code'):
            params['booking_code'] = request.POST['booking_code']
        if request.POST.get('block_code'):
            params['block_code'] = request.POST['block_code']

        url = self.get_success_url(next)
        if params:
            url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)

    def get_success_url(self, next='block_list'):
        return reverse('booking:{}'.format(next))
