"""Seed UniversityTier with the 50 Korean universities previously hardcoded
as alias map in integrity.py — moved here as the single source of truth.

Backfill is idempotent (get_or_create) so re-running is safe. Tier is left
empty intentionally; 검수자가 점진적으로 분류한다.
"""

from __future__ import annotations

from django.db import migrations


# (canonical 한글, 영문 표기, alias 변형들)
SEED = [
    ("동국대학교", "Dongguk University", ["Dongguk Univ", "The University of Dongguk", "The Graduate School of Dongguk"]),
    ("한국외국어대학교", "Hankuk University of Foreign Studies", ["Hankuk University of Foreign Language", "Hankuk Univ of Foreign Studies", "HUFS"]),
    ("한국해양대학교", "Korea Maritime and Ocean University", ["Korea Maritime University"]),
    ("고려대학교", "Korea University", ["Korea Univ"]),
    ("서울대학교", "Seoul National University", ["SNU"]),
    ("연세대학교", "Yonsei University", ["Yonsei Univ"]),
    ("한양대학교", "Hanyang University", ["Hanyang Univ"]),
    ("성균관대학교", "Sungkyunkwan University", ["SKKU"]),
    ("이화여자대학교", "Ewha Womans University", ["Ewha Univ", "Ewha"]),
    ("서강대학교", "Sogang University", ["Sogang Univ"]),
    ("중앙대학교", "Chung-Ang University", ["Chung Ang University", "Chungang University", "CAU"]),
    ("경희대학교", "Kyung Hee University", ["Kyunghee University", "KHU"]),
    ("한국과학기술원", "KAIST", ["Korea Advanced Institute of Science and Technology"]),
    ("포항공과대학교", "POSTECH", ["Pohang University of Science and Technology"]),
    ("단국대학교", "Dankook University", ["The University of Dankook", "The Graduate School of Dankook"]),
    ("건국대학교", "Konkuk University", []),
    ("동덕여자대학교", "Dongduk Women's University", ["Dongduk Womans University"]),
    ("서울여자대학교", "Seoul Women's University", ["Seoul Womens University"]),
    ("숙명여자대학교", "Sookmyung Women's University", ["Sookmyung Womens University"]),
    ("성신여자대학교", "Sungshin Women's University", ["Sungshin Womens University"]),
    ("덕성여자대학교", "Duksung Women's University", ["Duksung Womans University"]),
    ("광운대학교", "Kwangwoon University", []),
    ("국민대학교", "Kookmin University", []),
    ("명지대학교", "Myongji University", []),
    ("상명대학교", "Sangmyung University", []),
    ("세종대학교", "Sejong University", []),
    ("숭실대학교", "Soongsil University", []),
    ("아주대학교", "Ajou University", []),
    ("인하대학교", "Inha University", []),
    ("전남대학교", "Chonnam National University", ["Jeonnam National University"]),
    ("전북대학교", "Chonbuk National University", ["Jeonbuk National University"]),
    ("충남대학교", "Chungnam National University", []),
    ("충북대학교", "Chungbuk National University", []),
    ("강원대학교", "Kangwon National University", []),
    ("경상국립대학교", "Gyeongsang National University", ["Gyeongsang Nat'l University"]),
    ("경북대학교", "Kyungpook National University", ["KNU"]),
    ("부산대학교", "Pusan National University", ["PNU"]),
    ("제주대학교", "Jeju National University", []),
    ("한국기술교육대학교", "Korea University of Technology and Education", ["KOREATECH"]),
    ("서울과학기술대학교", "Seoul National University of Science and Technology", ["SeoulTech"]),
    ("한경국립대학교", "Hankyong National University", []),
    ("한밭대학교", "Hanbat National University", []),
    ("공주대학교", "Kongju National University", []),
    ("강남대학교", "Kangnam University", []),
    ("가천대학교", "Gachon University", []),
    ("을지대학교", "Eulji University", []),
    ("차의과학대학교", "CHA University", []),
    ("홍익대학교", "Hongik University", []),
    ("한성대학교", "Hansung University", []),
    ("동아대학교", "Dong-A University", ["Donga University"]),
]


def seed_universities(apps, schema_editor):
    UniversityTier = apps.get_model("clients", "UniversityTier")
    for name, name_en, aliases in SEED:
        UniversityTier.objects.get_or_create(
            name=name,
            country="KR",
            defaults={
                "name_en": name_en,
                "tier": "",
                "aliases": aliases,
                "auto_added": False,
                "needs_review": True,  # tier 미부여라 검수 대기
                "notes": "Seeded from integrity.py alias map (2026-04 verification).",
            },
        )


def unseed_universities(apps, schema_editor):
    UniversityTier = apps.get_model("clients", "UniversityTier")
    UniversityTier.objects.filter(
        notes__startswith="Seeded from integrity.py alias map"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0002_universitytier_aliases_universitytier_auto_added_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_universities, reverse_code=unseed_universities),
    ]
