# -*- coding: utf-8 -*-

from django import forms
from django.contrib.auth.models import User

from booking.models import Block


class UserChoiceField(forms.ChoiceField):

    def to_python(self, value):
        if value:
            return User.objects.get(id=value)

    def validate(self, value):
        if value:
            value = value.id
        super(UserChoiceField, self).validate(value)

    def has_changed(self, initial, data):
        if str(initial) == str(data):
            return False
        return super(UserChoiceField, self).has_changed(initial, data)


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
