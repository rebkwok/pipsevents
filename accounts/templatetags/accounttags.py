from django import template


register = template.Library()


@register.simple_tag
def modify_redirect_field_value(ret_url):
    if ret_url and ret_url in ['/accounts/password/change/', '/accounts/password/set/']:
        return '/accounts/profile'
    return ret_url


@register.simple_tag
def get_user_providers(user):
    if user.is_anonymous:
        return []
    return [socialaccount.provider for socialaccount in user.socialaccount_set.all()]
