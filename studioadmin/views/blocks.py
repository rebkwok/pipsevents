import logging

from django.views.generic import ListView

from braces.views import LoginRequiredMixin

from booking.models import Block

from studioadmin.forms import BlockStatusFilter
from studioadmin.views.helpers import StaffUserMixin


logger = logging.getLogger(__name__)


class BlockListView(LoginRequiredMixin, StaffUserMixin, ListView):

    model = Block
    template_name = 'studioadmin/block_list.html'
    context_object_name = 'blocks'
    default_sort_params = ('block_type', 'asc')

    def get_queryset(self):
        block_status = self.request.GET.get('block_status', 'current')
        all_blocks = Block.objects.all().order_by('user__first_name')
        if block_status == 'all':
            return all_blocks
        elif block_status == 'current':
            current = (block.id for block in all_blocks
                      if not block.expired and not block.full)
            return Block.objects.filter(id__in=current).order_by(
                'user__first_name'
            )
        elif block_status == 'active':
            active = (block.id for block in all_blocks if block.active_block())
            return Block.objects.filter(id__in=active).order_by(
                'user__first_name'
            )
        elif block_status == 'transfers':
            return all_blocks.filter(
                block_type__identifier='transferred'
            ).order_by('user__first_name')
        elif block_status == 'unpaid':
            unpaid = (block.id for block in all_blocks
                      if not block.expired and not block.paid
                      and not block.full)
            return Block.objects.filter(id__in=unpaid).order_by(
                'user__first_name'
            )
        elif block_status == 'expired':
            expired = (block.id for block in all_blocks if block.expired or block.full)
            return Block.objects.filter(id__in=expired).order_by(
                'user__first_name'
            )

    def get_context_data(self):
        context = super(BlockListView, self).get_context_data()
        context['sidenav_selection'] = 'blocks'

        block_status = self.request.GET.get('block_status', 'current')
        form = BlockStatusFilter(initial={'block_status': block_status})
        context['form'] = form
        context['block_status'] = block_status

        return context
