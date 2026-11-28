"""
공시 API (주소를 담당하는 곳)

요청을 받아서 → 서비스에 일을 맡기고 → 결과를 응답으로 돌려준다.
서비스가 None을 주면 "찾는 대상이 없음"이라 404로 바꾼다.
"""

from datetime import date

from fastapi import APIRouter, HTTPException

from app.services.disclosure_service import get_disclosure, get_disclosures

router = APIRouter(tags=["disclosures"])


@router.get("/stocks/{stock_code}/disclosures")
def read_disclosures(
    stock_code: str,
    type: str | None = None,
    start: date | None = None,   # 2026-08-01 형식. 잘못 보내면 FastAPI가 자동으로 422
    end: date | None = None,
):
    """종목코드로 공시 목록을 돌려준다. type·start·end를 안 보내면 v1 종류, 최근 3개월"""
    result = get_disclosures(stock_code, type, start, end)

    if result is None:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다.")

    return result


@router.get("/disclosures/{rcept_no}")
def read_disclosure(rcept_no: str):
    """접수번호로 공시 하나의 상세를 돌려준다"""
    result = get_disclosure(rcept_no)

    if result is None:
        raise HTTPException(status_code=404, detail="공시를 찾을 수 없습니다.")

    return result