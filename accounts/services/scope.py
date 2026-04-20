"""Query scope helpers for work-type entities (Project, Application, ActionItem, ...)."""


def scope_work_qs(qs, user, assigned_field="assigned_consultants"):
    """Filter a work-entity queryset by the user's permission level.

    - Level 0 (pending): empty queryset.
    - Level 1 (staff): only rows where the user is in `assigned_field`.
    - Level 2+ or is_superuser: full queryset.
    """
    if user.is_superuser or user.level >= 2:
        return qs

    if user.level < 1:
        return qs.none()

    filter_kwargs = {assigned_field: user}
    return qs.filter(**filter_kwargs).distinct()
