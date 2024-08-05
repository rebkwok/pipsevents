import logging

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.urls import reverse

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.views.generic import ListView, CreateView, DeleteView
from django.core.mail import send_mail
from django.template.loader import get_template, render_to_string
from django.utils import timezone
from braces.views import LoginRequiredMixin

from accounts.models import has_active_disclaimer, has_expired_disclaimer
from booking.models import Block, BlockType
from booking.forms import BlockCreateForm
import booking.context_helpers as context_helpers
from booking.views.views_utils import (
    DisclaimerRequiredMixin, DataPolicyAgreementRequiredMixin
)
from booking.views.booking_views import render_row
from booking.views.shopping_basket_views import shopping_basket_blocks_total_context
from common.views import _set_pagination_context

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

        if (
                self.request.user.is_authenticated and not
                context_helpers.get_blocktypes_available_to_book(self.request.user)
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
        return HttpResponseRedirect(reverse('booking:shopping_basket'))


class BlockListView(
    DataPolicyAgreementRequiredMixin, LoginRequiredMixin, ListView
):

    model = Block
    context_object_name = 'blocks'
    template_name = 'booking/block_list.html'
    paginate_by = 10

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BlockListView, self).get_context_data(**kwargs)
        context['disclaimer'] = has_active_disclaimer(self.request.user)
        context['expired_disclaimer'] = has_expired_disclaimer(
            self.request.user
        )
        if not BlockType.objects.filter(active=True):
            context["new_blocks_available"] = False
        else:
            types_available_to_book = context_helpers.\
                get_blocktypes_available_to_book(self.request.user)
            if types_available_to_book:
                context['can_book_block'] = True

        blockformlist = []

        for block in context['blocks']:
            blockform = {
                'block': block,
                'block_cost': block.block_type.cost,
                'expired': block.expired or block.full}
            blockformlist.append(blockform)

        context['blockformlist'] = blockformlist
        _set_pagination_context(context)
        return context

    def get_queryset(self):
        return Block.objects.filter(user=self.request.user).order_by('-start_date')


class BlockDeleteView(LoginRequiredMixin, DisclaimerRequiredMixin, DeleteView):

    model = Block
    template_name = 'booking/delete_block.html'

    def dispatch(self, request, *args, **kwargs):
        # redirect if block is paid or has bookings
        self.block = get_object_or_404(Block, id=self.kwargs['pk'])
        if self.block.paid or self.block.bookings.exists():
            if self.request.GET.get('ref') == 'basket':
                logger.error(f"Attempt to delete block that is paid or has bookings (id {self.block.id})")
                return HttpResponse("")
            return HttpResponseRedirect(reverse('booking:permission_denied'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['block_to_delete'] = self.block
        return context

    def form_valid(self, _form):
        block_id = self.block.id
        block_user = self.block.user.username
        block_type = self.block.block_type
        delete_from_shopping_basket = self.request.GET.get('ref') == 'basket'
        ActivityLog.objects.create(
            log='User {} deleted unpaid and unused block {} ({})'.format(
                block_user, block_id, block_type
            )
        )
        self.block.delete()

        if delete_from_shopping_basket:
            if settings.PAYMENT_METHOD == "stripe":
                template = "booking/includes/shopping_basket_blocks_checkout.html"
            else:
                template = "booking/includes/shopping_basket_blocks_total.html"
            
            context= {
               
                "block_id": block_id,
                'shopping_basket_blocks_total_html': render_to_string(
                    template,
                    shopping_basket_blocks_total_context(self.request)
                )
            }
            return render_row(
                self.request, 
                "booking/includes/shopping_basket_block_row_htmx.html", 
                None,
                context
            )

        messages.success(self.request, 'Block has been deleted')

        next_page = self.request.POST.get('next', 'block_list')
        params = {}
        if self.request.POST.get('booking_code'):
            params['booking_code'] = self.request.POST['booking_code']
        if self.request.POST.get('block_code'):
            params['block_code'] = self.request.POST['block_code']

        url = self.get_success_url(next_page)
        if params:
            url += '?{}'.format(urlencode(params))
        return HttpResponseRedirect(url)

    def get_success_url(self, next_page='block_list'):
        return reverse('booking:{}'.format(next_page))


@login_required
def blocks_modal(request):
    # order by expiry date
    blocks = request.user.blocks.filter(expiry_date__gte=timezone.now()).order_by("expiry_date")
    # # already sorted by expiry date,
    active_blocks = [block for block in blocks if block.active_block()]

    types_available_to_book = context_helpers.get_blocktypes_available_to_book(request.user)
    
    active_memberships = request.user.memberships.filter(
        subscription_status__in=["active", "past_due"], 
    ).order_by("end_date")

    context = {
        "active_memberships": active_memberships,
        'active_blocks': active_blocks, 'can_book_block': types_available_to_book}
    return render(request, 'booking/includes/payment_plans_modal_content.html', context)


def payment_plans(request):
    return render(request, 'booking/payment_plans.html')
