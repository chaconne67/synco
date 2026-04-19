from django.db import migrations


KEYWORD_MAP = [
    ("바이오/제약", ["바이오", "제약", "신약", "pharma", "bio"]),
    ("헬스케어/의료기기", ["헬스케어", "의료기기", "덴탈", "dental", "medical"]),
    ("IT/SW", ["it", "sw", "소프트웨어", "software", "saas", "플랫폼", "인터넷"]),
    ("소재/부품", ["소재", "부품", "반도체", "디스플레이", "화학"]),
    ("금융/캐피탈", ["금융", "캐피탈", "은행", "증권", "보험", "투자"]),
    ("소비재/패션", ["소비재", "패션", "식품", "리테일", "retail", "consumer"]),
    ("환경/유틸리티", ["환경", "에너지", "유틸리티", "energy", "utility"]),
    ("모빌리티/제조", ["모빌리티", "자동차", "mobility", "제조", "manufacturing"]),
    ("미디어/엔터", ["미디어", "엔터", "콘텐츠", "방송", "media"]),
    ("건설/부동산", ["건설", "부동산", "construction", "real estate"]),
]


def classify(industry_text: str) -> str:
    text = (industry_text or "").strip().lower()
    if not text:
        return "기타"
    for category, keywords in KEYWORD_MAP:
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "기타"


def forwards(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    for client in Client.objects.all():
        client.industry = classify(client.industry)
        client.save(update_fields=["industry"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0003_client_description_client_logo_client_website"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
