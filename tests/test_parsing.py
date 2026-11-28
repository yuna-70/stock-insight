"""
실적 표 파싱 테스트

인터넷(DART) 없이 표 모양만 직접 넣어서, 지금까지 잡은 함정들이 다시 생기지 않는지 확인한다.
(fetch와 parse를 나눠둔 덕분에 가능)

실행: pytest   (저장소 맨 위에서)
"""

from decimal import Decimal

import pytest

from scripts.explore_numbers import find_money_unit, parse_earnings, to_number

# ── 테스트용 표 (원문에서 복사한 그대로) ────────────────
SAMPLE_ROWS = [
    ["1. 연결실적내용", "단위 : 억원, %"],
    ["매출액", "당해실적", "1,952,532", "1,714,995", "13.85", "-", "860,617", "126.88", "-"],
    ["누계실적", "5,006,261", "-", "-", "-", "2,397,686", "108.80", "-"],   # rowspan: 항목 이름 없음
    ["전화번호", "02-2255-9000"],                                            # 숫자 줄 아님 → 빠져야 함
]


# ── to_number ───────────────────────────────────────
def test_to_number_comma():
    """쉼표가 든 글자 → 숫자"""
    assert to_number("1,952,532") == Decimal("1952532")


def test_to_number_dash_is_none():
    """'-'는 값 없음(None). 0과 뜻이 다르다"""
    assert to_number("-") is None


def test_to_number_negative():
    """마이너스 증감율은 None이 아니라 음수 (SK하이닉스 -58.7%)"""
    assert to_number("-58.7") == Decimal("-58.7")


# ── find_money_unit ─────────────────────────────────
def test_find_money_unit():
    """표의 '단위 : 억원, %' 칸에서 돈 단위만"""
    assert find_money_unit(SAMPLE_ROWS) == "억원"


def test_find_money_unit_unknown():
    """처음 보는 단위면 멈춰야 함 (모른 채 저장하면 만 배 차이 사고)"""
    with pytest.raises(ValueError):
        find_money_unit([["단위 : 엔, %"]])


# ── parse_earnings ──────────────────────────────────
def test_parse_count():
    """숫자 줄 2개 × 기간 5개 = 10개. 전화번호 줄은 빠짐"""
    results = parse_earnings(SAMPLE_ROWS)
    assert len(results) == 10


def test_parse_rowspan():
    """누계실적 줄(항목 이름 없음)도 바로 위 항목 '매출액'으로"""
    results = parse_earnings(SAMPLE_ROWS)
    cumulative = [r for r in results if r[1] == "누계실적"]   # (item, scope, period, value, unit)
    assert all(r[0] == "매출액" for r in cumulative)


def test_parse_unit_conversion():
    """조원 표 → 억원으로 (195.25조원 = 1,952,500억원)"""
    rows = [
        ["1. 연결실적내용", "단위 : 조원, %"],
        ["매출액", "당해실적", "195.25", "171.50", "13.85", "-", "86.06", "126.88", "-"],
    ]
    results = parse_earnings(rows)
    current = next(r for r in results if r[2] == "당기")       # 기간이 '당기'인 첫 줄
    assert current[3] == Decimal("1952500")
    assert current[4] == "억원"