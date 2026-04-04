from data_extraction.services.filename import group_by_person, parse_filename


class TestParseFilename:
    def test_standard_format(self):
        result = parse_filename("강솔찬.85.나디아.현대엠시트.인천대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_two_digit_year_90s(self):
        result = parse_filename("김영희.92.삼성전자.서울대.doc")
        assert result["name"] == "김영희"
        assert result["birth_year"] == 1992

    def test_two_digit_year_00s(self):
        result = parse_filename("박지민.01.LG.doc")
        assert result["name"] == "박지민"
        assert result["birth_year"] == 2001

    def test_four_digit_year(self):
        result = parse_filename("이수정.1988.SK.doc")
        assert result["name"] == "이수정"
        assert result["birth_year"] == 1988

    def test_docx_extension(self):
        result = parse_filename("최민수.79.현대.docx")
        assert result["name"] == "최민수"
        assert result["birth_year"] == 1979

    def test_no_birth_year(self):
        result = parse_filename("홍길동.이력서.doc")
        assert result["name"] == "홍길동"
        assert result["birth_year"] is None

    def test_extra_metadata(self):
        result = parse_filename("강원용.81.나디아.현대엠시트.인천대.doc")
        assert result["name"] == "강원용"
        assert result["birth_year"] == 1981
        assert "나디아" in result["extra"]

    def test_hyphen_separator(self):
        result = parse_filename("강솔찬-85-현대엠시트.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_underscore_separator(self):
        result = parse_filename("강솔찬_85_현대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_parentheses_year(self):
        result = parse_filename("강솔찬(85).현대.doc")
        assert result["name"] == "강솔찬"
        assert result["birth_year"] == 1985

    def test_unparseable(self):
        result = parse_filename("이력서양식.doc")
        assert result["name"] is None
        assert result["birth_year"] is None
        assert result["extra"] == []


class TestGroupByPerson:
    def test_single_file(self):
        files = [
            {
                "file_name": "강솔찬.85.나디아.doc",
                "modified_time": "2024-01-01T00:00:00",
            },
        ]
        groups = group_by_person(files)
        assert len(groups) == 1
        assert groups[0]["parsed"]["name"] == "강솔찬"
        assert groups[0]["primary"] is files[0]
        assert groups[0]["others"] == []

    def test_multiple_versions(self):
        files = [
            {
                "file_name": "강솔찬.85.나디아.doc",
                "modified_time": "2024-01-01T00:00:00",
            },
            {
                "file_name": "강솔찬.85.현대엠시트.doc",
                "modified_time": "2024-06-15T00:00:00",
            },
        ]
        groups = group_by_person(files)
        assert len(groups) == 1
        # Newest file should be primary
        assert groups[0]["primary"] is files[1]
        assert groups[0]["others"] == [files[0]]

    def test_different_people(self):
        files = [
            {
                "file_name": "강솔찬.85.나디아.doc",
                "modified_time": "2024-01-01T00:00:00",
            },
            {
                "file_name": "김영희.92.삼성전자.doc",
                "modified_time": "2024-01-01T00:00:00",
            },
        ]
        groups = group_by_person(files)
        assert len(groups) == 2

    def test_unparseable_files_as_individual_groups(self):
        files = [
            {"file_name": "이력서양식.doc", "modified_time": "2024-01-01T00:00:00"},
            {
                "file_name": "강솔찬.85.나디아.doc",
                "modified_time": "2024-01-01T00:00:00",
            },
        ]
        groups = group_by_person(files)
        assert len(groups) == 2
