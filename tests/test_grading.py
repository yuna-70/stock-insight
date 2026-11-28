"""
채점 기준 테스트

채점 함수가 틀리면 점수도 틀린다 → 기준마다 '통과해야 하는 요약'과 '걸려야 하는 요약'을 넣어 확인한다.
(채점기를 채점하는 테스트)
각 테스트는 GOOD에서 '한 부분만' 바꾼 요약으로, 확인하는 기준 함수 하나만 부른다.

실행: pytest   (저장소 맨 위에서)
"""

from app.llm.grading import (
    clean_numbers,
    direction_correct,
    evidence_covers,
    grade,
    has_key_number,
    length_ok,
    no_advice,
)
from app.llm.summarizer import DisclosureSummary

# 입력: 양수 %(13.85)와 음수 %(-57.7)가 둘 다 있게 → 방향 검사를 양쪽으로
MESSAGE = (
    "매출액 / 당해실적: 당기 1,952,532억원, 전기대비 13.85%\n"
    "당기순이익 / 당해실적: 전기대비 -57.7%"
)

# 7개 기준을 전부 통과하는 좋은 요약
GOOD = DisclosureSummary(
    short_summary="매출 1,952,532억원, 전기 대비 13.85% 증가",
    summary=(
        "매출액은 1,952,532억원으로 전기 대비 13.85% 증가했습니다. "
        "당기순이익은 전기 대비 57.7% 감소했습니다. "
        "매출은 늘었지만 순이익은 줄었습니다."
    ),
    evidence=["1,952,532억원", "13.85%", "57.7%"],
)


def with_changes(**changes) -> DisclosureSummary:
    """GOOD을 복사하면서 일부 칸만 바꾼 요약 (한 기준만 깨뜨리려고)"""
    return GOOD.model_copy(update=changes)


# ── 전체 ────────────────────────────────────────────
def test_good_summary_passes_all():
    result = grade(GOOD, MESSAGE)
    assert all(result.values()), result  # 실패하면 어느 기준이 False인지 같이 보여줌


# ── 기준 2: 방향 ────────────────────────────────────
def test_direction_wrong_up():
    """입력은 -57.7인데 '증가'라고 씀 → 걸려야 함 (기준 1은 부호를 떼서 못 잡음)"""
    out = with_changes(summary="당기순이익은 전기 대비 57.7% 증가했습니다. 좋습니다. 그렇습니다.")
    assert direction_correct(out, MESSAGE) is False


def test_direction_wrong_down():
    """입력은 +13.85인데 '감소'라고 씀 → 걸려야 함"""
    out = with_changes(summary="매출액은 전기 대비 13.85% 감소했습니다. 그렇습니다. 그렇습니다.")
    assert direction_correct(out, MESSAGE) is False


def test_direction_no_word():
    """방향 단어가 없으면 판단 불가 → 통과 (애매하면 떨어뜨리지 않음)"""
    out = with_changes(summary="당기순이익 변동률은 57.7%입니다. 그렇습니다. 그렇습니다.")
    assert direction_correct(out, MESSAGE) is True


# ── 기준 3: 근거 일치 ───────────────────────────────
def test_evidence_missing():
    """본문엔 13.85가 있는데 evidence엔 없음 → 근거 없는 숫자"""
    out = with_changes(evidence=["1,952,532억원", "57.7%"])
    assert evidence_covers(out, MESSAGE) is False


# ── 기준 4: 길이 ────────────────────────────────────
def test_length_one_sentence():
    out = with_changes(summary="매출액은 1,952,532억원입니다.")
    assert length_ok(out, MESSAGE) is False


# ── 기준 5: 투자 권유 ───────────────────────────────
def test_advice_word():
    out = with_changes(
        summary=GOOD.summary.replace("줄었습니다.", "줄었으니 매수를 추천합니다.")
    )
    assert no_advice(out, MESSAGE) is False


# ── 기준 6: 핵심 숫자 ───────────────────────────────
def test_no_key_number():
    out = with_changes(short_summary="매출이 늘었습니다")
    assert has_key_number(out, MESSAGE) is False


# ── 기준 7: 군더더기 ────────────────────────────────
def test_dirty_numbers():
    """v1에서 나왔던 '.00' (조원→억원 변환 흔적)"""
    out = with_changes(short_summary="매출 1,952,532.00억원")
    assert clean_numbers(out, MESSAGE) is False