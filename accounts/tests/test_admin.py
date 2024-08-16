from datetime import timedelta

from model_bakery import baker

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import TestCase, RequestFactory
from django.utils import timezone

from accounts.admin import AccountBanAdmin, CustomUserAdmin, CurrentlyBannedListFilter, \
    CurrentlyBannedUserListFilter
from accounts.models import AccountBan


class AccountBanAdminTests(TestCase):

    def test_currently_banned_filter(self):
        current = baker.make(AccountBan, end_date=timezone.now() + timedelta(2))
        past = baker.make(AccountBan, end_date=timezone.now() - timedelta(2))
        filter = CurrentlyBannedListFilter(
            None, {'currently_banned': ['currently_banned']}, AccountBan, AccountBanAdmin
        )
        assert filter.queryset(None, AccountBan.objects.all()).count() == 1
        ban = filter.queryset(None, AccountBan.objects.all())[0]
        assert ban.id == current.id

        filter = CurrentlyBannedListFilter(
            None, {'currently_banned': ['previously_banned']}, AccountBan, AccountBanAdmin
        )
        assert filter.queryset(None, AccountBan.objects.all()).count() == 1
        ban = filter.queryset(None, AccountBan.objects.all())[0]
        assert ban.id == past.id

        # no filter parameters returns all
        filter = CurrentlyBannedListFilter(None, {}, AccountBan, AccountBanAdmin)
        bans = filter.queryset(None, AccountBan.objects.all())
        assert bans.count() == 2

    def test_currently_banned_display(self):
        baker.make(AccountBan, end_date=timezone.now() + timedelta(2))
        baker.make(AccountBan, end_date=timezone.now() - timedelta(2))

        ban_admin = AccountBanAdmin(AccountBan, AdminSite())
        ban_query = ban_admin.get_queryset(None)
        assert ban_admin.currently_banned(ban_query[0]) is True
        assert ban_admin.currently_banned(ban_query[1]) is False


class CustomUserAdminTests(TestCase):

    def test_currently_banned_filter(self):
        user = baker.make(User)
        user1 = baker.make(User)
        user2 = baker.make(User)
        baker.make(AccountBan, user=user, end_date=timezone.now() + timedelta(2))
        baker.make(AccountBan, user=user1, end_date=timezone.now() - timedelta(2))

        filter = CurrentlyBannedUserListFilter(
            None, {'currently_banned': ['currently_banned']}, User, CustomUserAdmin
        )
        assert filter.queryset(None, User.objects.all()).count() == 1
        user = filter.queryset(None, User.objects.all())[0]
        assert user.id == user.id

        filter = CurrentlyBannedUserListFilter(
            None, {'currently_banned': ['not_banned']}, User, CustomUserAdmin
        )
        assert filter.queryset(None, User.objects.all()).count() == 2
        past_banned_user = filter.queryset(None, User.objects.all())[0]
        assert past_banned_user.id == user1.id
        no_ban_user = filter.queryset(None, User.objects.all())[1]
        assert no_ban_user.id == user2.id

        # no filter parameters returns all
        filter = CurrentlyBannedUserListFilter(None, {}, User, CustomUserAdmin)
        users = filter.queryset(None, User.objects.all())
        assert users.count() == 3

    def test_currently_banned_display(self):
        user = baker.make(User)
        user1 = baker.make(User)
        baker.make(User)
        baker.make(AccountBan, user=user, end_date=timezone.now() + timedelta(2))
        baker.make(AccountBan, user=user1, end_date=timezone.now() - timedelta(2))

        user_admin = CustomUserAdmin(User, AdminSite())
        user_query = user_admin.get_queryset(None).order_by("id")
        assert user_admin.currently_banned(user_query[0]) is True
        assert user_admin.currently_banned(user_query[1]) is False
        assert user_admin.currently_banned(user_query[2]) is False

    def test_ban_users(self):
        user1 = baker.make(User, email="user1@test.com")
        user2 = baker.make(User, email="user2@test.com")
        user3 = baker.make(User, email="user3@test.com")
        assert AccountBan.objects.exists() is False

        for user in [user1, user2, user3]:
            assert user.currently_banned() is False

        request = RequestFactory().get("/")
        setattr(request, 'session', 'session')
        setattr(request, '_messages', FallbackStorage(request))
        user_admin = CustomUserAdmin(User, AdminSite())
        queryset = User.objects.filter(id__in=[user1.id, user2.id])
        user_admin.ban_account(request, queryset)

        assert user1.currently_banned() is True
        assert user2.currently_banned() is True
        assert user3.currently_banned() is False

        assert len(mail.outbox) == 2
        assert mail.outbox[0].to == ["user1@test.com"]
        assert mail.outbox[1].to == ["user2@test.com"]
        for message in mail.outbox:
            assert "Account locked" in message.subject

        # call again with all users
        user_admin.ban_account(request, User.objects.all())

        # only 1 additional email, to user3
        assert len(mail.outbox) == 3
        assert mail.outbox[-1].to == ["user3@test.com"]
        assert user1.currently_banned() is True
        assert user2.currently_banned() is True
        assert user3.currently_banned() is True

        # All users are now banned; update user1 so their ban has expired
        user1.ban.end_date = timezone.now() - timedelta(1)
        user1.ban.save()
        assert user1.currently_banned() is False

        # call again with all users
        user_admin.ban_account(request, User.objects.all())

        # only 1 additional email, to user1
        assert len(mail.outbox) == 4
        assert mail.outbox[-1].to == ["user1@test.com"]
        assert user1.currently_banned() is True
        assert user2.currently_banned() is True
        assert user3.currently_banned() is True