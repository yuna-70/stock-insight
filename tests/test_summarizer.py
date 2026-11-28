"""
요약 입력·검증 함수 테스트 (LLM은 부르지 않음)

- fmt: .00 없애기(v2), None은 '없음'
- extract_numbers: 부호 떼기(v2, SK하이닉스 -58.7% 오탐 방지)
- find_unknown_numbers: 지어낸 숫자, 부분 일치('1,952'), 본문에만 있는 숫자까지 잡기

실행: pytest   (저장소 맨 위에서)
"""

from decimal import Decimal

from app.llm.summarizer import (
    DisclosureSummary,
    extract_numbers,
    find_unknown_numbers,
    fmt,
)

# build_message가 만드는 모양의 입력 (검증할 때 '정답지')
MESSAGE = "매출액 / 당해실적: 당기 1,952,532억원, 전기대비 13.85%, 전기대비 -58.7%"


def make_summary(short_summary: str, summary: str, evidence: list[str]) -> DisclosureSummary:
    """테스트용 요약 객체 만들기 (LLM 대신 직접)"""
    return DisclosureSummary(short_summary=short_summary, summary=summary, evidence=evidence)


# ── fmt ─────────────────────────────────────────────
def test_fmt_none():
    assert fmt(None, "억원") == "없음"


def test_fmt_drop_zero_decimal():
    """v2: 조원→억원 변환에서 생긴 .00 없애기"""
    assert fmt(Decimal("1952500.00"), "억원") == "1,952,500억원"


def test_fmt_keep_real_decimal():
    """진짜 소수는 그대로"""
    assert fmt(Decimal("13.85"), "%") == "13.85%"


# ── extract_numbers ─────────────────────────────────
def test_extract_numbers():
    assert extract_numbers("당기 1,952,532억원, 13.85%") == {"1,952,532", "13.85"}


def test_extract_numbers_drops_sign():
    """v2: 부호를 떼고 크기만 (방향은 채점에서 따로)"""
    assert extract_numbers("전기대비 -58.7%") == {"58.7"}


# ── find_unknown_numbers ────────────────────────────
def test_verify_pass():
    """입력에 있는 숫자만 쓰면 통과"""
    out = make_summary(
        "매출 1,952,532억원",
        "매출은 1,952,532억원으로 전기 대비 13.85% 늘었습니다.",
        ["1,952,532억원", "13.85%"],
    )
    assert find_unknown_numbers(out, MESSAGE) == []


def test_verify_made_up():
    """본문(summary)에만 지어낸 숫자 → 잡아야 함 (evidence만 보면 놓침)"""
    out = make_summary(
        "매출 1,952,532억원",
        "영업이익은 9,999,999억원입니다.",
        ["1,952,532억원"],
    )
    assert find_unknown_numbers(out, MESSAGE) == ["9,999,999"]


def test_verify_partial_number():
    """진짜 숫자의 일부('1,952')는 다른 숫자 → 잡아야 함 (in 비교였다면 통과해버림)"""
    out = make_summary(
        "매출 1,952억원",
        "매출은 1,952,532억원입니다.",
        ["1,952,532억원"],
    )
    assert find_unknown_numbers(out, MESSAGE) == ["1,952"]


def test_verify_decrease_word():
    """v2: '-58.7%'를 '58.7% 감소'로 바꿔 써도 통과 (v1에선 오탐으로 실패했던 경우)"""
    out = make_summary(
        "이익 58.7% 감소",
        "법인세차감전이익은 전기 대비 58.7% 감소했습니다.",
        ["58.7%"],
    )
    assert find_unknown_numbers(out, MESSAGE) == []