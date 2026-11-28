"""
요약 자동 채점 기준

LLM 요약 하나를 기준마다 통과/실패로 채점한다. (사람 채점 없이 코드로, 매번 같은 잣대)
6-5 채점 스크립트가 프롬프트 버전별로 이 점수를 모아 비교한다.

기준 7개
  1. numbers_exist     숫자 정확성: 요약 속 숫자가 전부 입력에 있다
  2. direction_correct 방향 정확성: 입력이 음수(-58.7)인 %를 '증가'라고 쓰지 않았다 (반대도)
  3. evidence_covers   근거 일치: 본문(summary)에 쓴 숫자가 evidence에 다 있다
  4. length_ok         길이: short_summary 60자 이내, summary 3~4문장
  5. no_advice         투자 권유 없음: 매수·매도·추천·목표주가 같은 말이 없다
  6. has_key_number    핵심 포함: short_summary에 숫자가 하나 이상 있다
  7. clean_numbers     읽기 쉬운 숫자: '.00' 같은 군더더기가 없다

모든 기준 함수는 (out, message)를 받는다. 안 쓰는 쪽이 있어도 모양을 맞춰서 grade가 한 줄로 돌게.
"""

import re

from app.llm.summarizer import DisclosureSummary, extract_numbers, find_unknown_numbers

# ── 설정 ─────────────────────────────────────────────
ADVICE_WORDS = ("매수", "매도", "추천", "목표주가", "사세요", "파세요", "투자하세요")

UP_WORDS = ("증가", "늘", "상승", "개선", "성장")
DOWN_WORDS = ("감소", "줄", "하락", "악화", "축소")

# % 숫자 하나 + 그 뒤 15글자 (마침표·숫자·%를 만나면 멈춤 → 다음 숫자의 방향 단어를 끌어오지 않게)
PCT_PATTERN = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)%([^.\d%]{0,15})")


# ── 도우미 ───────────────────────────────────────────
def all_text(out: DisclosureSummary) -> str:
    """요약의 세 칸을 한 글자로 합친다 (전체를 검사하는 기준에서 씀)"""
    return " ".join([out.short_summary, out.summary, *out.evidence])


def split_pct_by_sign(message: str) -> tuple[set[str], set[str]]:
    """입력의 % 숫자를 (음수, 양수) 두 묶음으로. 부호는 떼서 저장 ('-58.7' → '58.7')"""
    negatives, positives = set(), set()
    for number, _ in PCT_PATTERN.findall(message):
        if number.startswith("-"):
            negatives.add(number.lstrip("-"))
        else:
            positives.add(number)
    return negatives, positives


# ── 기준 1: 숫자 정확성 ──────────────────────────────
def numbers_exist(out: DisclosureSummary, message: str) -> bool:
    """요약에 나온 숫자가 전부 입력에 있다 (load_summaries가 저장할 때 쓰는 검증과 같음)"""
    return find_unknown_numbers(out, message) == []


# ── 기준 2: 방향 정확성 ──────────────────────────────
def direction_correct(out: DisclosureSummary, message: str) -> bool:
    """'-58.7%'를 '58.7% 증가'로, '13.85%'를 '13.85% 감소'로 거꾸로 쓰지 않았다.

    기준 1은 부호를 떼고 비교해서 방향을 못 잡는다 → 그 빈틈을 여기서 메운다.
    숫자 뒤에 방향 단어가 없으면(판단 불가) 통과로 본다.
    """
    negatives, positives = split_pct_by_sign(message)
    text = f"{out.short_summary} {out.summary}"

    for number, tail in PCT_PATTERN.findall(text):
        size = number.lstrip("-")
        says_up = any(word in tail for word in UP_WORDS)
        says_down = any(word in tail for word in DOWN_WORDS)

        # 같은 크기가 음수·양수 둘 다 있으면 어느 쪽인지 알 수 없어서 건너뜀
        if size in negatives and size in positives:
            continue
        if size in negatives and says_up:      # 줄었는데 늘었다고 함
            return False
        if size in positives and says_down:    # 늘었는데 줄었다고 함
            return False

    return True


# ── 기준 3: 근거 일치 ────────────────────────────────
def evidence_covers(out: DisclosureSummary, message: str) -> bool:
    """본문에 쓴 숫자가 evidence에 다 들어 있다 (근거 없는 숫자를 본문에만 쓰지 않음)"""
    return extract_numbers(out.summary) <= extract_numbers(" ".join(out.evidence))  # 부분집합


# ── 기준 4: 길이 ─────────────────────────────────────
def length_ok(out: DisclosureSummary, message: str) -> bool:
    """short_summary 60자 이내, summary 3~4문장 ('다.'로 끝나는 개수로 셈 → 말투가 다르면 부정확)"""
    sentences = out.summary.count("다.")
    return len(out.short_summary) <= 60 and 3 <= sentences <= 4


# ── 기준 5: 투자 권유 없음 ────────────────────────────
def no_advice(out: DisclosureSummary, message: str) -> bool:
    text = all_text(out)
    return not any(word in text for word in ADVICE_WORDS)


# ── 기준 6: 핵심 포함 ────────────────────────────────
def has_key_number(out: DisclosureSummary, message: str) -> bool:
    """목록에서 한 줄만 보고도 규모를 알 수 있게 short_summary에 숫자가 있다"""
    return len(extract_numbers(out.short_summary)) > 0


# ── 기준 7: 읽기 쉬운 숫자 ────────────────────────────
def clean_numbers(out: DisclosureSummary, message: str) -> bool:
    """'1,952,500.00억원' 같은 군더더기가 없다 (v1 → v2에서 고친 것)"""
    return ".00" not in all_text(out)


# ── 한 번에 채점 ──────────────────────────────────────
CRITERIA = [
    ("numbers_exist", numbers_exist),
    ("direction_correct", direction_correct),
    ("evidence_covers", evidence_covers),
    ("length_ok", length_ok),
    ("no_advice", no_advice),
    ("has_key_number", has_key_number),
    ("clean_numbers", clean_numbers),
]


def grade(out: DisclosureSummary, message: str) -> dict[str, bool]:
    """요약 하나를 7개 기준으로 채점 → {"numbers_exist": True, ...}"""
    return {name: check(out, message) for name, check in CRITERIA}