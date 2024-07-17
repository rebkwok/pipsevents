from django import forms

from django.template.loader import render_to_string
from django.urls import reverse

from crispy_forms.bootstrap import PrependedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, LayoutObject, Submit, Fieldset, HTML

from booking.models import Membership, MembershipItem


class Formset(LayoutObject):
    """
    Renders an entire formset, as though it were a Field.
    Accepts the names (as a string) of formset and helper as they
    are defined in the context

    Examples:
        Formset('contact_formset')
        Formset('contact_formset', 'contact_formset_helper')
    """

    template = "bootstrap4/table_inline_formset.html"

    def __init__(self, formset_context_name, helper_context_name=None,
                 template=None, label=None):

        self.formset_context_name = formset_context_name
        self.helper_context_name = helper_context_name

        # crispy_forms/layout.py:302 requires us to have a fields property
        self.fields = []

        # Overrides class variable with an instance level variable
        if template:  # pragma: no cover
            self.template = template

    def render(self, form, context, **kwargs):
        formset = context.get(self.formset_context_name)
        helper = context.get(self.helper_context_name)
        # closes form prematurely if this isn't explicitly stated
        if helper:  # pragma: no cover
            helper.form_tag = False

        context.update({'formset': formset, 'helper': helper})
        return render_to_string(self.template, context.flatten())



MembershipItemFormset = forms.inlineformset_factory(
    Membership, MembershipItem, fields=("event_type", "quantity"), can_delete=True,
)


class MembershipAddEditForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ('name', 'description', 'price', 'active')
        widgets = {
            "name": forms.TextInput(),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = True
        self.fields["price"] = forms.DecimalField(min_value=0)
        back_url = reverse('studioadmin:memberships_list')
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                "Membership Details",
                "name",
                "description",
            ),
            PrependedText('price', '£'),
            "active",
            Fieldset(
                "Monthly booking allowance",
                HTML(
                    "<small class='form-text text-muted'>Specify event types which can be booked with this membership.</small>"
                ),
                Formset("formset"),
            ),
            Submit('submit', f'Save', css_class="btn btn-success"),
            HTML(f'<a class="btn btn-secondary" href="{back_url}">Back</a>')
        )
