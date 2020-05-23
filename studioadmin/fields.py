# -*- coding: utf-8 -*-

from django import forms
from django.contrib.auth.models import User

from booking.models import Block


class UserBlockModelChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        return "{}{}; exp {}; {} left".format(
            obj.block_type.event_type.subtype,
            " ({})".format(obj.block_type.identifier)
            if obj.block_type.identifier else '',
            obj.expiry_date.strftime('%d/%m'),
            obj.block_type.size - obj.bookings_made()
        )

    def to_python(self, value):
        if value:
            return Block.objects.get(id=value)
