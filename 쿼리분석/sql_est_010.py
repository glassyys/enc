## python3 sql_est_010.py /home/p190872/chksrc/SIDHUB
## python3 sql_est_010.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB
## python3 sql_est_010.py /NAS/MIDP/DBMSVC/MIDP/SID
## python3 sql_est_010.py /NAS/MIDP/DBMSVC/MIDP/TMT
## python3 sql_est_010.py /NAS/MIDP/DBMSVC/MIDP/TDIA
## python3 sql_est_010.py /NAS/MIDP/DBMSVC/MIDP/TDM
## 파이썬으로 쿼리추출 소스코드 요청
## 1.추출 대상 확장자
## .sh
## .hql
## .sql
## .uld
## .ld
## 2. 추출 대상 쿼리 유형
## CREATE
## CREATE VIEW
## CREATE TEMPORARY VIEW
## ALTER VIEW
## REPLACE VIEW
## MERGE
## UPSERT
## INSERT
## UPDATE
## DELETE
## SELECT
## CTAS (CREATE TABLE AS)
## -세미콜론(;) 기준으로 완전 문장 추출
## 
## 3. dat 생성 규칙
## 저장 위치:
## 현재실행디렉토리/out/
## 파일명:
## 프로그램명_소스마지막디렉토리_YYYYMMDD_HHMMSS.dat
## 예:
## sql_extractor_projectA_20260215_091530.dat
## 
## 4. dat 컬럼 레이아웃 및 구분자
## 구분자 "|"로path는 절대경로로 아래와 같은 레이아웃으로 생서
## file_path|file_name|path_with_file|query_text
## 
## -파일경로/파일명은 쿼리문 행개수만큼 중복 생성됨
## 
## 파일생성시 아래쿼리의 경우 
## select col_1
##       ,col_2
##  from tb_1
## where a='1'
## 아래와 같은으로 생성하도록 쿼리 보완 전체코드 요청
## file_path|file_name|path_with_file|select col_1
## file_path|file_name|path_with_file|      ,col_2
## file_path|file_name|path_with_file| from tb_1
## file_path|file_name|path_with_file|where a='1'
## 
## 쿼리 유형 컬럼 추가 (C/R/U/D 자동분류)하고 파일 건수 결과도 출력하도록 수정한 전체소스
## 
## 아래 단계로 확장요청
## WITH 절 포함 강화 정규식으로 보완하고
## 파일의 전체행건수도 추가로 출력하는 소스코드 전체 요청
## 
## 아래 단계로 확장요청
## WITH 절 포함 강화 정규식으로 보완하고
## 파일의 전체행건수도 추가로 출력하는 소스코드 전체 요청
## 
## 소스유지하고 구분자만 "^"으로 변경한 전체소스
##
## 기존소스 유지하고 세미콜론(;) 기준 완전 문장 추출할때 ; 도 쿼리문생성시 포함해서 추출한 전체소스
##
## 기존소스 유지하고 쿼리문의 ";"도 "query_text" 항목에 추가하여 파일생성하도록 수정한 전체소스
##
## 기존소스 유지하고 파일명만 아래기준으로 수정한 전체소스
## dat 생성 규칙
## 저장 위치:
## 현재실행디렉토리/out/
## 파일명:
## 프로그램명_소스마지막디렉토리_YYYYMMDD_HHMMSS.dat
## 예:
## sql_extractor_projectA_20260215_091530.dat
## 
## 파일명은 예시처럼이 아닌 
## 프로그램명_소스마지막디렉토리_YYYYMMDD_HHMMSS.dat
## 의 형태인 실행프로그램명과 쿼리소스의마지막디렉토리명으로 변경한 전체소스 다시 생성
## 
## 기존소스 유지하고 아래내용 반영한 전체소스
## WITH 다중 CTE 완전 강화 버전
## 주석 제거 후 추출
## 
## 기존소스 유지하고 아래내용 반영한 전체소스
## WITH 다중 CTE 완전 강화 버전
## 주석 제거 후 추출
## 
## 기존소스 유지하고 아래 문장이 들어간 쿼리는 대문자 포함하여 모두 제거한 수정한 전체소스
## "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)"
## "dual" 
## 
## ■요청 : 기존 소스 유지하고 아래 내용 반영한 전체소스
## 1. MAIN_QUERY_START 에 아래 명령시작 쿼리구문 추가추출
## ALTER, DROP, TRUNCATE, RENAME, DECLARE, BEGINE, EXECUTE, COMMIT, ENT
## 2./* 과 */ 사이의 주석은 제외
## 3. 첫번째 단어가 "#" 인 행 제외
## 
## 추가 
## 기존 소스 유지하고 첫단어가 "/*" 으로 시작하고 "*/"으로 끝나는 주석제외한 로직 반영한 전체소스
## DBMS_OUTPUT로 시작되는 라인 모두제외한 전체소스
## 
## 아래 원본소스 로직 유지하고 (참고 : D:\파이썬\리니지\쿼리추출_007.txt)
## 아래 쿼리 형식도 쿼리로 추출되도록 소스 보완한 전체소스
## merge /* hint */
##     into
## using
## on
## 
## update
## 
## ;
## 
## 
## merge구문 처음과 끝부분 첨부합니다. 이 쿼리가 안 잡혀요 기존로직유지후 보완수정된 전체소스
## commit 키워드로 시작되는 쿼리는 제외한 전체소스
## end if 는 제외 end 키워드는 유지하도록 수정한 전체소스
## 방금 생성한 전체소스에 "alter" 제외 "alter table" 키워드는 포함하는 전체 수정 소스
## 
## sql_est_008.py 소스에서 1,2번요청 관련 로직만 수정하고 나머지는 로직 유지하고 수정한 전체소스
## 1. MAIN_QUERY_START 에서 "ALTER" 은 제외하고 "ALTER TABLE" 형식을 추가하여 적용
## 2. 쿼리추출시 "DUAL" 이 쿼리에 있는 것은 모두제외 했는데 이 로직을 "FROM DUAL"만 있는 경우 제외하는 로직으로 변경
## FROM DUAL 단독 쿼리만 제외하는 로직으로 변경한 전체소스 단,기존 나머지로직은 유지
## RENAME 키워드 수동제외

