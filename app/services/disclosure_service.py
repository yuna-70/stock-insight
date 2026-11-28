"""
공시 서비스 (데이터를 만드는 곳)

API가 "이 종목 공시 줘"라고 부르면 DB에서 꺼내 응답 모양으로 돌려준다.
- FastAPI는 여기서 쓰지 않는다 (주소·상태코드는 api가 담당)
- 찾는 대상이 없으면 None을 돌려주고, 404로 바꾸는 건 api가 한다
- 무거운 일(파싱·LLM 요약)은 수집할 때 끝내두고, 여기서는 DB에서 꺼내기만 한다
"""

from datetime import date, timedelta

from psycopg.rows import dict_row

from app.db import get_connection

# ── 설정 ─────────────────────────────────────────────
# type을 안 보내면 v1에서 다루는 종류만 (지분변동 등 '기타'는 기본 화면에서 뺌)
V1_TYPES = ("실적", "회사계획", "주주환원")

# 기간을 안 보내면 최근 3개월 (실적은 분기마다 나와서 최소 1건은 보이게)
DEFAULT_DAYS = 90

# DART 공시 뷰어 주소. rcept_no만 붙이면 원문 화면으로 바로 간다
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

DISCLAIMER = "투자 권유가 아니며, 판단의 근거는 원문 공시를 확인하세요."

# ── SQL ──────────────────────────────────────────────
# 값은 전부 %s로 따로 넘긴다 (글자에 직접 붙이지 않음 → SQL 인젝션 방지)
CORP_SQL = "SELECT corp_code, corp_name FROM corps WHERE stock_code = %s;"

DETAIL_SQL = (
    "SELECT d.rcept_no, d.rcept_dt, d.report_nm, d.type, c.corp_name "
    "FROM disclosures d "
    "JOIN corps c ON d.corp_code = c.corp_code "   # 회사명은 corps에만 있어서 JOIN
    "WHERE d.rcept_no = %s;"
)

NUMBERS_SQL = (
    "SELECT item, scope, period, value, unit "
    "FROM disclosure_numbers "
    "WHERE rcept_no = %s "
    "ORDER BY id;"                                  # 저장 순서 = 원문 표 순서
)

# 여러 공시의 '최신' 요약을 한 번에 (공시마다 created_at이 가장 늦은 한 줄)
# 공시 20개를 20번 조회하지 않고 ANY로 1번에 → N+1 문제 방지
LATEST_SUMMARY_SQL = (
    "SELECT DISTINCT ON (rcept_no) "
    "rcept_no, short_summary, summary, evidence, model, prompt_version, created_at "
    "FROM summaries "
    "WHERE rcept_no = ANY(%s) "
    "ORDER BY rcept_no, created_at DESC;"
)


# ── 작은 도우미들 ─────────────────────────────────────
def get_latest_summaries(cur, rcept_nos: list[str]) -> dict[str, dict]:
    """여러 공시의 최신 요약을 {접수번호: 요약 줄}로 돌려준다. 요약 없는 공시는 빠진다.

    커서를 받는 이유: 목록·상세 함수가 이미 연 연결을 같이 써서 연결을 또 열지 않으려고
    """
    if not rcept_nos:
        return {}  # 공시가 0건이면 쿼리하지 않음

    cur.execute(LATEST_SUMMARY_SQL, (rcept_nos,))  # 리스트 통째로 %s 한 칸에 → ANY(...)
    return {row["rcept_no"]: row for row in cur.fetchall()}


def group_numbers(rows: list[dict]) -> list[dict]:
    """DB의 긴 모양(숫자 하나당 한 줄)을 원문 표 모양(항목·구분당 한 줄)으로 묶는다.

    [{item, scope, period, value, unit}, ...] 50줄
      → [{item, scope, unit, 당기, 전기, 전년동기, 전기대비_pct, 전년동기대비_pct}, ...] 10줄
    unit이 '억원'인 이유: 저장할 때(load_numbers) 이미 돈을 전부 억원으로 바꿔뒀기 때문
    """
    grouped = {}  # (item, scope) → 한 줄
    for r in rows:
        key = (r["item"], r["scope"])
        if key not in grouped:
            grouped[key] = {"item": r["item"], "scope": r["scope"], "unit": "억원"}

        # %는 돈과 단위가 달라서 키 이름에 _pct를 붙여 구분
        column = f"{r['period']}_pct" if r["unit"] == "%" else r["period"]
        grouped[key][column] = r["value"]

    return list(grouped.values())


