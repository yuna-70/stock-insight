"""
실적 공시 요약을 DB(summaries)에 저장하는 스크립트

공시마다: DB에서 숫자 꺼내기 → LLM 요약 → 숫자 검증 → 통과한 것만 저장
- (rcept_no, model, prompt_version)이 같으면 덮어쓰고, 프롬프트·모델이 바뀌면 새 줄로 쌓인다
- 검증에 실패한 요약은 저장하지 않는다 (틀린 숫자가 사용자에게 가는 것보다 요약이 없는 게 낫다)
- 이미 같은 모델·프롬프트로 요약한 공시는 건너뛴다 (LLM 비용 절약). 다시 만들려면 --force

두 단계로 나눈다:
  1) 모으기: LLM 요약 + 검증 (느림, DB에 쓰지 않음, 여러 공시를 동시에)
  2) 저장하기: 한 번에 UPSERT 후 commit (빠름)

실행 전: load_numbers.py로 disclosure_numbers가 채워져 있어야 함
실행:    python -m scripts.load_summaries            (아직 요약 없는 공시만)
         python -m scripts.load_summaries --force    (전부 다시)
         (저장소 맨 위에서, -m 필수: app 패키지를 import하므로)
"""

import asyncio
import os
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb  # 파이썬 리스트를 JSONB 컬럼에 그대로 넣게 감싸줌

from app.llm.summarizer import (
    LLM_MODEL,
    PROMPT_VERSION,
    build_message,
    find_unknown_numbers,
    summarize,
)
from app.services.disclosure_service import get_disclosure

# LLM을 동시에 몇 개까지 부를지 (너무 많으면 API 속도 제한에 걸림)
MAX_CONCURRENT = 3

# ── SQL ──────────────────────────────────────────────
# 실적 공시 전부
SELECT_ALL_SQL = "SELECT rcept_no FROM disclosures WHERE type = '실적' ORDER BY rcept_dt;"

# 실적 공시 중 '이 모델·이 프롬프트 버전'의 요약이 아직 없는 것만
SELECT_TODO_SQL = (
    "SELECT d.rcept_no FROM disclosures d "
    "WHERE d.type = '실적' "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM summaries s "
    "  WHERE s.rcept_no = d.rcept_no AND s.model = %s AND s.prompt_version = %s"
    ") "
    "ORDER BY d.rcept_dt;"
)

# 같은 (공시, 모델, 프롬프트 버전)이면 덮어쓰기. created_at도 다시 만든 시각으로
# (괄호로 이어 붙일 때 각 줄 끝 공백 필수: 없으면 'SETshort_summary'처럼 붙어서 문법 에러)
UPSERT_SQL = (
    "INSERT INTO summaries (rcept_no, short_summary, summary, evidence, model, prompt_version) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (rcept_no, model, prompt_version) DO UPDATE SET "
    "short_summary = EXCLUDED.short_summary, "
    "summary = EXCLUDED.summary, "
    "evidence = EXCLUDED.evidence, "
    "created_at = NOW();"
)


# ── 함수 1: 대상 고르기 ─────────────────────────────────
def get_target_rcept_nos(database_url: str, force: bool) -> list[str]:
    """요약할 실적 공시의 접수번호 목록. force면 전부, 아니면 아직 요약 없는 것만."""
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if force:
                cur.execute(SELECT_ALL_SQL)
            else:
                cur.execute(SELECT_TODO_SQL, (LLM_MODEL, PROMPT_VERSION))
            return [row[0] for row in cur.fetchall()]  # ('2026...',) → '2026...'


