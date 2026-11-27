"""
공시 API (주소를 담당하는 곳)

요청을 받아서 → 서비스에 일을 맡기고 → 결과를 그대로 돌려준다.
여기서는 데이터를 직접 만들지 않는다. (그건 services가 담당)
"""

from fastapi import APIRouter

from app.services.disclosure_service import get_disclosure, get_disclosures

# 주소 묶음(라우터). app = FastAPI()는 main.py에 하나만 둔다
# tags: /docs 화면에서 이 API들을 "disclosures"로 묶어서 보여줌
router = APIRouter(tags=["disclosures"])


@router.get("/stocks/{stock_code}/disclosures")
def read_disclosures(stock_code: str, type: str | None = None, start: str | None = None, end: str | None = None, ):
    """종목코드로 공시 목록을 돌려준다. type·start·end는 안 보내면 기본값"""
    return get_disclosures(stock_code, type, start, end)


@router.get("/disclosures/{rcept_no}")
def read_disclosure(rcept_no: str):
    """접수번호로 공시 하나의 상세를 돌려준다"""
    return get_disclosure(rcept_no)