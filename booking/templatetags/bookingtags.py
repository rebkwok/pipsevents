from django import template
from booking.models import Block


register = template.Library()


@register.filter
def blocksize_format(value):
    """
    Convert block size into formatted text
    """
    block_choices = dict(Block.SIZE_CHOICES)
    return block_choices[value]