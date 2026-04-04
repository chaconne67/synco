from unittest.mock import MagicMock, mock_open, patch

import pytest

from data_extraction.services.drive import (
    CLIENT_SECRET_PATH,
    SCOPES,
    TOKEN_PATH,
    _get_client_id,
    _get_client_secret,
    _get_credentials,
    _save_token,
    discover_folders,
    download_file,
    find_category_folder,
    get_drive_service,
    list_files_in_folder,
    list_root_folders,
    parse_drive_id,
)


class TestConstants:
    def test_scopes_is_readonly(self):
        assert SCOPES == ["https://www.googleapis.com/auth/drive.readonly"]

    def test_token_path_ends_with_expected(self):
        assert TOKEN_PATH.name == "google_token.json"

    def test_client_secret_path_ends_with_expected(self):
        assert CLIENT_SECRET_PATH.name == "client_secret.json"


class TestGetClientCredentials:
    def test_get_client_id_installed_key(self):
        mock_data = '{"installed": {"client_id": "test-id-123"}}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            assert _get_client_id() == "test-id-123"

    def test_get_client_id_web_key(self):
        mock_data = '{"web": {"client_id": "web-id-456"}}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            assert _get_client_id() == "web-id-456"

    def test_get_client_secret_installed_key(self):
        mock_data = '{"installed": {"client_secret": "secret-abc"}}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            assert _get_client_secret() == "secret-abc"

    def test_get_client_secret_web_key(self):
        mock_data = '{"web": {"client_secret": "secret-web-xyz"}}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            assert _get_client_secret() == "secret-web-xyz"


_FAKE_TOKEN_JSON = '{"token": "tok", "client_id": "cid", "client_secret": "csec"}'


class TestGetCredentials:
    @patch("data_extraction.services.drive._save_token")
    @patch("data_extraction.services.drive.Credentials.from_authorized_user_info")
    def test_valid_credentials_returned(self, mock_from_info, mock_save):
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_from_info.return_value = mock_creds

        with patch("builtins.open", mock_open(read_data=_FAKE_TOKEN_JSON)):
            result = _get_credentials()
        assert result == mock_creds
        mock_save.assert_not_called()

    @patch("data_extraction.services.drive._save_token")
    @patch("data_extraction.services.drive.Credentials.from_authorized_user_info")
    def test_expired_credentials_refreshed(self, mock_from_info, mock_save):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token"
        mock_from_info.return_value = mock_creds

        with patch("builtins.open", mock_open(read_data=_FAKE_TOKEN_JSON)):
            result = _get_credentials()
        mock_creds.refresh.assert_called_once()
        mock_save.assert_called_once_with(mock_creds)
        assert result == mock_creds

    @patch("data_extraction.services.drive.Credentials.from_authorized_user_info")
    def test_invalid_credentials_raises(self, mock_from_info):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_from_info.return_value = mock_creds

        with patch("builtins.open", mock_open(read_data=_FAKE_TOKEN_JSON)):
            with pytest.raises(RuntimeError, match="Invalid Google credentials"):
                _get_credentials()


class TestSaveToken:
    @patch("builtins.open", mock_open())
    def test_save_token_writes_json(self):
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        _save_token(mock_creds)
        handle = open
        handle.assert_called_once_with(TOKEN_PATH, "w")


class TestGetDriveService:
    @patch("data_extraction.services.drive.build")
    @patch("data_extraction.services.drive._get_credentials")
    def test_returns_service(self, mock_get_creds, mock_build):
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = get_drive_service()
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)
        assert result == mock_service


class TestFindCategoryFolder:
    def test_find_existing_folder(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [{"id": "folder-abc", "name": "Sales"}]
        }
        result = find_category_folder(mock_service, "parent-id", "Sales")
        assert result == "folder-abc"

    def test_find_nonexistent_folder(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {"files": []}
        result = find_category_folder(mock_service, "parent-id", "NonExistent")
        assert result is None


class TestListFiles:
    def test_list_files_returns_doc_files(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "강솔찬.85.현대.doc",
                    "mimeType": "application/msword",
                    "size": "12345",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                }
            ],
            "nextPageToken": None,
        }
        files = list_files_in_folder(mock_service, "folder123")
        assert len(files) == 1
        assert files[0]["name"] == "강솔찬.85.현대.doc"

    def test_list_files_pagination(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.side_effect = [
            {
                "files": [
                    {
                        "id": "f1",
                        "name": "a.doc",
                        "mimeType": "application/msword",
                        "size": "100",
                        "modifiedTime": "2024-01-01T00:00:00Z",
                    }
                ],
                "nextPageToken": "token-page2",
            },
            {
                "files": [
                    {
                        "id": "f2",
                        "name": "b.docx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "size": "200",
                        "modifiedTime": "2024-02-01T00:00:00Z",
                    }
                ],
                "nextPageToken": None,
            },
        ]
        files = list_files_in_folder(mock_service, "folder123")
        assert len(files) == 2
        assert files[0]["id"] == "f1"
        assert files[1]["id"] == "f2"


class TestDownloadFile:
    @patch("data_extraction.services.drive.MediaIoBaseDownload")
    def test_download_file_success(self, mock_download_cls):
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_service.files().get_media.return_value = mock_request

        mock_downloader = MagicMock()
        mock_download_cls.return_value = mock_downloader
        mock_downloader.next_chunk.return_value = (
            MagicMock(progress=MagicMock(return_value=1.0)),
            True,
        )

        with patch("builtins.open", mock_open()):
            result = download_file(mock_service, "file-id", "/tmp/test.doc")

        assert result == "/tmp/test.doc"
        mock_service.files().get_media.assert_called_once_with(fileId="file-id")


class TestListRootFolders:
    def test_list_root_folders(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {"id": "root1", "name": "Folder A"},
                {"id": "root2", "name": "Folder B"},
            ]
        }
        result = list_root_folders(mock_service)
        assert len(result) == 2
        assert result[0]["name"] == "Folder A"


class TestParseDriveId:
    def test_parse_drive_id_from_url(self):
        url = "https://drive.google.com/drive/folders/1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"
        result = parse_drive_id(url)
        assert result == "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"

    def test_parse_drive_id_bare(self):
        bare_id = "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"
        result = parse_drive_id(bare_id)
        assert result == "1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"

    def test_parse_drive_id_url_with_trailing_slash(self):
        url = "https://drive.google.com/drive/folders/AbCdEfGhIjKlMnOpQrStUv/"
        result = parse_drive_id(url)
        assert result == "AbCdEfGhIjKlMnOpQrStUv"


class TestDiscoverFolders:
    def test_discover_folders_returns_sorted(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {"id": "id-sales", "name": "Sales"},
                {"id": "id-hr", "name": "HR"},
                {"id": "id-eng", "name": "Engineer"},
            ],
            "nextPageToken": None,
        }
        result = discover_folders(mock_service, "parent-123")
        names = [f["name"] for f in result]
        assert names == sorted(names)

    def test_discover_folders_empty(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {
            "files": [],
            "nextPageToken": None,
        }
        result = discover_folders(mock_service, "parent-empty")
        assert result == []

    def test_discover_folders_pagination(self):
        mock_service = MagicMock()
        mock_service.files().list().execute.side_effect = [
            {
                "files": [{"id": "id-a", "name": "Accounting"}],
                "nextPageToken": "page2-token",
            },
            {
                "files": [{"id": "id-z", "name": "VMD"}],
                "nextPageToken": None,
            },
        ]
        result = discover_folders(mock_service, "parent-paged")
        assert len(result) == 2
        ids = {f["id"] for f in result}
        assert ids == {"id-a", "id-z"}
