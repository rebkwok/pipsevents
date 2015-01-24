from django.shortcuts import render, HttpResponse, get_object_or_404


def profile(request):

    return render(request, 'account/profile.html', {'section': 'home'})