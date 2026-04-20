def rbac_context(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"current_user_level": None, "is_superuser": False}
    return {
        "current_user_level": user.level,
        "is_superuser": user.is_superuser,
    }
