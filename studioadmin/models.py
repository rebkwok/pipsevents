from django.contrib.auth.models import Group, User
from accounts.models import PrintDisclaimer


def is_regular_student(self):
    return self.has_perm('booking.is_regular_student')


def has_print_disclaimer(self):
    return PrintDisclaimer.objects.filter(user=self).exists()


def subscribed(self):
    group, _ = Group.objects.get_or_create(name='subscribed')
    return group in self.groups.all()


User.add_to_class("is_regular_student", is_regular_student)
User.add_to_class("has_print_disclaimer", has_print_disclaimer)
User.add_to_class("subscribed", subscribed)
