import logging

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse

from django.db.models import Q
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, CreateView, DeleteView
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import get_template
from django.template.response import TemplateResponse
from braces.views import LoginRequiredMixin

from accounts.utils import has_active_disclaimer, has_expired_disclaimer
from payments.forms import PayPalPaymentsListForm, PayPalPaymentsShoppingBasketForm
from booking.models import Booking, Block, BlockVoucher, UsedBlockVoucher
from booking.forms import BlockCreateForm, VoucherForm
import booking.context_helpers as context_helpers
from booking.views.views_utils import DisclaimerRequiredMixin
from payments.helpers import create_multiblock_paypal_transaction

from activitylog.models import ActivityLog

logger = logging.getLogger(__name__)


class BlockCreateView(DisclaimerRequiredMixin, LoginRequiredMixin, CreateView):

    model = Block
    template_name = 'booking/add_block.html'
    form_class = BlockCreateForm
    success_message = 'New block booking created: {}'

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


class BlockListView(LoginRequiredMixin, ListView):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'

    def validate_voucher_code(self, voucher, user):
        if voucher.has_expired:
            return 'Voucher code has expired'
        elif voucher.max_vouchers and \
            UsedBlockVoucher.objects.filter(voucher=voucher).count() >= \
                voucher.max_vouchers:
            return 'Voucher has limited number of uses and has now expired'
        elif not voucher.has_started:
            return 'Voucher code is not valid until {}'.format(
                voucher.start_date.strftime("%d %b %y")
            )
        elif voucher.max_per_user and UsedBlockVoucher.objects.filter(
                voucher=voucher, user=user
        ).count() >= voucher.max_per_user:
            return 'Voucher code has already been used the maximum number ' \
                   'of times ({})'.format(
                    voucher.max_per_user
                    )
        else:
            user_unpaid_blocks = [
                block for block in Block.objects.filter(user=user, paid=False)
                if not block.expired
            ]
            for block in user_unpaid_blocks:
                if voucher.check_block_type(block.block_type):
                    return None
            return 'Code is not valid for any of your currently unpaid ' \
                   'blocks'

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
                voucher_error = self.validate_voucher_code(
                    voucher, self.request.user
                )

            context = {'blocks': self.get_queryset()}
            extra_context = self.get_extra_context(
                voucher=voucher, voucher_error=voucher_error, code=code,
            )
            context.update(**extra_context)
            return TemplateResponse(self.request, self.template_name, context)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)
        extra_context = self.get_extra_context()
        context.update(**extra_context)
        return context

    def get_queryset(self):
        return Block.objects.filter(
           Q(user=self.request.user)
        ).order_by('-start_date')

    def get_extra_context(self, **kwargs):
        context = {}
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
        unpaid_blocks = []
        total_cost = 0
        voucher_applied_items = []

        if valid_voucher:
            times_used = UsedBlockVoucher.objects.filter(
                voucher=voucher, user=self.request.user
            ).count()
            context['times_voucher_used'] = times_used

            check_max_per_user = False
            check_max_total = False
            if voucher.max_per_user:
                check_max_per_user = True
                uses_per_user_left = voucher.max_per_user - times_used

            if voucher.max_vouchers:
                check_max_total = True
                max_voucher_uses_left = (
                    voucher.max_vouchers -
                    UsedBlockVoucher.objects.filter(voucher=voucher).count()
                )

            invalid_block_types = []
            max_per_user_exceeded = False
            max_total_exceeded = False

        for block in self.get_queryset():
            expired = block.expiry_date < timezone.now()
            block_cost = block.block_type.cost

            if not block.paid and not expired and not block.paypal_pending:
                context['has_unpaid_block'] = True
                unpaid_blocks.append(block)

                if not valid_voucher:
                    total_cost += block.block_type.cost

                else:
                    can_use = voucher.check_block_type(block.block_type)
                    if check_max_per_user and uses_per_user_left <= 0:
                        can_use = False
                        max_per_user_exceeded = True
                    if check_max_total and max_voucher_uses_left <= 0:
                        can_use = False
                        max_total_exceeded = True

                    if can_use:
                        voucher_applied_items.append(block.id)
                        total_cost += Decimal(
                            float(block_cost) * ((100 - voucher.discount) / 100)
                        ).quantize(Decimal('.05'))
                        if check_max_per_user:
                            uses_per_user_left -= 1
                        if check_max_total:
                            max_voucher_uses_left -= 1
                    else:
                        total_cost += block.block_type.cost
                        # if we can't use the voucher but max_total and
                        # max_per_user are not exceeded, it must be an invalid
                        # block type
                        if not (max_total_exceeded or max_per_user_exceeded):
                            invalid_block_types.append(
                                block.block_type.event_type.subtype
                            )

                    voucher_msg = []
                    if invalid_block_types:
                        voucher_msg.append(
                            'Voucher cannot be used for some blocks '
                            '({})'.format(', '.join(set(invalid_block_types)))
                        )
                    if max_per_user_exceeded:
                        voucher_msg.append(
                            'Voucher not applied to some blocks; you can '
                            'only use this voucher a total of {} times.'.format(
                                voucher.max_per_user
                            )
                        )
                    if max_total_exceeded:
                        voucher_msg.append(
                            'Voucher not applied to some blocks; voucher '
                            'has limited number of total uses.'
                        )

                    context['voucher_applied_items'] = voucher_applied_items
                    context['voucher_msg'] = voucher_msg


            full = Booking.objects.filter(
                block__id=block.id).count() >= block.block_type.size
            blockform = {
                'block': block,
                'block_cost': block_cost,
                'expired': expired or full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist

        host = 'http://{}'.format(self.request.META.get('HTTP_HOST'))

        if unpaid_blocks:
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
                    voucher_applied_items=voucher_applied_items,
                    voucher=voucher,
                )
            )
            self.request.session['cart_items'] = custom
            context['total_cost'] = total_cost
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

        return super(BlockDeleteView, self).delete(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('booking:block_list')
