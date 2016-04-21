# -*- coding: utf-8 -*-

from django import forms


class BlockStatusFilter(forms.Form):

    block_status = forms.ChoiceField(
        choices=(('current', 'Current (paid and unpaid)'),
                 ('active', 'Active (current and paid)'),
                 ('transfers', 'Transfers only'),
                 ('unpaid', 'Unpaid (current)'),
                 ('expired', 'Expired or full'),
                 ('all', 'All'),
                 ),
        widget=forms.Select(),
    )
