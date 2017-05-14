from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist


def active_disclaimer_cache_key(user):
    return 'user_{}_active_disclaimer'.format(user.id)


def expired_disclaimer_cache_key(user):
    return 'user_{}_expired_disclaimer'.format(user.id)


def has_active_disclaimer(user):
    key = active_disclaimer_cache_key(user)
    has_disclaimer = bool(cache.get(key))
    if not has_disclaimer:
        has_disclaimer = bool(
            [
                True for od in user.online_disclaimer.all()
                if od.is_active
            ]
        )

        if not has_disclaimer:
            try:
                user.print_disclaimer
                has_disclaimer = True
            except ObjectDoesNotExist:
                pass

        cache.set(key, has_disclaimer, timeout=6000)

    return has_disclaimer


def has_expired_disclaimer(user):
    key = expired_disclaimer_cache_key(user)
    has_disclaimer = bool(cache.get(key))
    if not has_disclaimer:
        has_disclaimer = bool(
            [
                True for od in user.online_disclaimer.all()
                if not od.is_active
            ]
        )

        cache.set(key, has_disclaimer, timeout=6000)

    return has_disclaimer