#!/usr/bin/env python3
# 실행방법:
# python3 프로그램명.py 절대경로포함소스디렉토리

import os
import re
import sys
from datetime import datetime

# ==============================
# 1. 파라미터 체크
# ==============================

if len(sys.argv) != 2:
    print("사용법: python3 프로그램명.py 절대경로포함소스디렉토리")
    sys.exit(1)

SOURCE_DIR = os.path.abspath(sys.argv[1])

if not os.path.isdir(SOURCE_DIR):
    print("오류: 유효한 디렉토리가 아닙니다.")
    sys.exit(1)

# ==============================
# 2. 설정
# ==============================

TARGET_EXTENSIONS = ('.sh', '.hql', '.sql', '.uld', '.ld')
DELIMITER = "^"

EXCLUDE_PATTERNS = [
    "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)"
]

# 🔥 FROM DUAL 단독 쿼리만 제외
ONLY_FROM_DUAL_PATTERN = re.compile(
    r'^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$',
    re.IGNORECASE | re.DOTALL
)

# ==============================
# 3. 전처리
# ==============================

def preprocess(content):

    content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith("#")
    )

    content = "\n".join(
        line for line in content.splitlines()
        if not re.match(r'(?i)^\s*DBMS_OUTPUT', line)
    )

    content = "\n".join(
        line for line in content.splitlines()
        if not (line.strip().startswith("/*") and line.strip().endswith("*/"))
    )

    pattern = re.compile(
        r"""
        ('([^']|'')*') |
        ("([^"]|"")*") |
        (--[^\n]*$) |
        (/\*.*?\*/)
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )

    def replacer(match):
        if match.group(1) or match.group(3):
            return match.group(0)
        return ""

    return pattern.sub(replacer, content)

# ==============================
# 4. MAIN QUERY 시작 (요청 반영)
# ==============================

MAIN_QUERY_START = re.compile(
    r"""
    \b(
        CREATE\s+OR\s+REPLACE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|
        CREATE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|
        CREATE\s+TABLE|
        CREATE\s+VIEW|
        ALTER\s+TABLE|
        ALTER\s+VIEW|
        DROP\s+TABLE|
        DROP\s+VIEW|
        TRUNCATE\s+TABLE|
        REPLACE\s+VIEW|
        MERGE\s+INTO|
        MERGE|
        UPSERT|
        INSERT|
        UPDATE|
        DELETE|
        SELECT|
        WITH|
        EXECUTE
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

END_IF_PATTERN = re.compile(r'^\s*END\s+IF\b', re.IGNORECASE)

# ==============================
# 5. 쿼리 추출
# ==============================

def extract_queries_from_file(file_path):

    queries = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        content = preprocess(content)

        pos = 0
        length = len(content)

        while pos < length:

            match = MAIN_QUERY_START.search(content, pos)
            if not match:
                break

            start = match.start()
            keyword = match.group(1).upper()

            # 세미콜론까지 추출
            end = start
            in_string = False
            quote_char = None

            while end < length:
                ch = content[end]

                if ch in ("'", '"'):
                    if not in_string:
                        in_string = True
                        quote_char = ch
                    elif quote_char == ch:
                        in_string = False

                if ch == ";" and not in_string:
                    end += 1
                    break

                end += 1

            query = content[start:end].strip()

            if query:
                lower_query = query.lower()

                if any(p.lower() in lower_query for p in EXCLUDE_PATTERNS):
                    pos = end
                    continue

                # FROM DUAL 단독 SELECT 제외
                if ONLY_FROM_DUAL_PATTERN.match(query.strip()):
                    pos = end
                    continue

                queries.append(query)

            pos = end

    except Exception as e:
        print(f"[ERROR] 파일 읽기 실패: {file_path} ({e})")

    return queries

# ==============================
# 6. CRUD 분류
# ==============================

def classify_query(query):
    q = query.strip().upper()

    if q.startswith(("CREATE", "INSERT", "MERGE", "UPSERT",
                     "EXECUTE")):
        return "C"
    elif q.startswith("SELECT") or q.startswith("WITH"):
        return "R"
    elif q.startswith("UPDATE"):
        return "U"
    elif q.startswith("DELETE"):
        return "D"
    elif q.startswith(("ALTER", "REPLACE", "DROP", "TRUNCATE")):
        return "U"
    else:
        return "R"

# ==============================
# 7. 메인
# ==============================

def main():

    program_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    source_last_dir = os.path.basename(SOURCE_DIR.rstrip(os.sep))

    out_dir = os.path.join(os.getcwd(), "out")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{program_name}_{source_last_dir}_{timestamp}.dat"
    output_path = os.path.join(out_dir, output_filename)

    total_files = 0
    total_queries = 0
    total_output_rows = 0
    total_file_lines = 0

    with open(output_path, 'w', encoding='utf-8') as out_file:

        for root, _, files in os.walk(SOURCE_DIR):

            for file in files:
                if file.lower().endswith(TARGET_EXTENSIONS):

                    total_files += 1
                    full_path = os.path.join(root, file)
                    abs_path = os.path.abspath(root)

                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            total_file_lines += sum(1 for _ in f)
                    except:
                        pass

                    queries = extract_queries_from_file(full_path)

                    for query in queries:
                        total_queries += 1
                        crud_type = classify_query(query)

                        for line in query.splitlines():
                            if line.strip():
                                out_file.write(
                                    f"{crud_type}{DELIMITER}"
                                    f"{abs_path}{DELIMITER}"
                                    f"{file}{DELIMITER}"
                                    f"{full_path}{DELIMITER}"
                                    f"{line.rstrip()}\n"
                                )
                                total_output_rows += 1

    print("====================================")
    print(" SQL 추출 완료 (확장 MAIN_QUERY_START 적용 + FROM DUAL 단독 제외)")
    print("====================================")
    print(f"DAT 파일 위치        : {output_path}")
    print(f"처리 파일 건수        : {total_files}")
    print(f"추출 쿼리 건수        : {total_queries}")
    print(f"생성 행 건수          : {total_output_rows}")
    print(f"전체 파일 총 행 건수  : {total_file_lines}")
    print("====================================")

if __name__ == "__main__":
    main()