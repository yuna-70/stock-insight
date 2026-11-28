"""
공시 분류 테스트

주주환원을 '결정' 공시로 좁힌 규칙(삼성·SK 13줄을 직접 보고 8개 → 3개로 정한 것)이 유지되는지 확인한다.
'잡혀야 하는 것'과 '잡히면 안 되는 것'을 둘 다 넣어서, 규칙이 넓어져도 좁아져도 알아챈다.

실행: pytest   (저장소 맨 위에서)
"""

import pytest

from scripts.load_disclosures import classify


# ── 실적 ────────────────────────────────────────────
def test_classify_earnings():
    assert classify("연결재무제표기준영업(잠정)실적(공정공시)") == "실적"


def test_classify_earnings_correction():
    """정정 공시도 실적 (v1은 정정을 따로 빼지 않고 표시만)"""
    assert classify("[기재정정]연결재무제표기준영업(잠정)실적(공정공시)") == "실적"


# ── 주주환원: 잡혀야 하는 것 ─────────────────────────
@pytest.mark.parametrize("report_nm", [
    "현금ㆍ현물배당결정",
    "주요사항보고서(자기주식취득결정)",
    "주요사항보고서(자기주식소각결정)",   # 데이터엔 아직 없지만 규칙에 넣은 것
])
def test_classify_shareholder_return(report_nm):
    assert classify(report_nm) == "주주환원"


# ── 주주환원: 잡히면 안 되는 것 (예전에 오분류됐던 공시들) ──
@pytest.mark.parametrize("report_nm", [
    "주요사항보고서(자기주식처분결정)",              # 처분 = 주주환원과 반대 방향일 수 있음
    "자기주식처분결과보고서",
    "자기주식취득결과보고서",                        # 결과 보고 = 새 정보 적음
    "현금ㆍ현물배당을위한주주명부폐쇄(기준일)결정",    # '배당'이 들어가지만 절차 공시
    "임원ㆍ주요주주특정증권등소유상황보고서",
])
def test_classify_not_shareholder_return(report_nm):
    assert classify(report_nm) == "기타"


# ── 회사계획 ─────────────────────────────────────────
def test_classify_plan():
    assert classify("장래사업ㆍ경영계획(공정공시)") == "회사계획"