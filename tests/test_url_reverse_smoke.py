"""Smoke test: project-facing URL names must resolve via reverse()."""

import uuid

import pytest
from django.urls import NoReverseMatch, get_resolver, reverse


def _collect_url_names():
    """Collect first-party URL names from the root resolver."""
    names: list[str] = []
    allowed_namespaces = {
        "accounts",
        "candidates",
        "clients",
        "reference",
        "voice",
        "projects",
        "telegram",
        "superadmin",
        "news",
    }
    allowed_global = {"home", "dashboard", "team"}

    def visit(patterns, namespace_prefix=""):
        for pattern in patterns:
            subpatterns = getattr(pattern, "url_patterns", None)
            if subpatterns is not None:
                namespace = getattr(pattern, "namespace", None)
                if namespace and namespace not in allowed_namespaces:
                    continue
                next_prefix = f"{namespace_prefix}{namespace}:" if namespace else namespace_prefix
                visit(subpatterns, next_prefix)
                continue

            name = getattr(pattern, "name", None)
            if not name:
                continue
            full_name = f"{namespace_prefix}{name}"
            if namespace_prefix or name in allowed_global:
                names.append(full_name)

    visit(get_resolver().url_patterns)
    return sorted(set(names))


_PLACEHOLDER_UUID = uuid.uuid4()
_CANDIDATE_KWARGS = [
    {},
    {"pk": _PLACEHOLDER_UUID},
    {"user_id": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "sub_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "interview_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "site_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "action_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "resume_pk": _PLACEHOLDER_UUID},
    {"pk": _PLACEHOLDER_UUID, "contract_pk": _PLACEHOLDER_UUID},
    {"resume_pk": _PLACEHOLDER_UUID, "project_pk": _PLACEHOLDER_UUID},
    {"appr_pk": _PLACEHOLDER_UUID},
]


@pytest.mark.parametrize("name", _collect_url_names())
def test_url_reverses_with_some_candidate(name):
    last_error = None
    for kwargs in _CANDIDATE_KWARGS:
        try:
            url = reverse(name, kwargs=kwargs)
            assert url
            return
        except NoReverseMatch as exc:
            last_error = exc
    raise AssertionError(
        f"URL name '{name}' could not be reversed with known kwargs. "
        f"Last error: {last_error}"
    )
