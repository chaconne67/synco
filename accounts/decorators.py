"""RBAC decorators. Must be used after @login_required."""

from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


def _redirect_named(name, fallback):
    try:
        return redirect(reverse(name))
    except NoReverseMatch:
        return redirect(fallback)


def level_required(min_level):
    """Gate a view on User.level. Level 0 → pending page.

    Superusers bypass (treated as Level 2+).
    Insufficient level but authenticated → 403.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated:
                return _redirect_named("landing", "/accounts/login/")

            if user.is_superuser:
                return view_func(request, *args, **kwargs)

            if user.level == 0:
                return _redirect_named(
                    "pending_approval", "/accounts/pending/"
                )

            if user.level < min_level:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def superuser_required(view_func):
    """Allow only User.is_superuser. Others get 403."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden(
                "개발자 전용 페이지입니다."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


# Legacy — to be removed in T6 after all consumers migrate.
def membership_required(view_func):
    from accounts.models import Membership

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        try:
            membership = request.user.membership
        except Membership.DoesNotExist:
            return _redirect_named("invite_code", "/accounts/invite/")
        if membership.status == "pending":
            return _redirect_named(
                "pending_approval", "/accounts/pending/"
            )
        if membership.status == "rejected":
            return _redirect_named("rejected", "/accounts/rejected/")
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*roles):
    from accounts.models import Membership

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                membership = request.user.membership
            except Membership.DoesNotExist:
                return _redirect_named("invite_code", "/accounts/invite/")
            if membership.status != "active":
                return _redirect_named(
                    "pending_approval", "/accounts/pending/"
                )
            if membership.role not in roles:
                return HttpResponseForbidden(
                    "이 페이지에 접근할 권한이 없습니다."
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
