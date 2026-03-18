from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def platform_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("/platform/")


def admin_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("/platform/")

