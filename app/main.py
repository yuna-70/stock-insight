"""
FastAPI 시작점

앱을 만들고, 기능별 라우터를 연결한다.
실행: uvicorn app.main:app --reload  (저장소 맨 위 폴더에서)
확인: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

from app.api.disclosures import router as disclosures_router

app = FastAPI(title="stock-insight")

# 공시 API 묶음을 앱에 연결 (이 줄이 없으면 /docs에 공시 API가 안 보임)
app.include_router(disclosures_router)


@app.get("/health")
def health():
    """서버가 살아있는지 확인하는 가장 간단한 API"""
    return {"status": "ok"}