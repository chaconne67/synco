"""Google Drive sync service: OAuth token management, folder navigation, file download."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

TOKEN_PATH = Path(settings.BASE_DIR) / "assets" / "google_token.json"
CLIENT_SECRET_PATH = Path(settings.BASE_DIR) / "assets" / "client_secret.json"

CATEGORY_FOLDERS: list[str] = [
    "Accounting",
    "EHS",
    "Engineer",
    "Finance",
    "HR",
    "Law",
    "Logistics",
    "Marketing",
    "MD",
    "MR",
    "Plant",
    "PR+AD",
    "Procurement",
    "Production",
    "Quality",
    "R&D",
    "Sales",
    "SCM",
    "SI+IT",
    "VMD",
]

# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------


def _get_client_id() -> str:
    """Read client_id from CLIENT_SECRET_PATH JSON (handles 'installed' and 'web' keys)."""
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    key = "installed" if "installed" in data else "web"
    return data[key]["client_id"]


def _get_client_secret() -> str:
    """Read client_secret from CLIENT_SECRET_PATH JSON (handles 'installed' and 'web' keys)."""
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    key = "installed" if "installed" in data else "web"
    return data[key]["client_secret"]


def _save_token(creds: Credentials) -> None:
    """Persist refreshed credentials to TOKEN_PATH."""
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())


def _get_credentials() -> Credentials:
    """Load OAuth token from TOKEN_PATH, auto-refresh if expired, save refreshed token.

    Raises RuntimeError if credentials are invalid and cannot be refreshed.
    """
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    # Token file may lack client_id/client_secret (e.g., manually created).
    # Inject from client_secret.json if missing.
    if "client_id" not in token_data or "client_secret" not in token_data:
        token_data["client_id"] = _get_client_id()
        token_data["client_secret"] = _get_client_secret()
        # Persist so future loads don't need this fixup
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f)

    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    raise RuntimeError(
        "Invalid Google credentials. Please re-authenticate via OAuth flow."
    )


# ---------------------------------------------------------------------------
# Drive service
# ---------------------------------------------------------------------------


def get_drive_service():
    """Build and return a Google Drive API v3 service object."""
    creds = _get_credentials()
    return build("drive", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Folder / file operations
# ---------------------------------------------------------------------------


def find_category_folder(service, parent_id: str, folder_name: str) -> str | None:
    """Find a folder by *folder_name* under *parent_id*.

    Returns the folder ID if found, else ``None``.
    """
    query = (
        f"'{parent_id}' in parents"
        f" and name = '{folder_name}'"
        f" and mimeType = 'application/vnd.google-apps.folder'"
        f" and trashed = false"
    )
    response = (
        service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def list_files_in_folder(service, folder_id: str, page_size: int = 1000) -> list[dict]:
    """List .doc/.docx files in *folder_id*, paginating with nextPageToken.

    Returns a list of dicts with keys: id, name, mimeType, size, modifiedTime.
    """
    query = (
        f"'{folder_id}' in parents"
        " and ("
        "mimeType = 'application/msword'"
        " or mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
        ")"
        " and trashed = false"
    )
    fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime)"

    all_files: list[dict] = []
    page_token: str | None = None

    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields=fields,
                pageSize=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        all_files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return all_files


def download_file(service, file_id: str, dest_path: str, max_retries: int = 3) -> str:
    """Download a file from Drive to *dest_path* using MediaIoBaseDownload.

    Retries on transient SSL/network errors. Returns the destination path.
    """
    import time

    for attempt in range(max_retries):
        try:
            request = service.files().get_media(fileId=file_id)
            with open(dest_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _status, done = downloader.next_chunk()
            return dest_path
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            raise


def list_root_folders(service) -> list[dict]:
    """List folders at the Drive root."""
    query = (
        "'root' in parents"
        " and mimeType = 'application/vnd.google-apps.folder'"
        " and trashed = false"
    )
    response = (
        service.files().list(q=query, fields="files(id, name)", pageSize=100).execute()
    )
    return response.get("files", [])
