from pathlib import Path

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".svg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


def normalize_contact_persons(raw):
    """빈 행(이름 공란)을 제거하고 스키마를 정규화."""
    out = []
    for row in raw or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "position": (row.get("position") or "").strip(),
            "phone": (row.get("phone") or "").strip(),
            "email": (row.get("email") or "").strip(),
        })
    return out


def apply_logo_upload(client, uploaded_file, *, delete=False):
    """새 로고 저장. delete=True 면 기존 파일 제거."""
    if delete:
        if client.logo:
            client.logo.delete(save=False)
        client.logo = None
        client.save(update_fields=["logo"])
        return

    if uploaded_file is None:
        return

    if client.logo:
        client.logo.delete(save=False)

    client.logo = uploaded_file
    client.save(update_fields=["logo"])


def validate_logo_file(uploaded_file):
    """form.clean_logo() 에서 호출. 문제 있으면 ValueError."""
    if uploaded_file is None:
        return
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"허용되지 않는 파일 형식입니다 ({ext}).")
    if uploaded_file.size > MAX_BYTES:
        raise ValueError("2MB 이하 이미지만 업로드할 수 있습니다.")
