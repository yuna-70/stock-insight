"""
LLM 요약 담당

공시의 숫자(코드가 파싱한 것)를 받아서 LLM이 해석한 요약을 돌려준다.
"숫자는 코드, 해석은 LLM" → LLM에게는 원문 대신 정확한 숫자만 주고,
LLM이 돌려준 숫자가 입력에 진짜 있는지 다시 코드로 검사한다.

흐름: build_message(입력 글자) → summarize(LLM 호출) → find_unknown_numbers(검증)

실행(테스트): python -m app.llm.summarizer   (저장소 맨 위에서)
"""

import asyncio
import os
import re

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent

# ── 설정 ─────────────────────────────────────────────
load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError(".env에서 LLM_MODEL을 찾을 수 없습니다.")

# 프롬프트(SYSTEM_PROMPT, 입력 모양)를 고치면 버전을 올린다
# → summaries.prompt_version에 저장해서 버전별로 요약을 비교·채점
PROMPT_VERSION = "v2"

# 글자에서 숫자 뽑기: 1,952,532 / 13.85 / -58.7 / 2026
# (마이너스 증감율도 같은 숫자로 보이도록 앞의 '-'까지 포함)
NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

# (numbers의 키, LLM에게 보여줄 이름, 단위)
FIELDS = [
    ("당기", "당기", "억원"),
    ("전기", "전기", "억원"),
    ("전기대비_pct", "전기대비", "%"),
    ("전년동기", "전년동기", "억원"),
    ("전년동기대비_pct", "전년동기대비", "%"),
]

SYSTEM_PROMPT = """
너는 한국 상장사 공시를 개인 투자자에게 쉽게 설명하는 분석가야.
규칙:
- 입력으로 받은 숫자만 사용해. 입력에 없는 숫자를 만들지 마.
- 숫자는 입력에 적힌 그대로 써. 단위를 바꾸거나 직접 계산하지 마.
- '없음'인 값은 언급하지 마.
- 매수·매도 추천이나 주가 전망은 하지 마.
- 한국어로 답해.
"""


# ── 출력 형식 ─────────────────────────────────────────
class DisclosureSummary(BaseModel):
    """LLM이 반드시 지켜야 할 요약 형식 (어기면 PydanticAI가 다시 시도)

    description = LLM에게 주는 안내문 / max_length·min_length = Pydantic이 실제로 검사하는 규칙
    """

    short_summary: str = Field(
        max_length=60,
        description="목록 화면용 60자 이내 한 문장. 가장 중요한 숫자 1~2개 포함",
    )
    summary: str = Field(
        description="상세 화면용 3~4문장. 전기·전년동기와 비교해서 무엇이 늘고 줄었는지",
    )
    evidence: list[str] = Field(
        min_length=1,  # 근거가 하나도 없는 요약은 받지 않음
        description="요약에 쓴 숫자를 입력에 적힌 그대로 옮겨 적은 목록. 입력에 없는 숫자는 쓰지 말 것",
    )


# ── 입력 만들기 ───────────────────────────────────────
def fmt(value, unit: str) -> str:
    """숫자 하나를 원문처럼 쓴다. None → '없음', 1952532 → '1,952,532억원'

    소수점 아래가 0이면 정수로 (1952500.00 → 1952500)
    → 조원·백만원을 억원으로 바꾸면서 생긴 .00 군더더기를 LLM 입력에서 없앰
    """
    # None이면 "없음" (int(None)은 에러라서 숫자 처리보다 먼저)
    if value is None:
        return "없음"

    # 소수점 아래가 0이면 정수로 (13.85, 1046154.83처럼 진짜 소수는 그대로)
    if value == int(value):
        value = int(value)

    # 쉼표 + 단위
    return f"{value:,}{unit}"


