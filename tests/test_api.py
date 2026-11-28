"""
API 테스트 (DB 없이)

services 함수를 가짜로 바꿔치기해서, api 층이 하는 일만 확인한다.
- services가 데이터를 주면 200, None을 주면 404로 바꾸는지
- 쿼리 값 형식이 틀리면 FastAPI가 422를 내는지
(api / services를 나눠둔 덕분에 DB·도커 없이 테스트 가능)

실행: pytest   (저장소 맨 위에서)
"""

from fastapi.testclient import TestClient

from app.api import disclosures  # 바꿔치기할 '모듈'(api 파일)을 통째로 가져옴
from app.main import app

# 서버를 켜지 않고 요청을 보내는 도구 (requests.get과 같은 모양)
client = TestClient(app)

# ── services 대신 돌려줄 가짜 데이터 ──────────────────
FAKE_LIST = {
    "stock_code": "005930",
    "corp_name": "삼성전자",
    "disclosures": [
        {
            "rcept_no": "20261029800087",
            "rcept_dt": "2026-10-29",
            "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
            "type": "실적",
            "summary": "매출 1,952,532억원",
            "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261029800087",
        }
    ],
}

FAKE_DETAIL = {
    "rcept_no": "20261029800087",
    "rcept_dt": "2026-10-29",
    "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
    "type": "실적",
    "corp_name": "삼성전자",
    "numbers": [],
    "summary": None,
    "evidence": [],
    "summary_info": None,
    "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261029800087",
    "disclaimer": "투자 권유가 아니며, 판단의 근거는 원문 공시를 확인하세요.",
}


# ── /health ─────────────────────────────────────────
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── 목록 ────────────────────────────────────────────
def test_list_ok(monkeypatch):
    """services가 데이터를 주면 200 + 그대로 응답"""
    # api 파일이 쓰는 이름을 가짜로 (무엇을 받든 FAKE_LIST를 돌려주는 함수)
    monkeypatch.setattr(disclosures, "get_disclosures", lambda *args, **kwargs: FAKE_LIST)

    response = client.get("/stocks/005930/disclosures")

    assert response.status_code == 200
    assert response.json()["corp_name"] == "삼성전자"
    assert len(response.json()["disclosures"]) == 1


def test_list_not_found(monkeypatch):
    """services가 None을 주면(없는 종목) api가 404로 바꿈"""
    monkeypatch.setattr(disclosures, "get_disclosures", lambda *args, **kwargs: None)

    response = client.get("/stocks/999999/disclosures")

    assert response.status_code == 404
    assert response.json()["detail"] == "종목을 찾을 수 없습니다."


def test_list_bad_date():
    """날짜 형식이 틀리면 422. services까지 가기 전에 FastAPI가 막아서 바꿔치기 불필요"""
    response = client.get("/stocks/005930/disclosures", params={"start": "20260801"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "start"]  # 어디가 틀렸는지까지


# ── 상세 ────────────────────────────────────────────
def test_detail_ok(monkeypatch):
    monkeypatch.setattr(disclosures, "get_disclosure", lambda *args, **kwargs: FAKE_DETAIL)

    response = client.get("/disclosures/20261029800087")

    assert response.status_code == 200
    assert response.json()["rcept_no"] == "20261029800087"


def test_detail_not_found(monkeypatch):
    monkeypatch.setattr(disclosures, "get_disclosure", lambda *args, **kwargs: None)

    response = client.get("/disclosures/00000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "공시를 찾을 수 없습니다."