# fastapi에서 FastAPI 가져오기
from fastapi import FastAPI

# 서버(앱) 만들기. title은 "stock-insight" (/docs 화면 맨 위에 보이는 이름)
app = FastAPI(title="stock-insight")

# GET /health 주소 만들기 (데코레이터)
# 함수 이름: health
    # {"status": "ok"} 돌려주기
@app.get("/health")
def health():
    return {"status": "ok"}

# GET /disclosures/{rcept_no} 주소 만들기
# 함수 이름: read_disclosure, 매개변수: rcept_no (글자)
    # 지금은 가짜 값을 돌려준다 (나중에 DB에서 꺼내는 것으로 바꿈)
    # rcept_no는 받은 값 그대로, 나머지는 가짜:
    #   report_nm, rcept_dt, corp_name, summary, dart_url
@app.get("/disclosures/{rcept_no}")
def read_disclosure(rcept_no: str):
    return {
        "rcept_no": rcept_no, 
        "report_nm": "가짜 공시명",
        "rcept_dt": "가짜 공시일", 
        "corp_name": "가짜 회사명", 
        "summary": "가짜 요약", 
        "dart_url": "가짜 주소"
    }

# GET /stocks/{stock_code}/disclosures 주소 만들기
# 함수 이름: read_disclosures
# 매개변수: stock_code (경로, 글자)
#           type, start, end (쿼리, 글자, 안 보내면 None)
    # 가짜 값 돌려주기:
    #   stock_code: 받은 값, corp_name: 가짜
    #   disclosures: 공시 2개짜리 리스트
    #     각 공시: rcept_no, rcept_dt, report_nm, summary, dart_url
@app.get("/stocks/{stock_code}/disclosures")
def read_disclosures(stock_code: str, type: str | None = None, start: str | None = None, end: str | None = None,):
    return {
        "stock_code": stock_code,
        "corp_name": "가짜 회사명",
        "disclosures": [{"rcept_no": "가짜 공시번호",
                         "rcept_dt": "가짜 공시일",
                         "report_nm": "가짜 공시명",
                         "summary": "가짜 요약",
                         "dart_url": "가짜 주소"},
                         {"rcept_no": "가짜 공시번호",
                         "rcept_dt": "가짜 공시일",
                         "report_nm": "가짜 공시명",
                         "summary": "가짜 요약",
                         "dart_url": "가짜 주소"}],
    }




