from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist


def active_disclaimer_cache_key(user):
    return 'user_{}_active_disclaimer'.format(user.id)

def active_online_disclaimer_cache_key(user):
    return 'user_{}_active_online_disclaimer'.format(user.id)

def active_print_disclaimer_cache_key(user):
    return 'user_{}_active_print_disclaimer'.format(user.id)

def expired_disclaimer_cache_key(user):
    return 'user_{}_expired_disclaimer'.format(user.id)


def has_active_disclaimer(user):
    key = active_disclaimer_cache_key(user)
    has_disclaimer = cache.get(key)
    if has_disclaimer is None:
        has_disclaimer = has_active_online_disclaimer(user)

        if not has_disclaimer:
            has_disclaimer = has_active_print_disclaimer(user)
        cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def has_active_online_disclaimer(user):
    key = active_online_disclaimer_cache_key(user)
    if cache.get(key) is None:
        has_disclaimer = bool(
            [
                True for od in user.online_disclaimer.all()
                if od.is_active
            ]
        )
        cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def has_active_print_disclaimer(user):
    key = active_print_disclaimer_cache_key(user)
    if cache.get(key) is None:
        try:
            pd = user.print_disclaimer
            has_disclaimer = pd.is_active
            cache.set(key, has_disclaimer, timeout=600)
        except ObjectDoesNotExist:
            cache.set(key, False, timeout=600)
            has_disclaimer = False
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def has_expired_disclaimer(user):
    key = expired_disclaimer_cache_key(user)
    has_disclaimer = cache.get(key)
    if has_disclaimer is None:
        if not has_disclaimer:
            has_disclaimer = bool(
                [
                    True for od in user.online_disclaimer.all()
                    if not od.is_active
                ]
            )

            cache.set(key, has_disclaimer, timeout=600)
    else:
        has_disclaimer = bool(cache.get(key))
    return has_disclaimer


def active_data_privacy_cache_key(user):
    from accounts.models import DataPrivacyPolicy
    current_version = DataPrivacyPolicy.current_version()
    return 'user_{}_active_data_privacy_agreement_version_{}'.format(
        user.id, current_version
    )


def has_active_data_privacy_agreement(user):
    key = active_data_privacy_cache_key(user)
    if cache.get(key) is None:
        has_active_agreement = bool(
            [
                True for dp in user.data_privacy_agreement.all()
                if dp.is_active
            ]
        )
        cache.set(key, has_active_agreement, timeout=600)
    else:
        has_active_agreement = bool(cache.get(key))
    return has_active_agreement