def format_numbers(numbers: list[dict]) -> str:
    """group_numbers 결과(항목·구분당 한 줄)를 LLM이 읽을 글자로 바꾼다.

    매출액 / 당해실적: 당기 1,952,532억원, 전기 1,714,995억원, 전기대비 13.85%, ...
    """
    lines = []
    for n in numbers:
        parts = [f"{label} {fmt(n.get(key), unit)}" for key, label, unit in FIELDS]
        lines.append(f"{n['item']} / {n['scope']}: " + ", ".join(parts))
    return "\n".join(lines)


def build_message(corp_name: str, report_nm: str, rcept_dt: str, numbers: list[dict]) -> str:
    """LLM에게 보낼 사용자 메시지. 검증할 때도 이 글자를 '정답지'로 쓴다."""
    return (
        f"회사: {corp_name}\n"
        f"공시: {report_nm}\n"
        f"접수일: {rcept_dt}\n"
        f"\n"
        f"[실적 숫자] (돈은 억원)\n"
        f"{format_numbers(numbers)}"
    )


# ── LLM 호출 ──────────────────────────────────────────
agent = Agent(
    model=LLM_MODEL,
    output_type=DisclosureSummary,  # 객체가 아니라 클래스(설계도)를 넘김
    system_prompt=SYSTEM_PROMPT,
)


async def summarize(message: str) -> DisclosureSummary:
    """만들어둔 메시지를 LLM에게 주고 정해진 형식의 요약을 받는다."""
    result = await agent.run(message)  # 먼저 실행(await)하고
    return result.output               # 그다음 결과를 꺼낸다 (await agent.run(...).output 은 안 됨)


# ── 검증 ──────────────────────────────────────────────
def extract_numbers(text: str) -> set[str]:
    # ★ 뽑은 숫자마다 앞의 "-"를 떼서 집합으로
    """글자 속 숫자를 전부 뽑아 집합으로. '1,952,532억원, 13.85%' → {'1,952,532', '13.85'}"""
    return {n.lstrip("-") for n in NUMBER_PATTERN.findall(text)}


def find_unknown_numbers(output: DisclosureSummary, message: str) -> list[str]:
    """요약에 나온 숫자 중 입력(message)에 없는 것을 돌려준다. 빈 리스트면 통과.

    - in(글자 일부 비교) 대신 집합으로 '정확히 같은 숫자'인지 본다
      ('1,952'는 '1,952,532' 안에 글자로는 있지만 다른 숫자 → 잡아냄)
    - evidence뿐 아니라 short_summary, summary 본문의 숫자도 검사한다
    """
    allowed = extract_numbers(message)

    used = set()
    for text in [output.short_summary, output.summary, *output.evidence]:
        used |= extract_numbers(text)  # |= : 집합 합치기

    return sorted(used - allowed)  # 집합 빼기: 요약에는 있는데 입력에는 없는 숫자


# ── 테스트: 직접 실행할 때만 ───────────────────────────
if __name__ == "__main__":
    sample = [
        {"item": "매출액", "scope": "당해실적", "unit": "억원",
         "당기": 1952532, "전기": 1714995, "전기대비_pct": 13.85,
         "전년동기": 860617, "전년동기대비_pct": 126.88},
        {"item": "매출액", "scope": "누계실적", "unit": "억원",
         "당기": 5006261, "전기": None, "전기대비_pct": None,
         "전년동기": 2397686, "전년동기대비_pct": 108.8},
    ]

    message = build_message("삼성전자", "연결재무제표기준영업(잠정)실적(공정공시)", "2026-10-29", sample)
    print("[입력]\n" + message)

    out = asyncio.run(summarize(message))
    print("\n[요약]", out.model_dump())
    print("[검증] 입력에 없는 숫자:", find_unknown_numbers(out, message))

    # 일부러 틀린 요약으로 검증이 잡아내는지 확인
    fake = DisclosureSummary(
        short_summary="매출 1,952억원",                    # 진짜 숫자의 일부만 (in이면 통과했을 것)
        summary="영업이익이 9,999,999억원으로 늘었습니다.",  # 본문에만 지어낸 숫자
        evidence=["당기 1,952,532억원"],                     # 근거는 진짜
    )
    print("[가짜 검증]", find_unknown_numbers(fake, message))