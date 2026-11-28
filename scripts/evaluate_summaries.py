"""요약 품질 평가 스크립트.

같은 공시를 RUNS번씩 요약해 grading.py의 기준으로 채점하고,
기준별 통과율을 출력한 뒤 CSV로 저장한다.

실행: python -m scripts.evaluate_summaries
"""

import asyncio
import csv
from pathlib import Path

from app.services.disclosure_service import get_disclosure
from app.llm.summarizer import (
    LLM_MODEL,
    PROMPT_VERSION,
    build_message,
    find_unknown_numbers,
    summarize,
)
from app.llm.grading import CRITERIA, grade


# ── 설정 ───────────────────────────────────────────────
# 함정별로 고른 평가용 공시 (rcept_no는 DB 조회 결과로 채우기)
EVAL_SET = [
    {"rcept_no": "20261008800004", "trap": "억원 기본"},
    {"rcept_no": "20261029800099", "trap": "조원 정정"},
    {"rcept_no": "20261028800036", "trap": "백만원·음수 증감률"},
    {"rcept_no": "20261029800087", "trap": "억원 (같은 날 정정과 함께 나온 공시)"},
]
RUNS = 3              # 공시 하나당 요약 횟수 (처음 확인할 때는 1)
MAX_CONCURRENT = 3    # 동시에 보내는 LLM 요청 수
OUT_DIR = Path("docs/eval")

CRITERIA_NAMES = [name for name, _ in CRITERIA]   # CSV 열 이름·리포트 순서로 사용


# ── 1회 실행 ───────────────────────────────────────────
async def run_once(item: dict, run: int, sem: asyncio.Semaphore) -> dict:
    """공시 하나를 한 번 요약하고 채점한 결과(한 줄)를 dict로 돌려준다."""
    row = {"rcept_no": item["rcept_no"], "trap": item["trap"], "run": run}

    disclosure = get_disclosure(item["rcept_no"])
    if disclosure is None:
        return {**row, "error": "공시 없음"}

    message = build_message(
        disclosure["corp_name"],
        disclosure["report_nm"],
        disclosure["rcept_dt"],
        disclosure["numbers"],
    )

    async with sem:                      # 동시 요청 수 제한
        try:
            out = await summarize(message)
        except Exception as e:           # LLM 실패도 평가 결과로 기록
            return {**row, "error": f"{type(e).__name__}: {e}"}

    unknown = find_unknown_numbers(out, message)
    return {
        **row,
        "error": "",
        "verified": not unknown,          # 입력에 없는 숫자가 없으면 통과
        "unknown": ", ".join(unknown),
        **grade(out, message),            # 기준 이름: True/False 가 열로 펼쳐짐
        "short_summary": out.short_summary,
    }


# ── 전체 평가 ──────────────────────────────────────────
async def evaluate() -> list[dict]:
    """EVAL_SET의 모든 공시를 RUNS번씩 돌려 결과 목록을 만든다."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [
        run_once(item, run, sem)
        for item in EVAL_SET
        for run in range(1, RUNS + 1)
    ]
    return await asyncio.gather(*tasks)


# ── 리포트 ─────────────────────────────────────────────
def rate(ok: int, total: int) -> str:
    """'11/12 (92%)' 형태의 통과율 문자열."""
    if total == 0:
        return "0/0"
    return f"{ok}/{total} ({ok / total:.0%})"


def print_report(rows: list[dict]) -> None:
    """기준별 통과율과 실패한 줄을 화면에 출력한다."""
    done = [r for r in rows if not r["error"]]      # 채점 가능한 줄만 분모로
    failed = [r for r in rows if r["error"]]

    print(f"모델: {LLM_MODEL} | 프롬프트: {PROMPT_VERSION}")
    print(f"실행: {len(rows)}회 (성공 {len(done)}, 실패 {len(failed)})\n")

    print(f"{'숫자 검증':<20} {rate(sum(r['verified'] for r in done), len(done))}")
    for name in CRITERIA_NAMES:
        print(f"{name:<20} {rate(sum(r[name] for r in done), len(done))}")

    print("\n[떨어진 줄]")
    lines = []
    for r in done:
        misses = [n for n in ["verified", *CRITERIA_NAMES] if not r[n]]
        if misses:
            lines.append(f"- {r['trap']} #{r['run']}: {', '.join(misses)}")
    for r in failed:
        lines.append(f"- {r['trap']} #{r['run']}: 실행 실패 ({r['error']})")

    print("\n".join(lines) if lines else "없음 ✅")


def save_csv(rows: list[dict]) -> Path:
    """결과를 docs/eval/eval_{PROMPT_VERSION}.csv로 저장하고 경로를 돌려준다."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"eval_{PROMPT_VERSION}.csv"

    fields = ["rcept_no", "trap", "run", "error", "verified", "unknown",
              *CRITERIA_NAMES, "short_summary"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:   # 엑셀 한글 깨짐 방지
        writer = csv.DictWriter(f, fieldnames=fields, restval="")  # 실패 줄의 빈 칸은 ""
        writer.writeheader()
        writer.writerows(rows)
    return path


# ── 진입점 ─────────────────────────────────────────────
async def main() -> None:
    rows = await evaluate()
    print_report(rows)
    path = save_csv(rows)
    print(f"\n저장: {path}")


if __name__ == "__main__":
    asyncio.run(main())