# ── 함수 2: 공시 하나 요약 + 검증 ─────────────────────────
async def summarize_one(rcept_no: str) -> tuple | None:
    """공시 하나를 요약하고 검증한다. 통과하면 DB에 넣을 6칸 튜플, 실패하면 None."""

    # 1. 공시 상세 (회사명·공시명·날짜·숫자 10줄이 한 딕셔너리에 → services 재사용)
    disclosure = get_disclosure(rcept_no)

    # 공시가 없거나(None) 숫자가 비었으면([]) 요약할 게 없음
    # (or는 앞이 True면 뒤를 안 봐서, None일 때 ["numbers"]까지 안 가 안전)
    if not disclosure or not disclosure["numbers"]:
        print(f"[건너뜀] {rcept_no}: 숫자가 없음")
        return None

    # 2. LLM 입력 = 검증할 때의 정답지 (날짜는 date라서 글자로)
    message = build_message(
        disclosure["corp_name"],
        disclosure["report_nm"],
        str(disclosure["rcept_dt"]),
        disclosure["numbers"],
    )

    # 3. 요약 받기. 네트워크·형식 재시도 초과 등으로 실패해도 이 공시만 건너뛰고 나머지는 계속
    try:
        out = await summarize(message)
    except Exception as e:
        print(f"[LLM 실패] {rcept_no}: {type(e).__name__}: {e}")
        return None

    # 4. 검증: 요약에 나온 숫자가 입력에 하나라도 없으면 저장하지 않음
    unknown = find_unknown_numbers(out, message)
    if unknown:
        print(f"[검증 실패] {rcept_no}: 입력에 없는 숫자 {unknown}")
        return None

    print(f"[요약] {rcept_no} {disclosure['corp_name']}: {out.short_summary}")

    # 5. UPSERT_SQL의 %s 순서 그대로 (칸이 뒤바뀌면 에러 없이 틀린 데이터가 들어가니 위아래 맞춰 쓰기)
    return (
        rcept_no,              # rcept_no
        out.short_summary,     # short_summary
        out.summary,           # summary
        Jsonb(out.evidence),   # evidence (JSONB)
        LLM_MODEL,             # model
        PROMPT_VERSION,        # prompt_version
    )


# ── 함수 3: 1단계 모으기 (동시에) ─────────────────────────
async def collect_summaries(rcept_nos: list[str]) -> list[tuple]:
    """공시마다 요약·검증해서 통과한 것만 모은다. DB에 쓰지 않는다.

    LLM 응답을 기다리는 동안 다른 공시 요청도 보내서(async의 진짜 이점) 시간을 줄인다.
    Semaphore로 동시에 MAX_CONCURRENT개까지만 부른다 (API 속도 제한 방지).
    """
    limit = asyncio.Semaphore(MAX_CONCURRENT)

    async def run(rcept_no: str) -> tuple | None:
        async with limit:  # 자리가 날 때까지 기다렸다가 들어감
            return await summarize_one(rcept_no)

    # gather: 여러 작업을 동시에 시작하고 전부 끝날 때까지 기다림 (결과 순서는 넣은 순서 그대로)
    results = await asyncio.gather(*(run(r) for r in rcept_nos))

    return [row for row in results if row is not None]  # 통과한 것만


# ── 함수 4: 2단계 저장 ──────────────────────────────────
def save_summaries(database_url: str, rows: list[tuple]) -> int:
    """모은 요약을 한 번에 저장(UPSERT)하고, summaries 전체 줄 수를 돌려준다.

    UPSERT라 다시 돌리면 새 줄 없이 덮어쓴다 → '보낸 개수'가 아니라 'DB에 실제 있는 줄 수'로 확인
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
            cur.execute("SELECT COUNT(*) FROM summaries;")
            total = cur.fetchone()[0]
        conn.commit()  # 안 하면 끝날 때 전부 취소
    return total


# ── main ────────────────────────────────────────────────
async def main():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(".env에서 DATABASE_URL을 찾을 수 없습니다.")

    force = "--force" in sys.argv  # 실행할 때 --force를 붙이면 전부 다시

    rcept_nos = get_target_rcept_nos(database_url, force)
    mode = "전부 다시" if force else "요약 없는 것만"
    print(f"[대상] 실적 공시 {len(rcept_nos)}개 ({mode}) · 모델 {LLM_MODEL} · 프롬프트 {PROMPT_VERSION}")

    if not rcept_nos:
        print("[완료] 새로 요약할 공시가 없습니다. 다시 만들려면 --force")
        return

    rows = await collect_summaries(rcept_nos)            # 1단계: 모으기 (LLM, 느림)
    if not rows:
        raise SystemExit("검증을 통과한 요약이 없습니다.")

    total = save_summaries(database_url, rows)            # 2단계: 저장 (DB, 빠름)
    print(f"[완료] 통과 {len(rows)}/{len(rcept_nos)}개 저장 → summaries 전체 {total}줄")


if __name__ == "__main__":
    asyncio.run(main())  # main()을 불러서 나온 코루틴을 실행 (main만 넘기면 안 됨)