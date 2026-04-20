"""Query scope helpers for work-type entities.

Work entities: Project, Application, ActionItem, Interview, Submission.
Info entities (Candidate, Client, references) bypass scope — gated only by
`accounts.decorators.level_required(1)`.

Level 2+ / is_superuser: full access.
Level 1 (staff): limited to assigned/own records per _WORK_SCOPE_RULES.
Level 0 (pending): empty.
"""

from django.db.models import Q
from django.http import Http404


def _project_rule(user):
    return Q(assigned_consultants=user)


def _application_rule(user):
    return Q(project__assigned_consultants=user)


def _action_item_rule(user):
    return Q(assigned_to=user) | Q(application__project__assigned_consultants=user)


def _interview_rule(user):
    return Q(action_item__application__project__assigned_consultants=user)


def _submission_rule(user):
    return Q(application__project__assigned_consultants=user)


def _build_rules():
    from projects.models import (
        ActionItem,
        Application,
        Interview,
        Project,
        Submission,
    )

    return {
        Project: _project_rule,
        Application: _application_rule,
        ActionItem: _action_item_rule,
        Interview: _interview_rule,
        Submission: _submission_rule,
    }


_WORK_SCOPE_RULES = None


def _rule_for(model):
    global _WORK_SCOPE_RULES
    if _WORK_SCOPE_RULES is None:
        _WORK_SCOPE_RULES = _build_rules()
    rule = _WORK_SCOPE_RULES.get(model)
    if rule is None:
        raise ValueError(
            f"No work-scope rule for {model.__name__}. "
            f"Add one in accounts/services/scope.py::_build_rules."
        )
    return rule


def scope_work_qs(qs, user):
    """Filter a work-entity queryset by the user's permission level.

    - Level 0 (pending): empty queryset.
    - Level 1 (staff): filtered to assigned/own per model rule.
    - Level 2+ or is_superuser: full queryset.
    """
    if user.is_superuser or user.level >= 2:
        return qs
    if user.level < 1:
        return qs.none()
    rule = _rule_for(qs.model)
    return qs.filter(rule(user)).distinct()


def get_scoped_object_or_404(model, user, **lookup):
    """Fetch a work-model instance subject to the user's scope.

    Level 2+ / superuser: behaves like django.shortcuts.get_object_or_404.
    Level 1: raises Http404 if the user is not assigned to the object.
    Level 0: always Http404.
    """
    qs = scope_work_qs(model.objects.all(), user)
    try:
        return qs.get(**lookup)
    except model.DoesNotExist:
        raise Http404(f"{model.__name__} matching query does not exist.")
