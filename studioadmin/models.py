from django.contrib.auth.models import Group, User
from accounts.utils import has_active_print_disclaimer


def is_regular_student(self):
    return self.has_perm('booking.is_regular_student')


def has_print_disclaimer(self):
    return has_active_print_disclaimer(self)


def subscribed(self):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in self.groups.all()


User.add_to_class("is_regular_student", is_regular_student)
User.add_to_class("has_print_disclaimer", has_print_disclaimer)
User.add_to_class("subscribed", subscribed)
