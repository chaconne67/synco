from accounts.models import Membership


def membership(request):
    """Inject current user's membership into template context."""
    if not request.user.is_authenticated:
        return {"membership": None}

    try:
        m = request.user.membership
        if m.status != "active":
            return {"membership": None}
        return {"membership": m}
    except Membership.DoesNotExist:
        return {"membership": None}
