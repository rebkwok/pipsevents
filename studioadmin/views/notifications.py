from typing import Any, Dict
from django import forms
from django.contrib import messages
from django.template.response import TemplateResponse

from ckeditor.widgets import CKEditorWidget
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Hidden, Layout, Submit, Div

from notices.models import Notice

from booking.models import Banner
from studioadmin.views.helpers import is_instructor_or_staff


class BannerForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        banner_type = kwargs.pop("banner_type")
        super().__init__(*args, **kwargs)
        start = self.fields["start_datetime"]
        start.input_formats=('%d %b %Y %H:%M',)
        start.label = "Start date & time"
        end = self.fields["end_datetime"]
        end.input_formats=('%d %b %Y %H:%M',)
        end.label = "End date & time"
        end.help_text = "Leave blank if the banner should never expire"
        self.helper = FormHelper()
        submit_button = Submit('submit', 'Save')
        
        self.helper.layout = Layout(
            Hidden("banner_type", banner_type),
            "content",
            "colour",
            Div("start_datetime", css_class="form-group"),
            Div("end_datetime", css_class="form-group"),
            submit_button
        )
    
    class Meta:
        model = Banner
        fields = ("content", "colour", "start_datetime", "end_datetime", "banner_type")
        widgets = {
            'start_datetime': forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    'id': "start_datetimepicker",
                    "autocomplete": "off",
                },
                format='%d %b %Y %H:%M'
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    'id': "end_datetimepicker",
                    "autocomplete": "off",
                },
                format='%d %b %Y %H:%M'
            ),
            'content': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
        }


class NoticeForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        expires = self.fields["expires_at"]
        expires.input_formats=('%d %b %Y %H:%M',)
        expires.label = "Expires at:"
        expires.help_text = "Leave blank if the notice should never expire"

        starts = self.fields["starts_at"]
        starts.input_formats=('%d %b %Y %H:%M',)
        starts.label = "Starts at:"
        starts.help_text = "Leave blank if the notice should start immediately"
        
        timeout = self.fields["timeout_seconds"]
        timeout.label = "Timeout (in seconds); the notice will be shown again after this time."
        timeout.help_text = "Leave blank to show once only. Note: 1 hour=3600s; 1 day=86400s; 1 week=604800s."
        self.helper = FormHelper()
        submit_button = Submit('submit', 'Save')
        
        self.helper.layout = Layout(
            "title",
            "content",
            "timeout_seconds",
            Div("starts_at", css_class="form-group"),
            Div("expires_at", css_class="form-group"),
            submit_button
        )
    
    class Meta:
        model = Notice
        fields = ("title", "content", "timeout_seconds", "starts_at", "expires_at")
        widgets = {
            'starts_at': forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    'id': "start_datetimepicker",
                    "autocomplete": "off",
                },
                format='%d %b %Y %H:%M'
            ),
            'expires_at': forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    'id': "end_datetimepicker",
                    "autocomplete": "off",
                },
                format='%d %b %Y %H:%M'
            ),
            'content': CKEditorWidget(
                attrs={'class': 'form-control container-fluid'},
                config_name='studioadmin_min',
            ),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        expires_at = cleaned_data.get("expires_at")
        if starts_at and expires_at and starts_at > expires_at:
            self.add_error("starts_at", "Start date must be before expiry date")
            self.add_error("expires_at", "Expiry date must be after start date")
        return cleaned_data


def get_banner_form(banner_type, data=None):
    banner = Banner.objects.filter(banner_type=banner_type).first()
    kwargs = {"banner_type": banner_type}
    if banner:
        kwargs["instance"] = banner
    if data:
        kwargs["data"] = data
    return BannerForm(**kwargs)


@is_instructor_or_staff
def all_users_banner_view(request):
    context = {
        "studioadmin": True,
        "sidenav_selection": "all_banner"
    }
    if request.method == "POST":
        form = get_banner_form("banner_all", request.POST)
        form.is_valid()
        form.save()
        messages.success(request, "Banner updated")
    else:
        form = get_banner_form("banner_all")
    return TemplateResponse(
            request, "studioadmin/banner_all_users.html", {**context, 'form': form}
        )

@is_instructor_or_staff
def new_users_banner_view(request):
    context = {
        "studioadmin": True,
        "sidenav_selection": "new_banner"
    }
    if request.method == "POST":
        form = get_banner_form("banner_new", request.POST)
        form.is_valid()
        form.save()
        messages.success(request, "Banner updated")
    else:
        form = get_banner_form("banner_new")
    return TemplateResponse(
            request, "studioadmin/banner_new_users.html", {**context, 'form': form}
        )


def popup_notification_view(request):
    context = {
        "studioadmin": True,
        "sidenav_selection": "popup_notification"
    }
    notice = Notice.latest_notice()
    kwargs = {}
    if notice:
        kwargs["instance"] = notice
    
    if request.method == "POST":
        form = NoticeForm(**kwargs, data=request.POST)
        if form.is_valid():
            form.save()
            if notice and (set(form.changed_data) & {'title', 'content', 'timeout_seconds'}):
                notice.version += 1
                notice.save()
            messages.success(request, "Notice saved")
    else:
        form = form = NoticeForm(**kwargs)
    
    if notice:
        context["has_started"] = notice.has_started()
        context["has_expired"] = notice.has_expired()
        kwargs["instance"] = notice
    return TemplateResponse(
            request, "studioadmin/popup_notification.html", {**context, 'form': form}
        )