def summary_fields(summary_row: dict | None) -> dict:
    """상세 응답에 넣을 요약 관련 칸들. 요약이 없으면 비어 있는 기본값.

    if summary_row를 칸마다 반복하지 않으려고 한 곳에 모음
    """
    if summary_row is None:
        return {"summary": None, "evidence": [], "summary_info": None}

    return {
        "summary": summary_row["summary"],
        "evidence": summary_row["evidence"],  # JSONB → psycopg가 파이썬 리스트로 바꿔줌
        # 이 요약을 언제·어떤 모델·어떤 프롬프트로 만들었는지 (추적·비교용)
        "summary_info": {
            "model": summary_row["model"],
            "prompt_version": summary_row["prompt_version"],
            "created_at": summary_row["created_at"],
        },
    }


# ── 목록 ──────────────────────────────────────────────
def get_disclosures(
    stock_code: str,
    type: str | None = None,       # 쿼리 이름이 ?type= 이라 그대로 씀 (함수 안에서 내장 type()은 안 씀)
    start: date | None = None,
    end: date | None = None,
) -> dict | None:
    """종목코드로 공시 목록을 DB에서 꺼낸다. 회사가 없으면 None."""

    # 기본값: 끝은 오늘, 시작은 끝에서 90일 전
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_DAYS)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            # 1. 회사 찾기
            cur.execute(CORP_SQL, (stock_code,))
            corp = cur.fetchone()
            if corp is None:
                return None  # 없는 종목 → 404

            # 2. 공시 목록: type을 보냈는지에 따라 조건이 달라서 조립
            #    (조건 글자는 코드가 정한 것만, 사용자 값은 전부 params로 → 안전)
            conditions = ["corp_code = %s", "rcept_dt BETWEEN %s AND %s"]
            params = [corp["corp_code"], start, end]

            if type is None:
                conditions.append("type = ANY(%s)")
                params.append(list(V1_TYPES))
            else:
                conditions.append("type = %s")
                params.append(type)

            cur.execute(
                "SELECT rcept_no, rcept_dt, report_nm, type "
                "FROM disclosures "
                "WHERE " + " AND ".join(conditions) + " "
                "ORDER BY rcept_dt DESC, rcept_no DESC;",   # 최신순 (같은 날이면 나중 접수가 위)
                params,
            )
            rows = cur.fetchall()

            # 3. 목록 공시들의 최신 요약을 한 번에
            summaries = get_latest_summaries(cur, [row["rcept_no"] for row in rows])

    # 4. 응답 모양 (목록에는 짧은 요약만, 아직 요약 안 한 공시는 None)
    disclosures = []
    for row in rows:
        summary_row = summaries.get(row["rcept_no"])
        disclosures.append({
            **row,                                                            # rcept_no, rcept_dt, report_nm, type
            "summary": summary_row["short_summary"] if summary_row else None,
            "dart_url": DART_VIEWER_URL + row["rcept_no"],
        })

    return {
        "stock_code": stock_code,
        "corp_name": corp["corp_name"],
        "disclosures": disclosures,  # 0건이어도 빈 리스트 → 200 (회사는 있으니까)
    }


# ── 상세 ──────────────────────────────────────────────
def get_disclosure(rcept_no: str) -> dict | None:
    """접수번호로 공시 하나의 상세를 DB에서 꺼낸다. 없으면 None."""

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            # 1. 공시 + 회사명
            cur.execute(DETAIL_SQL, (rcept_no,))
            row = cur.fetchone()
            if row is None:
                return None  # 없는 접수번호 → 404 (return으로 with를 나가도 연결은 닫힘)

            # 2. 파싱 숫자 (실적이 아닌 공시는 빈 리스트)
            cur.execute(NUMBERS_SQL, (rcept_no,))
            number_rows = cur.fetchall()

            # 3. 최신 요약 (목록과 같은 함수를 1개짜리 리스트로 재사용)
            summary_row = get_latest_summaries(cur, [rcept_no]).get(rcept_no)

    return {
        **row,                                   # rcept_no, rcept_dt, report_nm, type, corp_name
        "numbers": group_numbers(number_rows),   # 원문 표처럼 10줄 (돈은 억원)
        **summary_fields(summary_row),           # summary, evidence, summary_info
        "dart_url": DART_VIEWER_URL + row["rcept_no"],
        "disclaimer": DISCLAIMER,
    }