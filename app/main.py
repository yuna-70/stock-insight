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