"""
실적 공시 숫자 파싱 탐색 스크립트

실적 공시 원문(document.xml) 안의 표를 읽어서
(항목, 구분, 기간, 값, 단위) 튜플로 바꾼다. → 4일차 load_numbers.py의 재료

"숫자는 코드, 해석은 LLM": 숫자는 코드가 정확하게 꺼내고, LLM은 나중에 해석만 한다.

★ 공시마다 돈 단위가 다르다 (삼성 원래: 억원 / 삼성 정정: 조원 / SK하이닉스: 백만원)
  → 표의 "단위 : ○○, %" 칸에서 단위를 읽고, 돈은 전부 억원으로 바꿔서 돌려준다

실행: python scripts/explore_numbers.py                  (기본: 삼성전자 26.3Q 실적)
      python scripts/explore_numbers.py 20261028800036    (SK하이닉스)
"""

import io
import os
import sys
import zipfile
from decimal import Decimal  # ★ 돈은 float 대신 Decimal (소수 오차 없이 정확하게)

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DEFAULT_RCEPT_NO = "20261029800087"  # 삼성전자 연결재무제표기준영업(잠정)실적 (2026-10-29)

SCOPES = ("당해실적", "누계실적")

# ★ 8칸 줄 기준: (칸 위치, 기간 이름, 종류)
#   "money" = 돈 → 억원으로 바꿈 / "pct" = 증감율 → % 그대로
COLUMNS = [
    (1, "당기", "money"),
    (2, "전기", "money"),
    (3, "전기대비", "pct"),
    (5, "전년동기", "money"),
    (6, "전년동기대비", "pct"),
]

# ★ 돈 단위 → 억원으로 바꿀 때 곱할 값 (새 단위가 나오면 여기에 추가)
TO_EOK = {
    "원": Decimal("0.00000001"),
    "천원": Decimal("0.00001"),
    "백만원": Decimal("0.01"),
    "억원": Decimal("1"),
    "조원": Decimal("10000"),
}


def to_number(text: str) -> Decimal | None:
    """표의 숫자 칸(글자)을 숫자로 바꾼다.

    '1,952,532' → Decimal('1952532') / '-58.7' → Decimal('-58.7') / '-' 또는 빈칸 → None
    정확히 '-'일 때만 None (마이너스 숫자 '-58.7'은 숫자로)
    """
    text = text.strip()
    if text in ("-", ""):
        return None
    return Decimal(text.replace(",", ""))  # ★ float → Decimal


def find_money_unit(rows: list[list[str]]) -> str:
    """★ 표에서 '단위 : 억원, %' 칸을 찾아 돈 단위('억원')만 돌려준다.

    단위를 모른 채 저장하면 만 배 차이 사고가 나서, 못 찾거나 처음 보는 단위면 멈춘다.
    """
    for row in rows:
        for cell in row:
            if "단위" in cell and ":" in cell:
                # "단위 : 백만원, %" → [' 백만원', ' %'] → '백만원'
                after_colon = cell.split(":", 1)[1]
                unit = after_colon.split(",")[0].strip()

                if unit not in TO_EOK:
                    raise ValueError(f"처음 보는 단위입니다: '{unit}' (원문: {cell})")
                return unit

    raise ValueError("표에서 '단위' 칸을 찾지 못했습니다.")


def fetch_table_rows(api_key: str, rcept_no: str) -> list[list[str]]:
    """원문을 받아서 표의 모든 행을 [['칸', '칸', ...], ...] 모양으로 돌려준다."""
    response = requests.get(
        DOCUMENT_URL,
        params={"crtfc_key": api_key, "rcept_no": rcept_no},
        timeout=10,
    )

    # 정상이면 ZIP, 키나 접수번호가 틀리면 에러 메시지(XML)가 온다
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()
            doc_bytes = zf.read(names[0])  # 공시마다 파일 이름이 달라서 첫 번째 파일
    except zipfile.BadZipFile:
        raise ValueError(f"ZIP이 아닌 응답이 왔습니다: {response.text[:200]}")

    soup = BeautifulSoup(doc_bytes, "html.parser")  # 이름은 .xml이지만 내용은 HTML

    rows = []
    for tr in soup.find_all("tr"):
        rows.append([td.get_text(strip=True) for td in tr.find_all("td")])

    if not rows:
        raise ValueError(f"{rcept_no}: 원문에서 표(tr)를 찾지 못했습니다.")

    return rows


def parse_earnings(rows: list[list[str]]) -> list[tuple]:
    """실적 표의 행들을 (항목, 구분, 기간, 값, 단위) 튜플 리스트로 바꾼다.

    - 돈은 전부 억원으로, 증감율은 % 그대로
    - rowspan: '누계실적' 줄(8칸)은 바로 위 9칸 줄의 항목 이름을 기억해서 쓴다
    - 구분 값이 SCOPES가 아닌 줄(실적기간, 연락처 등)은 건너뛴다
    """
    money_unit = find_money_unit(rows)  # ★ 표에서 단위 읽기
    multiplier = TO_EOK[money_unit]     # ★ 억원으로 바꿀 배수

    results = []
    current_item = None

    for cells in rows:
        if len(cells) == 9:
            current_item = cells[0]
            cells = cells[1:]

        if len(cells) != 8 or cells[0] not in SCOPES:
            continue

        if current_item is None:
            raise ValueError(f"항목 이름 없이 숫자 줄이 나왔습니다: {cells}")

        scope = cells[0]
        for index, period, kind in COLUMNS:
            value = to_number(cells[index])

            # ★ 돈이면 억원으로 바꾸기 (None은 그대로 None)
            if kind == "money":
                if value is not None:
                    value = value * multiplier
                unit = "억원"
            else:
                unit = "%"

            results.append((current_item, scope, period, value, unit))

    return results


def main():
    load_dotenv()
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit(".env에서 DART_API_KEY를 찾을 수 없습니다.")

    rcept_no = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RCEPT_NO

    rows = fetch_table_rows(api_key, rcept_no)
    results = parse_earnings(rows)

    items = list(dict.fromkeys(r[0] for r in results))
    print(f"[공시] {rcept_no}")
    print(f"[원문 단위] {find_money_unit(rows)} → 억원으로 변환")  # ★
    print(f"[행] {len(rows)}개")
    print(f"[숫자] {len(results)}개 (항목 {len(items)}개 × 당해/누계 × 기간 {len(COLUMNS)}개)")
    print(f"[항목] {items}")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()