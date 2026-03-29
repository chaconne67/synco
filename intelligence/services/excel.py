import json

from common.claude import call_claude_json

KNOWN_FIELDS = {
    "name",
    "phone",
    "company_name",
    "industry",
    "region",
    "revenue_range",
    "employee_count",
    "meeting_date",
    "meeting_time",
    "memo",
    "skip",
}


def detect_header_and_map(first_rows: list[list], max_cols: int) -> dict:
    """Use Claude to detect if headers exist and map columns to Contact fields.

    Args:
        first_rows: First 6 rows of raw data (list of lists).
        max_cols: Number of columns.

    Returns:
        {"has_header": bool, "mapping": {"col_key": "field_name"}}
        - If has_header=True, col_key is the header text.
        - If has_header=False, col_key is "col_0", "col_1", etc.
    """
    rows_str = json.dumps(first_rows[:6], ensure_ascii=False, default=str)

    prompt = f"""아래는 엑셀 파일의 처음 몇 행이야. 두 가지를 판단해줘.

**1단계: 헤더 판단**
- 첫 번째 행이 컬럼 헤더(이름, 전화번호, 회사명 같은 라벨)인지, 아니면 바로 데이터인지 판단해.
- 날짜, 전화번호, 회사명 같은 실제 값이면 헤더가 아니라 데이터야.

**2단계: 컬럼 매핑**
각 컬럼을 아래 필드 중 하나에 매핑해:
- name: 대표자/CEO/담당자 이름 (한국인 이름 2~4글자)
- phone: 핸드폰/전화번호 (010-XXXX-XXXX 또는 숫자)
- company_name: 회사명/상호/업체명
- industry: 업종/업태
- region: 지역/주소/소재지
- revenue_range: 매출규모/매출액
- employee_count: 직원수/종업원수
- meeting_date: 미팅일자/방문일/날짜
- meeting_time: 미팅시간/방문시간
- memo: 비고/메모/사업자번호/사무실전화 등 유용한 부가정보
- skip: 완전히 불필요한 컬럼

원칙: 유용한 정보는 버리지 말고 memo로 분류해.

데이터 (행 단위):
{rows_str}

JSON으로만 응답:
{{"has_header": true/false, "mapping": {{"컬럼키": "필드명"}}}}

- has_header=true이면 mapping 키는 첫 행의 헤더 텍스트
- has_header=false이면 mapping 키는 "col_0", "col_1", ... (컬럼 인덱스)"""

    result = call_claude_json(prompt)

    # Sanitize mapping
    raw_mapping = result.get("mapping", {})
    sanitized = {}
    for col, field in raw_mapping.items():
        if field not in KNOWN_FIELDS:
            sanitized[col] = "memo"
        else:
            sanitized[col] = field

    return {
        "has_header": result.get("has_header", True),
        "mapping": sanitized,
    }


def classify_sheets(sheets_info: list[dict]) -> list[dict]:
    """Use Claude to classify which sheets contain contact data.

    Args:
        sheets_info: [{"name": "Sheet1", "headers": [...], "sample": [...], "rows": 50}, ...]

    Returns:
        [{"name": "Sheet1", "is_contact": true, "reason": "..."}, ...]
    """
    prompt = f"""아래 엑셀 파일의 시트 목록을 분석해서 연락처(사람/CEO/거래처) 데이터가 포함된 시트인지 판단해줘.

판단 기준:
- 연락처 시트: 이름, 전화번호, 회사명 등 사람/거래처 정보가 행 단위로 나열
- 비연락처 시트: 매출 요약, 통계, 차트 데이터, 설정, 목차 등

시트 정보:
{json.dumps(sheets_info, ensure_ascii=False)}

JSON 배열로만 응답. 형식:
[{{"name": "시트명", "is_contact": true/false, "reason": "한줄 사유"}}]"""

    return call_claude_json(prompt, timeout=30)
