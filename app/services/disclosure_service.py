"""
공시 서비스 (데이터를 만드는 곳)

API가 "이 종목 공시 줘"라고 부르면 데이터를 만들어 돌려준다.
지금은 가짜 값이고, 나중에 DB 조회 → 파싱 숫자 → LLM 요약으로 바꾼다.
FastAPI는 여기서 쓰지 않는다. (주소는 api가 담당)
"""


def get_disclosures(stock_code: str, type: str | None = None, start: str | None = None, end: str | None = None, ):
    """종목코드로 공시 목록을 만든다 (지금은 가짜 값)"""

    # TODO(나중에): stock_code로 DB에서 공시 목록 조회, type·start·end로 거르기
    return {
        "stock_code": stock_code,
        "corp_name": "가짜 회사명",
        "disclosures": [
            {
                "rcept_no": "20261029800087",
                "rcept_dt": "20261029",
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "summary": "가짜 요약 1",
                "dart_url": "가짜 주소 1",
            },
            {
                "rcept_no": "20260731800123",
                "rcept_dt": "20260731",
                "report_nm": "연결재무제표기준영업(잠정)실적(공정공시)",
                "summary": "가짜 요약 2",
                "dart_url": "가짜 주소 2",
            },
        ],
    }


def get_disclosure(rcept_no: str):
    """접수번호로 공시 하나의 상세를 만든다 (지금은 가짜 값)"""

    # TODO(나중에): rcept_no로 DB에서 공시 + 파싱 숫자 + 최신 요약 조회
    return {
        "rcept_no": rcept_no,
        "report_nm": "가짜 공시명",
        "rcept_dt": "가짜 공시일",
        "corp_name": "가짜 회사명",
        "summary": "가짜 요약",
        "dart_url": "가짜 주소",
    }