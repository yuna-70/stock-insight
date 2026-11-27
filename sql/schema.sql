-- =====================================================================
-- stock-insight v1 스키마
--
-- 회사 하나 → 공시 여러 개 → 공시마다 파싱 숫자 여러 줄 · 요약 여러 개
-- 숫자는 코드가 파싱하고(disclosure_numbers), 해석은 LLM이 한다(summaries)
--
-- 실행 (저장소 맨 위에서):
--   docker exec -i stock-insight-db psql -U postgres -d stock_insight < sql\schema.sql
--
-- 순서 주의: FK가 가리키는 테이블이 먼저 있어야 해서
--   corps → disclosures → disclosure_numbers, summaries 순서로 만든다
-- =====================================================================


-- 회사 정보
-- corpCode.xml에서 가끔 한 번 받아 저장 (요청마다 매번 받지 않음)
-- 회사명은 여기 한 곳에만 저장 → 사명이 바뀌어도 한 줄만 고치면 됨 (정규화)
CREATE TABLE corps (
    corp_code VARCHAR(8) PRIMARY KEY,       -- DART 회사코드 8자리. 앞의 0 때문에 숫자 대신 글자
    stock_code VARCHAR(6),                  -- 종목코드 6자리. 비상장사는 공백이라 strip 후 저장 (없으면 NULL)
    corp_name VARCHAR(100) NOT NULL         -- 회사명
);


-- 공시 목록
-- list.json에서 주기적으로 받아 새 것만 추가
-- rcept_no가 공시마다 하나뿐이라 PK = 중복 방지 기준
CREATE TABLE disclosures (
    rcept_no VARCHAR(14) PRIMARY KEY,                           -- DART 접수번호 14자리
    corp_code VARCHAR(8) NOT NULL REFERENCES corps(corp_code),  -- 어느 회사의 공시인지 (없는 회사코드는 거절됨)
    report_nm VARCHAR(200) NOT NULL,                            -- 공시명. 뒤에 공백이 붙어 와서 strip 후 저장
    rcept_dt DATE NOT NULL,                                     -- 접수일. DATE라서 기간 검색(start~end)이 정확함
    type VARCHAR(20)                                            -- 실적 / 회사계획 / 주주환원 / 기타. API의 type 필터용
);


-- 파싱 숫자
-- 코드가 원문 표에서 꺼낸 값. 숫자 하나당 한 줄 (길게 저장)
-- 넓게(항목마다 컬럼) 저장하면 공시 종류가 늘 때마다 테이블 구조를 바꿔야 해서 길게 저장
CREATE TABLE disclosure_numbers (
    id SERIAL PRIMARY KEY,                                              -- 자동 증가 번호
    rcept_no VARCHAR(14) NOT NULL REFERENCES disclosures(rcept_no),     -- 어떤 공시의 숫자인지
    item VARCHAR(50) NOT NULL,                                          -- 항목: 매출액, 영업이익 ...
    scope VARCHAR(50),                                                  -- 당해실적 / 누계실적
    period VARCHAR(50),                                                 -- 당기 / 전기 / 전년동기
    value NUMERIC,                                                      -- 쉼표 뺀 숫자, 소수(13.85)도 담음. 원문 '-'는 NULL (0과 뜻이 다름)
    unit VARCHAR(50)                                                    -- 억원, % (단위 없으면 숫자 의미를 모름)
);


-- LLM 요약
-- 수집할 때 미리 만들어 저장 → API는 꺼내기만 해서 빠르고, LLM 호출도 공시당 한 번
-- 프롬프트를 고치면 새 줄로 다시 만들어 버전별로 비교·채점
CREATE TABLE summaries (
    id SERIAL PRIMARY KEY,                                              -- 자동 증가 번호
    rcept_no VARCHAR(14) NOT NULL REFERENCES disclosures(rcept_no),     -- 어떤 공시의 요약인지
    short_summary VARCHAR,                                              -- 목록용 한두 줄 (LLM 실패 시 비어 있을 수 있음)
    summary TEXT,                                                       -- 상세용 요약 (길이 제한 없는 긴 글)
    evidence JSONB,                                                     -- 근거 문장 목록. JSONB라 검색이 빠름
    model VARCHAR NOT NULL,                                             -- 요약한 LLM 모델 이름
    prompt_version VARCHAR NOT NULL,                                    -- 프롬프트 버전 (v1, v2 비교·채점용)
    created_at TIMESTAMP DEFAULT NOW()                                  -- 만든 시각. 저장할 때 자동으로 채워짐
);