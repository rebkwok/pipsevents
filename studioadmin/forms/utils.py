from django import forms


class StatusFilter(forms.Form):

    status_choice = forms.ChoiceField(
        widget=forms.Select(attrs={'onchange': "this.form.submit()"}),
        choices=(('OPEN', 'Open bookings only'),
                 ('CANCELLED', 'Cancelled Bookings only'),
                 ('ALL', 'All'),),
    )


day = 24
week = day * 7

cancel_choices = (
    (day * 0, '0 hours'),
    (day * 1, '24 hours'),
    (day * 2, '2 days'),
    (day * 3, '3 days'),
    (day * 4, '4 days'),
    (day * 5, '5 days'),
    (day * 6, '6 days'),
    (week, '1 week'),
    (week * 2, '2 weeks'),
    (week * 3, '3 weeks'),
    (week * 4, '4 weeks'),
    (week * 5, '5 weeks'),
    (week * 6, '6 weeks'),
)
