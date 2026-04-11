"""RBAC decorators. Must be used after @login_required."""
from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from accounts.models import Membership


def _redirect_named(name, fallback):
    """Redirect to a named URL, falling back to a literal path if not yet registered."""
    try:
        return redirect(reverse(name))
    except NoReverseMatch:
        return redirect(fallback)


def membership_required(view_func):
    """Ensure user has an active Membership. Redirect otherwise."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            membership = request.user.membership
        except Membership.DoesNotExist:
            return _redirect_named("invite_code", "/accounts/invite/")

        if membership.status == "pending":
            return _redirect_named("pending_approval", "/accounts/pending/")
        if membership.status == "rejected":
            return _redirect_named("rejected", "/accounts/rejected/")

        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    """Ensure user has one of the specified roles. Returns 403 otherwise."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                membership = request.user.membership
            except Membership.DoesNotExist:
                return _redirect_named("invite_code", "/accounts/invite/")

            if membership.status != "active":
                return _redirect_named("pending_approval", "/accounts/pending/")

            if membership.role not in roles:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
