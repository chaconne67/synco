"""Re-export split project views to preserve existing import paths."""

# ruff: noqa: F401

from projects.views._helpers import (
    _build_overview_context,
    _build_tab_context,
    _create_receive_resume_action,
    _filter_params_string,
    _get_draft_context,
    _has_pending_approval,
)
from projects.views.actions import (
    action_complete,
    action_create,
    action_propose_next,
    action_reschedule,
    action_skip,
)
from projects.views.applications import (
    application_actions_partial,
    application_drop,
    application_hire,
    application_restore,
    application_resume_request_email,
    application_resume_upload,
    application_resume_use_db,
    application_skip_stage,
    project_add_candidate,
)
from projects.views.approvals import (
    approval_cancel,
    approval_decide,
    approval_queue,
    auto_action_apply,
    auto_action_dismiss,
    project_auto_actions,
)
from projects.views.context import (
    project_context,
    project_context_discard,
    project_context_resume,
    project_context_save,
)
from projects.views.dashboard import dashboard
from projects.views.interviews import (
    interview_create,
    interview_delete,
    interview_result,
    interview_update,
)
from projects.views.jd import (
    analyze_jd,
    jd_matching_results,
    jd_results,
    start_search_session,
)
from projects.views.postings import (
    posting_download,
    posting_edit,
    posting_generate,
    posting_site_add,
    posting_site_delete,
    posting_site_update,
    posting_sites,
)
from projects.views.project import (
    drive_picker,
    project_applications_partial,
    project_check_collision,
    project_close,
    project_create,
    project_delete,
    project_detail,
    project_list,
    project_reopen,
    project_tab_interviews,
    project_tab_overview,
    project_tab_search,
    project_tab_submissions,
    project_timeline_partial,
    project_update,
)
from projects.views.resumes import (
    link_resume_to_candidate,
    process_pending_upload,
    resume_assign_project,
    resume_discard,
    resume_link_candidate,
    resume_process_pending,
    resume_retry,
    resume_unassigned,
    resume_upload,
    resume_upload_status,
)
from projects.views.stages import (
    stage_client_submit_single,
    stage_contact_complete,
    stage_interview_complete,
    stage_pre_meeting_record,
    stage_pre_meeting_schedule,
    stage_prep_submission_confirm,
)
from projects.views.submissions import (
    draft_consultation,
    draft_consultation_audio,
    draft_convert,
    draft_finalize,
    draft_generate,
    draft_preview,
    draft_review,
    submission_batch_create,
    submission_create,
    submission_delete,
    submission_download,
    submission_draft,
    submission_feedback,
    submission_submit,
    submission_update,
)
