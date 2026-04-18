"""프로젝트 서칭 도구 — DB에서 후보자를 선택해 Application으로 등록."""

from __future__ import annotations

from candidates.models import Candidate
from projects.models import Application


def add_candidates_to_project(project, candidate_ids, created_by=None):
    """주어진 후보자 ID 목록을 프로젝트에 Application으로 추가. 이미 존재하면 건너뜀.

    Returns: 새로 생성된 Application 인스턴스 리스트.
    """
    existing_ids = set(
        Application.objects.filter(
            project=project, candidate_id__in=candidate_ids
        ).values_list("candidate_id", flat=True)
    )
    new_ids = [cid for cid in candidate_ids if cid not in existing_ids]
    if not new_ids:
        return []

    candidates = Candidate.objects.filter(id__in=new_ids)
    return [
        Application.objects.create(
            project=project,
            candidate=c,
            created_by=created_by,
        )
        for c in candidates
    ]
