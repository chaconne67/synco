# Implementation Rulings — p11

Status: COMPLETE
Last updated: 2026-04-08T23:55:00+09:00
Rounds: 1

## Resolved Items

### Issue 1: CASCADE deletes approval on project deletion [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** ProjectApproval.project FK is CASCADE; deleting project cascades approval. Tests expect approval to survive.
- **Action:** Change ProjectApproval.project to `on_delete=SET_NULL, null=True`. Update migration. Tests can then verify approval status post-deletion.

### Issue 2: project_delete bypasses approval_cancel [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** Any org member can delete pending_approval project via project_delete, bypassing the approval flow.
- **Action:** Add `pending_approval` guard to `project_delete` view. Only `approval_cancel` can delete pending_approval projects.

### Issue 3: project_update not guarded [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Pending_approval projects can be edited via project_update.
- **Action:** Add `pending_approval` guard to `project_update`. Add test for 403 on edit.

### Issue 4: VIEWER not blocked from create [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** No existing view in the codebase checks VIEWER role. All use only @login_required + _get_org(). Adding VIEWER checks specifically to P11 would be inconsistent. This is a codebase-wide concern, not a P11 issue.
- **Action:** None for P11. Consider as separate task.

### Issue 5: Message action missing from UI [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Approval card template has no message button/input.
- **Action:** Add message textarea + button to approval card. Add test for message decision path.

### Issue 6: merge_target dropdown missing from UI [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** No UI for selecting merge target project.
- **Action:** Add dropdown showing same-client active projects. Pass candidates from view to template context. Add test for non-default merge target.

### Issue 7: decide_approval single function missing [MAJOR]
- **Resolution:** REBUTTED
- **Summary:** Design spec shows decide_approval() as an example, not a strict interface contract. The actual requirements (transition validation, atomic execution, select_for_update) are achieved by individual focused functions. Org validation is at the view level via get_object_or_404 with project__organization=org filter.
- **Action:** None. Keep separate functions.

### Issue 8: PRG pattern missing for high collision [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** POST after high collision renders inline instead of redirecting. Causes form resubmission risk.
- **Action:** Redirect to project_list with success message after approval submission. Use django messages framework or query param.

### Issue 9: Pending approval UI in project list missing [MAJOR]
- **Resolution:** ACCEPTED
- **Summary:** Project list templates (board/list/table) don't show pending badge or cancel button.
- **Action:** Add pending_approval badge + cancel button to all three list view templates. Add to File Structure.

### Issue 10: Regression fix incomplete [CRITICAL]
- **Resolution:** ACCEPTED
- **Summary:** edit/update tests that use status field will also break.
- **Action:** Make Task 7 regression fix more explicit about update tests and edit form changes.

### Issue 11: Medium collision test inadequate [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** Test allows empty medium results, doesn't verify medium warnings are shown.
- **Action:** Add fixture with known medium similarity. Test that medium results are returned and project is still created as status=new.

### Issue 12: Sidebar badge missing [MINOR]
- **Resolution:** ACCEPTED
- **Summary:** Design spec requires OWNER sidebar badge for pending approvals.
- **Action:** Add context processor for pending approval count. Modify sidebar template. OWNER-only.

## Disputed Items

(없음)
