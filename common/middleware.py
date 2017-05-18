from django.utils.deprecation import MiddlewareMixin

from responsive.middleware import DeviceInfoMiddleware


class NewDeviceInfoMiddleware(MiddlewareMixin, DeviceInfoMiddleware):
    """Add MiddlewareMixin for new-style django middleware"""
    pass
