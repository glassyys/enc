#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v08_gm.py(20260625)
#
# [소스 내용 정리]
#   본 프로그램은 DB의 [검색기준테이블]로부터 암호화 검토 칼럼을 읽어온 후,
#   지정한 [검색디렉토리] 하위의 소스 파일들(또는 --mid 옵션으로 지정한 sub-directory)을 
#   검색하여 칼럼이 정식 사용되고 있는지 상세 분석 및 결과를 추출하는 프로그램입니다.
#   
#   - 쿼리 블록 분리: 소스 파일 내 SELECT, INSERT, UPDATE 등의 DML/DDL 및 EXECUTE IMMEDIATE문 단독 검출
#   - 주석 무시: SQL 한줄 주석(--, #) 및 블록 주석(/* */) 내 칼럼 매칭은 자동 제외
#   - 오밋(Omit) 필터: 단순 칼럼 선택(col1, a.col1), alias 부여(col1 as c), 단순 1:1 대입/비교(a.col1 = b.col22) 제외
#   - 인클루드(Include) 필터: 칼럼 가공이나 함수가 적용된 식(substr, nvl, case문, max 등)만 추출
#   - 결과 다중화: 추출 결과는 MID별로 CSV 파일, 화면 덤프 텍스트 파일(print.txt), 제외된 로그(exclude.txt)를 생성하며
#                  --db 옵션 지정 시 지정한 [검색결과테이블명] 테이블에 자동 적재
#   - 암호화 검증 기능: default 분리 CSV 파일 생성 시 동일 라인 내 [컬럼명, default.decrypt/encrypt/eccyrpt, 변환된 key값] 동시 존재 여부 검사 및 OK/NOT OK 판정
#
# [실행 형식]
# # python p190872_local_chk_v08_gm.py <검색기준테이블> <검색디렉토리> <검색결과테이블명> [--mid <MID목록>] [--db] [--conf <설정파일>] [--where <old|new>] [--chk <default|encdec_no|all>]
#
# [실행 예시]
# # 1. 기본 실행 예시 (MID 전체 검색, DB 미적재):
# # python p190872_local_chk_v08_gm.py my_db.my_ref_table D:\chksrc\sources my_db.my_result_table
#
# # 2. 특정 MID(subdirectories) 검색 및 DB 적재:
# # python p190872_local_chk_v08_gm.py my_db.my_ref_table D:\chksrc\sources my_db.my_result_table --mid aaa,bbb,ccc --db --conf D:\chksrc\mysql.conf
#
# # 3. 분리 적재 및 파일 개별 생성 (--chk all):
# # python p190872_local_chk_v08_gm.py my_db.my_ref_table D:\chksrc\sources my_db.my_result_table --mid aaa --db --chk all
#
# [수정 이력]
# ─────────────────────────────────────────────────────────────
# v05_gm (2026-06-16)
#   - 최초 작성 및 LIKE 검색방식에서 정규식 완전일치 방식으로 수정
# v06_gm (2026-06-24)
#   - 실행 구조 개편 및 기타 옵션 추가 등
# v07_gm (2026-06-24)
#   - query_text 내의 원본 주석을 유지하여 CSV 및 DB에 적재하되 칼럼 매칭은 주석 제거 상태로 수행하도록 개선
#   - is_pure_column(생략/포함 조건) 로직을 사용자의 예시 요건에 맞추어 전면 보완
#   - 9차 수정: 
#     * 동일 칼럼 비교(on, where, and 뒤의 a.col1=b.col1 등) 및 단순 나열 생략 처리
#     * 파라미터에 결과테이블명 지정받도록 변경
#     * DB 적재 시 테이블이 없으면 생성하고, 이미 존재 시 mid 조건 데이터만 삭제 후 등록 처리
#   - 10차 추가요청:
#     * --chk all 조건 추가 및 all 분기 시 default (encrypt/decrypt 포함) 와 encdec_no (미포함) 결과 분리 생성/적재 기능 적용
#   - 11차 추가요청:
#     * CSV 파일 생성 시에는 query_text 컬럼 제외하고 저장하도록 스키마 분리
#   - 12차 추가요청:
#     * exclude로 제외한 매칭 데이터들도 구조적으로 수집하여 {결과테이블명}_exclude 테이블에 적재하도록 기능 보완
# v08_gm (2026-06-25)
#   - 암호화파일 정상처리 여부 검증로직 추가:
#     * "default 분리 CSV" 파일을 검색하여 동일 라인에 [column_name], [default.decrypt/encrypt/eccyrpt], [tobe_enc_key 변환코드(e1/e2/e3/e4)]가 모두 있으면 "OK", 없으면 "NOT OK"
#     * 검증된 결과를 담은 별도의 CSV 파일(p190872_{ref_tbl_only}_{mid}_default_chk.csv) 생성
# ===============================================================

import os
import re
import sys
import csv
import argparse
import codecs
from datetime import datetime

# Python 2.7 ConfigParser 호환성 처리
try:
    import configparser
except ImportError:
    import ConfigParser as configparser

# ============================================================
# 검색기준테이블 고정 칼럼 목록
# ============================================================
REF_TABLE_COLS = [
    "db_name", "tbl_name", "column_name", "type_name", "integer_idx",
    "mig_dec", "tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn"
]

# 결과 파일 최종 필드 레이아웃 (query_text 제외)
CSV_FIELDNAMES = [
    "run_id", "mid", "db_name", "tbl_name", "column_name", "type_name", "integer_idx",
    "mig_dec", "tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn",
    "source_file", "line_number", "matched_line", "vscode_open_cmd",
    "op_dtm"
]

# ============================================================
# MySQL 드라이버 동적 로드
# ============================================================
_MYSQL_DRIVER = None

def _detect_mysql_driver():
    global _MYSQL_DRIVER
    try:
        import mysql.connector
        _MYSQL_DRIVER = "connector"
    except ImportError:
        try:
            import pymysql
            _MYSQL_DRIVER = "pymysql"
        except ImportError:
            _MYSQL_DRIVER = None

_detect_mysql_driver()

def _mysql_connect(conf):
    host     = conf.get("host",     "localhost")
    port     = int(conf.get("port", 3306))
    user     = conf.get("user",     "")
    password = conf.get("password", "")
    database = conf.get("database", "")
    charset  = conf.get("charset",  "utf8mb4")

    if _MYSQL_DRIVER == "connector":
        import mysql.connector
        return mysql.connector.connect(
            host=host, port=port, user=user,
            password=password, database=database, charset=charset
        )
    elif _MYSQL_DRIVER == "pymysql":
        import pymysql
        return pymysql.connect(
            host=host, port=port, user=user,
            password=password, database=database,
            charset=charset, autocommit=False
        )
    else:
        raise ImportError(
            "MySQL 드라이버가 없습니다. pip install pymysql 또는 mysql-connector-python을 설치하세요."
        )

# ============================================================
# mysql.conf 로드
# ============================================================
def load_mysql_conf(explicit_path=None):
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), "mysql.conf")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        fallback = os.path.join(script_dir, "mysql.conf")
        if os.path.isfile(fallback):
            path = fallback
        else:
            return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path
    cp = configparser.ConfigParser()
    try:
        # Python 2/3 호환 인코딩 파일 읽기
        with codecs.open(path, "r", encoding="utf-8") as f:
            cp.readfp(f)
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)
    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."
    
    # Python 2.7 대소문자 유지 및 dict 변환 호환 처리
    conf = {}
    for option in cp.options("mysql"):
        conf[option] = cp.get("mysql", option)
        
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
    return conf, None

# ============================================================
# 스키마.테이블 분리 유틸
# ============================================================
def split_schema_table(full_table):
    parts = full_table.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", parts[0].strip()

def make_fq(schema, table):
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table

# ============================================================
# 검색기준테이블 전체 조회 (조건 필터 적용)
# ============================================================
def load_ref_rows_from_db(mysql_conf: dict, ref_table: str, where_opt: str = None) -> tuple:
    rows     = []
    conn     = None
    cursor   = None
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    fq_table = make_fq(ref_schema, ref_tbl_only)

    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        if ref_schema:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (ref_schema, ref_tbl_only)
            )
        else:
            cursor.execute("SHOW TABLES LIKE %s", (ref_tbl_only,))
        row_chk = cursor.fetchone()
        exists  = (row_chk[0] > 0) if row_chk else False
        if not exists:
            return [], ref_schema, ref_tbl_only, "테이블이 존재하지 않습니다: %s" % ref_table

        cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
        existing_cols = {row[0].lower() for row in cursor.fetchall()}

        select_parts = []
        for col in REF_TABLE_COLS:
            if col in existing_cols:
                select_parts.append("`%s`" % col)
            else:
                select_parts.append("NULL AS `%s`" % col)

        # 2차수정요청 조건 적용
        where_conds = []
        if "tobe_enc_key" in existing_cols:
            where_conds.append("(`tobe_enc_key` IS NOT NULL AND `tobe_enc_key` <> '')")
        if where_opt == "old" and "asis_enc_yn" in existing_cols:
            where_conds.append("`asis_enc_yn` = 'Y'")
        elif where_opt == "new" and "asis_enc_yn" in existing_cols:
            where_conds.append("`asis_enc_yn` = 'N'")

        where_clause = ""
        if where_conds:
            where_clause = "WHERE " + " AND ".join(where_conds)

        sql = "SELECT %s FROM %s %s ORDER BY tbl_name" % (", ".join(select_parts), fq_table, where_clause)
        cursor.execute(sql)
        db_rows = cursor.fetchall()

        for db_row in db_rows:
            row_dict = {}
            for idx, col in enumerate(REF_TABLE_COLS):
                val = db_row[idx]
                row_dict[col] = str(val).strip() if val is not None else ""
            rows.append(row_dict)

        return rows, ref_schema, ref_tbl_only, None

    except Exception as e:
        return [], ref_schema, ref_tbl_only, "DB 조회 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

# ============================================================
# 소스 파싱: 전처리 (주석 제거, 문자열 리터럴 유지, 문자열 길이 보존)
# ============================================================
def preprocess(content: str) -> str:
    # 1) # 주석 라인 및 DBMS_OUTPUT 라인, 블록 주석 라인을 공백으로 치환하여 원본 길이 및 라인 위치 유지
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            lines[i] = " " * len(line)
        elif re.match(r"(?i)^\s*DBMS_OUTPUT", line):
            lines[i] = " " * len(line)
        elif line.strip().startswith("/*") and line.strip().endswith("*/"):
            lines[i] = " " * len(line)
    content = "\n".join(lines)
    
    # 2) 문자열 리터럴은 보존하고, -- 주석 및 /* */ 주석은 동일 길이의 공백(개행은 유지)으로 대체
    pattern = re.compile(
        r"('(?:[^']|'')*')|"            # m.group(1): 싱글쿼트 문자열
        r"(\"(?:[^\"]|\"\")*\")|"        # m.group(2): 더블쿼트 문자열
        r"(--[^\n]*$)|"                 # m.group(3): -- 주석
        r"(/\*.*?\*/)",                 # m.group(4): /* */ 주석
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )
    
    def replacer(m):
        if m.group(1) or m.group(2):
            return m.group(0)  # 리터럴은 보존
        else:
            orig = m.group(0)
            res = []
            for ch in orig:
                if ch == '\n':
                    res.append('\n')
                else:
                    res.append(' ')
            return "".join(res)
            
    return pattern.sub(replacer, content)

# ============================================================
# 파싱 칼럼 키값 코드 변환 함수
# ============================================================
def convert_key_to_code(col_key):
    if not col_key:
        return ""
    k_lower = col_key.strip().lower()
    if k_lower == "key1":   return "e1"
    elif k_lower == "key2": return "e2"
    elif k_lower == "key3": return "e3"
    elif k_lower == "key4": return "e4"
    # Fallback/pattern match (예: key5 -> e5)
    m = re.match(r"^key(\d+)$", k_lower)
    if m:
        return "e" + m.group(1)
    return col_key

# ============================================================
# default 분리 CSV 파일 검증 함수
# ============================================================
def verify_default_results(results):
    """
    default 결과 리스트의 각 행마다 다음을 검증한다:
    - column_name값, 'default.decrypt'(또는 'default.encrypt'), 그리고
      tobe_enc_key 값을 e1/e2/e3/e4 등으로 컨버전한 값이 matched_line에 동시에 존재
    각 행에 'chk_result' ('OK' 또는 'NOK')를 부여하고, 통계(total, ok, nok)를 반환하며
    NOK인 경우 화면에 상세 출력한다.
    """
    ok_cnt = 0
    nok_cnt = 0
    
    for row in results:
        col_name = row.get("column_name", "").strip()
        tobe_enc_key = row.get("tobe_enc_key", "").strip()
        matched_line = row.get("matched_line", "").strip()
        
        # Key conversion
        chk_key = convert_key_to_code(tobe_enc_key)
        
        line_lower = matched_line.lower()
        col_lower = col_name.lower()
        key_lower = chk_key.lower()
        
        has_col = col_lower in line_lower if col_lower else False
        has_encrypt = "default.encrypt" in line_lower
        has_decrypt = "default.decrypt" in line_lower
        has_key = key_lower in line_lower if key_lower else False
        
        is_ok = False
        if has_col:
            # Case 1: default.encrypt가 포함된 경우 (encrypt/decrypt 동시 존재 포함): 반드시 key가 존재해야 OK
            if has_encrypt:
                if has_key:
                    is_ok = True
            # Case 2: default.decrypt만 포함되고 default.encrypt는 없는 경우: key가 존재하지 않아야 OK
            elif has_decrypt:
                if not has_key:
                    is_ok = True
        
        if is_ok:
            row["chk_result"] = "OK"
            ok_cnt += 1
        else:
            row["chk_result"] = "NOK"
            nok_cnt += 1
            # NOK 발생 시 화면 출력
            print("[NOK] mid=%s, column_name=%s, source_file=%s, line_number=%s, matched_line=%s, vscode_open_cmd=%s, chk_result=NOK" % 
                  (row.get("mid", "").strip(), 
                   col_name, 
                   row.get("source_file", "").strip(), 
                   str(row.get("line_number", "")).strip(), 
                   matched_line, 
                   row.get("vscode_open_cmd", "").strip()))
                   
    return len(results), ok_cnt, nok_cnt

# ============================================================
# 쿼리 단위 추출
# ============================================================
MAIN_QUERY_START = re.compile(
    r"\b(CREATE\s+OR\s+REPLACE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|"
    r"CREATE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|CREATE\s+TABLE|CREATE\s+VIEW|"
    r"ALTER\s+TABLE|ALTER\s+VIEW|DROP\s+TABLE|DROP\s+VIEW|TRUNCATE\s+TABLE|REPLACE\s+VIEW|"
    r"MERGE\s+INTO|MERGE|UPSERT|INSERT|UPDATE|DELETE|SELECT|WITH|EXECUTE)\b", re.IGNORECASE
)
END_IF_PATTERN = re.compile(r"^\s*END\s+IF\b", re.IGNORECASE)
ONLY_FROM_DUAL_PATTERN = re.compile(r"^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$", re.IGNORECASE | re.DOTALL)
EXCLUDE_PATTERNS = ["insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)", "sidtest.ad1901_rgb_ac190212_svc"]

def extract_queries_from_text(raw):
    result     = []
    content    = preprocess(raw)

    ei_queries = []
    ei_pattern = re.compile(r"\bEXECUTE\s+IMMEDIATE\s+'(.*?)'", re.IGNORECASE | re.DOTALL)
    for m in ei_pattern.finditer(content):
        inner_start = m.start(1)
        inner_end = m.end(1)
        inner_raw = raw[inner_start:inner_end].strip()
        inner_clean = content[inner_start:inner_end].strip()
        if inner_raw:
            start_line_no = raw[:inner_start].count('\n') + 1
            ei_queries.append({
                "query_text": inner_raw,
                "query_text_clean": inner_clean,
                "start_line_no": start_line_no
            })

    masked = re.sub(
        r"\bEXECUTE\s+IMMEDIATE\s+'.*?'",
        lambda m: " " * len(m.group(0)),
        content,
        flags=re.IGNORECASE | re.DOTALL
    )
    pos, length = 0, len(masked)

    while pos < length:
        match = MAIN_QUERY_START.search(masked, pos)
        if not match: break
        keyword = match.group(1).upper()
        start   = match.start()

        if keyword.startswith("END"):
            line_start = masked.rfind("\n", 0, start) + 1
            line_end   = masked.find("\n", start)
            if line_end == -1: line_end = length
            if END_IF_PATTERN.match(masked[line_start:line_end]):
                pos = line_end; continue

        end, depth, in_str, q_char = start, 0, False, None
        while end < length:
            ch = masked[end]
            if ch in ("'", '"'):
                if not in_str: in_str, q_char = True, ch
                elif q_char == ch: in_str = False
            elif not in_str:
                if ch == "(": depth += 1
                elif ch == ")": depth = max(depth - 1, 0)
                elif ch == ";" and depth == 0: end += 1; break
            end += 1

        query_masked = masked[start:end].strip()
        if query_masked and ";" in query_masked:
            query_raw = raw[start:end].strip()
            lower_q = query_masked.lower()
            if any(p.lower() in lower_q for p in EXCLUDE_PATTERNS) or ONLY_FROM_DUAL_PATTERN.match(query_masked):
                pos = end; continue
            if keyword.upper().startswith("ALTER") and not re.match(r"ALTER\s+(TABLE|VIEW)\b", query_masked, re.IGNORECASE):
                pos = end; continue

            start_line_no = raw[:start].count('\n') + 1

            result.append({
                "query_text": query_raw,
                "query_text_clean": query_masked,
                "start_line_no": start_line_no
            })
        pos = end

    result.extend(ei_queries)
    return result

def open_and_extract_queries(source_file_path):
    if not source_file_path or not source_file_path.strip():
        return [], "source_file 경로가 비어 있습니다.", [], ""
    path = source_file_path.strip().replace("\\", os.sep).replace("/", os.sep)
    if not os.path.isfile(path):
        return [], "파일을 찾을 수 없습니다: %s" % path, [], ""

    try:
        with codecs.open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception as e:
        return [], "파일 접근 실패: %s / %s" % (path, str(e)), [], ""

    try:
        queries = extract_queries_from_text(raw)
    except Exception as e:
        return [], "쿼리 추출 오류: %s" % str(e), [], ""

    return queries, None, raw.splitlines(), raw

# ============================================================
# 주석 및 칼럼 필터링 유틸리티
# ============================================================
def strip_comments(line):
    # 1) -- 주석 제거
    line = re.sub(r'--.*$', '', line)
    # 2) # 주석 제거
    line = re.sub(r'#.*$', '', line)
    # 3) single-line block comment /* ... */ 제거
    line = re.sub(r'/\*.*?\*/', '', line)
    return line.strip()

def is_pure_column(clean_line, col_name):
    line_lower = clean_line.lower().strip()
    col_lower = col_name.lower().strip()
    
    # 해당 칼럼명이 존재하지 않으면 매칭 분석할 필요가 없음
    if not re.search(r'\b%s\b' % re.escape(col_lower), line_lower):
        return True
        
    # --------------------------------------------------------
    # 1. 포함(Include) 조건 검사 (해당되면 False 반환)
    # --------------------------------------------------------
    
    # 1) 문자열 리터럴이 존재하는 경우 (예: 'aa', '', '#', '한글' 등)
    if "'" in line_lower:
        return False
        
    # 2) NULL이 단독 단어로 존재하는 경우
    if re.search(r'\bnull\b', line_lower):
        return False
        
    # 3) SQL 제어문 / CASE문 키워드가 존재하는 경우
    if re.search(r'\b(case|when|then|else|end|if)\b', line_lower):
        return False

    # 4) 함수 호출이 존재하는 경우: 단어 + ( 형태 (단, select, where, and, or, on, in, exists 등 제외)
    funcs = re.findall(r'\b([a-zA-Z0-9_]+)\s*\(', line_lower)
    if funcs:
        exclude_keywords = {'select', 'where', 'and', 'or', 'on', 'in', 'exists'}
        for f in funcs:
            if f not in exclude_keywords:
                return False

    # 5) 가공 연산자 존재 여부 (||, +, -, *, /, 정규식 관련 기호 등)
    if '||' in line_lower:
        return False
    if re.search(r'[\+\-\*/]', line_lower):
        return False

    # 6) as 또는 공백 기준 alias 부여에서 칼럼명이 서로 다른 경우
    # AS가 있는 경우 파싱
    as_pattern = re.compile(
        r'\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\s+as\s+(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\b',
        re.IGNORECASE
    )
    for m in as_pattern.finditer(line_lower):
        left, right = m.group(1), m.group(2)
        if left == col_lower or right == col_lower:
            if left != right:
                return False

    # AS 없이 공백으로만 alias를 준 경우 (예: c.col_1 c.col_2)
    no_as_pattern = re.compile(
        r'\b(?!select|from|where|and|or|on|as)\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\s+(?!select|from|where|and|or|on|as)\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\b',
        re.IGNORECASE
    )
    for m in no_as_pattern.finditer(line_lower):
        left, right = m.group(1), m.group(2)
        if left == col_lower or right == col_lower:
            if left != right:
                return False

    # 7) 대입/비교식 (=) 에서 칼럼명이 서로 다른 경우
    # on/where/and/or 키워드 뒤에 있는 같은 컬럼 조인식도 동일하게 필터링 적용
    if '=' in line_lower:
        parts = line_lower.split('=')
        if len(parts) == 2:
            left_val = parts[0].strip()
            right_val = parts[1].strip()
            left_m = re.search(r'(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)$', left_val)
            right_m = re.search(r'^(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)', right_val)
            if left_m and right_m:
                left_col = left_m.group(1)
                right_col = right_m.group(1)
                if (left_col == col_lower or right_col == col_lower) and (left_col != right_col):
                    return False

    # --------------------------------------------------------
    # 2. 생략(Omit) 조건 만족 여부 검사 (그 외는 생략 가능하므로 True 반환)
    # --------------------------------------------------------
    return True

# ============================================================
# 서로 다른 컬럼 비교 탐색 로직 (13차 추가요청)
# ============================================================
def check_diff_cols_match(clean_line, matched_cols):
    cols = list(matched_cols)
    if len(cols) < 2:
        return None

    # 모든 서로 다른 두 컬럼 쌍 (col1, col2) 에 대해 검사
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            col1 = cols[i]
            col2 = cols[j]
            
            # 1) AS 및 공백 alias 구문: col1 as col2 또는 col1 col2 등
            p1_1 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s+(?:as\s+)?(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col1), re.escape(col2))
            p1_2 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s+(?:as\s+)?(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col2), re.escape(col1))
            if re.search(p1_1, clean_line) or re.search(p1_2, clean_line):
                return "1) AS/Alias 문"

            # 2) = 사이에 서로 다른 컬럼 (where 이나 join의 on절 등)
            if re.search(r"\b(where|on|and|or)\b", clean_line):
                p2_1 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s*=\s*(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col1), re.escape(col2))
                p2_2 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s*=\s*(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col2), re.escape(col1))
                if re.search(p2_1, clean_line) or re.search(p2_2, clean_line):
                    return "2) = 비교문 (WHERE/ON)"

            # 3) case 문
            # 가) case when ... then col1 else col2 end
            # 나) case when ... then ... else col2 end as col3 (공백 alias 포함)
            p3_1_1 = r"\bcase\b.*?then\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\belse\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\bend\b" % (re.escape(col1), re.escape(col2))
            p3_1_2 = r"\bcase\b.*?then\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\belse\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\bend\b" % (re.escape(col2), re.escape(col1))
            
            p3_2_1 = r"\belse\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\bend\s+(?:as\s+)?(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col1), re.escape(col2))
            p3_2_2 = _DDL_CREATE_RESULT = """
CREATE TABLE IF NOT EXISTS {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `mid`              VARCHAR(100)  NOT NULL                 COMMENT '검색 MID',
  `db_name`          VARCHAR(200)  NULL,
  `tbl_name`         VARCHAR(500)  NOT NULL,
  `column_name`      VARCHAR(500)  NULL,
  `type_name`        VARCHAR(200)  NULL,
  `integer_idx`      INT           NULL,
  `mig_dec`          VARCHAR(200)  NULL,
  `tobe_enc_key`     VARCHAR(200)  NULL,
  `tobe_enc_rsn`     VARCHAR(1000) NULL,
  `asis_enc_yn`      VARCHAR(1)    NULL,
  `source_file`      VARCHAR(500)  NULL,
  `line_number`      INT           NULL,
  `matched_line`     TEXT          NULL,
  `vscode_open_cmd`  VARCHAR(1000) NULL,
  `query_text`       LONGTEXT      NULL,
  `op_dtm`           DATETIME      NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_run_id`    (`run_id`),
  KEY `idx_mid`       (`mid`),
  KEY `idx_tbl_name`  (`tbl_name`(191)),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과';
"""

_DDL_CREATE_RESULT_DEFAULT = """
CREATE TABLE IF NOT EXISTS {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `mid`              VARCHAR(100)  NOT NULL                 COMMENT '검색 MID',
  `db_name`          VARCHAR(200)  NULL,
  `tbl_name`         VARCHAR(500)  NOT NULL,
  `column_name`      VARCHAR(500)  NULL,
  `type_name`        VARCHAR(200)  NULL,
  `integer_idx`      INT           NULL,
  `mig_dec`          VARCHAR(200)  NULL,
  `tobe_enc_key`     VARCHAR(200)  NULL,
  `tobe_enc_rsn`     VARCHAR(1000) NULL,
  `asis_enc_yn`      VARCHAR(1)    NULL,
  `source_file`      VARCHAR(500)  NULL,
  `line_number`      INT           NULL,
  `matched_line`     TEXT          NULL,
  `vscode_open_cmd`  VARCHAR(1000) NULL,
  `query_text`       LONGTEXT      NULL,
  `chk_result`       VARCHAR(10)   NULL                     COMMENT '암호화 검증 결과(OK/NOK)',
  `op_dtm`           DATETIME      NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_run_id`    (`run_id`),
  KEY `idx_mid`       (`mid`),
  KEY `idx_tbl_name`  (`tbl_name`(191)),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과';
"""

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (run_id, mid, db_name, tbl_name, column_name, type_name, integer_idx,
   mig_dec, tobe_enc_key, tobe_enc_rsn, asis_enc_yn,
   source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_SQL_INSERT_RESULT_DEFAULT = """
INSERT INTO {table}
  (run_id, mid, db_name, tbl_name, column_name, type_name, integer_idx,
   mig_dec, tobe_enc_key, tobe_enc_rsn, asis_enc_yn,
   source_file, line_number, matched_line, vscode_open_cmd, query_text, chk_result, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

def db_load_table(mysql_conf, fq_table, ddl_create, sql_insert, batch, mid, table_label):
    conn, cursor = None, None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        
        # 1) 테이블 없으면 생성 (CREATE TABLE IF NOT EXISTS)
        cursor.execute(ddl_create.format(table=fq_table))
        conn.commit()
        
        # 1-2) 기존 테이블에 chk_result 컬럼이 누락된 경우 자동 추가 (테이블명에 default가 포함된 경우만 하위 호환성 유지)
        if "default" in fq_table.lower():
            cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
            columns = [row[0].lower() for row in cursor.fetchall()]
            if "chk_result" not in columns:
                try:
                    cursor.execute("ALTER TABLE %s ADD COLUMN `chk_result` VARCHAR(10) NULL COMMENT '암호화 검증 결과(OK/NOK)' AFTER `query_text`" % fq_table)
                    conn.commit()
                    print("[INFO] 테이블 %s 에 chk_result 컬럼을 자동으로 추가했습니다." % fq_table)
                except Exception as alter_err:
                    print("[WARNING] 컬럼 추가 실패 (이미 존재하거나 권한 부족): %s" % str(alter_err))
        
        # 2) 기존 존재하는 경우는 where mid = 'mid' 조건 자료 지우고 등록
        cursor.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_table, (mid,))
        conn.commit()
        
        # 3) 등록
        if batch:
            cursor.executemany(sql_insert.format(table=fq_table), batch)
            conn.commit()
        print("[INFO] DB 적재 완료 [%s]: %s (DELETE/INSERT mid=%s, %d 건)" % (table_label, fq_table, mid, len(batch)))
        return len(batch), None
    except Exception as e:
        print("[ERROR] DB 적재 실패 [%s]: %s" % (table_label, str(e)), file=sys.stderr)
        if conn:
            try: conn.rollback()
            except Exception: pass
        return 0, str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

def save_csv(rows, filepath, fieldnames, op_dtm):
    dir_path = os.path.dirname(filepath)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        
    if sys.version_info[0] < 3:
        # Python 2.7 호환 CSV 쓰기
        f = open(filepath, "wb")
        f.write(codecs.BOM_UTF8)
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            row = dict(r)
            row["op_dtm"] = op_dtm
            utf8_row = {}
            for k, v in row.items():
                if isinstance(v, unicode):
                    utf8_row[k] = v.encode('utf-8')
                else:
                    utf8_row[k] = str(v) if v is not None else ""
            writer.writerow(utf8_row)
        f.close()
    else:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                row = dict(r)
                row["op_dtm"] = op_dtm
                writer.writerow(row)

def to_int(v):
    try:
        if v is None or str(v).strip() == "" or str(v).strip().lower() == "none":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None

def build_db_batch(results, run_id, mid, op_dtm, include_chk_result=False):
    if include_chk_result:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                r.get("chk_result", ""), # chk_result 추가
                op_dtm
            )
            for r in results
        ]
    else:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                op_dtm
            )
            for r in results
        ]   if include_chk_result:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                r.get("chk_result", ""), # chk_result 추가
                op_dtm
            )
            for r in results
        ]
    else:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                op_dtm
            )
            for r in results
        ]s 에 chk_result 컬럼을 자동으로 추가했습니다." % fq_table)
                except Exception as alter_err:
                    print("[WARNING] 컬럼 추가 실패 (이미 존재하거나 권한 부족): %s" % str(alter_err))
        
        # 2) 기존 존재하는 경우는 where mid = 'mid' 조건 자료 지우고 등록
        cursor.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_table, (mid,))
        conn.commit()
        
        # 3) 등록
        if batch:
            cursor.executemany(sql_insert.format(table=fq_table), batch)
            conn.commit()
        print("[INFO] DB 적재 완료 [%s]: %s (DELETE/INSERT mid=%s, %d 건)" % (table_label, fq_table, mid, len(batch)))
        return len(batch), None
    except Exception as e:
        print("[ERROR] DB 적재 실패 [%s]: %s" % (table_label, str(e)), file=sys.stderr)
        if conn:
            try: conn.rollback()
            except Exception: pass
        return 0, str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

def save_csv(rows: list, filepath: str, fieldnames: list, op_dtm: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            row = dict(r)
            row["op_dtm"] = op_dtm
            writer.writerow(row)

def to_int(v):
    try:
        if v is None or str(v).strip() == "" or str(v).strip().lower() == "none":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None

def build_db_batch(results: list, run_id: str, mid: str, op_dtm: str, include_chk_result: bool = False) -> list:
    if include_chk_result:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                r.get("chk_result", ""), # chk_result 추가
                op_dtm
            )
            for r in results
        ]
    else:
        return [
            (
                run_id,
                mid,
                r.get("db_name"),
                r.get("tbl_name"),
                r.get("column_name"),
                r.get("type_name"),
                to_int(r.get("integer_idx")),
                r.get("mig_dec"),
                r.get("tobe_enc_key"),
                r.get("tobe_enc_rsn"),
                r.get("asis_enc_yn"),
                r.get("source_file"),
                to_int(r.get("line_number")),
                r.get("matched_line"),
                r.get("vscode_open_cmd"),
                r.get("query_text"),  # DB 적재 시 query_text 보존
                op_dtm
            )
            for r in results
        ]

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Query Analyzer Script (v08_gm)")
    parser.add_argument("ref_table", help="검색기준테이블")
    parser.add_argument("search_dir", help="검색디렉토리")
    parser.add_argument("out_table", help="검색결과테이블명")
    parser.add_argument("--mid", help="검색디렉토리 하위 MID값 (쉼표 구분)", default=None)
    parser.add_argument("--db", action="store_true", help="DB 적재 활성화")
    parser.add_argument("--conf", help="mysql.conf 파일 경로", default=None)
    parser.add_argument("--where", choices=["old", "new"], help="검색기준테이블 조회 필터", default=None)
    parser.add_argument("--chk", choices=["default", "encdec_no", "all"], help="암호화/복호화 포함 및 제외 필터", default=None)

    args = parser.parse_args()

    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    out_dir = os.path.join(script_dir, "out")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 80)
    print(" [검색기준테이블 조회 → 소스 매칭 분석 시작]")
    print("=" * 80)
    print("  검색 기준 테이블   : %s" % args.ref_table)
    print("  검색 디렉토리       : %s" % args.search_dir)
    print("  검색 결과 테이블   : %s" % args.out_table)
    print("  MID                 : %s" % (args.mid if args.mid else "(미지정, 전체 검색)"))
    print("  WHERE 필터          : %s" % (args.where if args.where else "(미지정)"))
    print("  CHK 필터            : %s" % (args.chk if args.chk else "(미지정)"))
    print("  DB 적재 여부        : %s" % ("YES (--db)" if args.db else "NO"))
    print("-" * 80)

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다.")
        sys.exit(1)

    mysql_conf, err = load_mysql_conf(args.conf)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    print("[INFO] MySQL 접속 정보")
    print("  드라이버           : %s" % _MYSQL_DRIVER)
    print("  호스트             : %s:%s" % (mysql_conf.get("host"), mysql_conf.get("port", 3306)))
    print("  데이터베이스       : %s" % mysql_conf.get("database"))
    print("-" * 80)

    print("[INFO] 검색기준테이블 조회 중: %s ..." % args.ref_table)
    ref_rows, ref_schema, ref_tbl_only, db_err = load_ref_rows_from_db(mysql_conf, args.ref_table, args.where)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[ERROR] 검색기준테이블에서 조회된 데이터가 없습니다.")
        sys.exit(1)

    print("[INFO] 조회 완료: %d 행" % len(ref_rows))
    print("-" * 80)

    # column_name 기준 중복제거
    unique_ref_rows = []
    seen_cols = set()
    for r in ref_rows:
        col_name = r.get("column_name", "").strip()
        if not col_name:
            continue
        c_lower = col_name.lower()
        if c_lower not in seen_cols:
            seen_cols.add(c_lower)
            unique_ref_rows.append(r)
    ref_rows = unique_ref_rows
    print("[INFO] 중복 제거 후 검색기준 칼럼 수: %d 개" % len(ref_rows))
    print("-" * 80)

    # Group rows by column_name (case-insensitive)
    col_to_rows = {}
    for r in ref_rows:
        col_name = r.get("column_name", "").strip()
        if not col_name:
            continue
        c_lower = col_name.lower()
        if c_lower not in col_to_rows:
            col_to_rows[c_lower] = []
        col_to_rows[c_lower].append(r)

    # Get mids to process
    mids = None
    if args.mid:
        mids = [m.strip() for m in args.mid.split(",") if m.strip()]

    # Scan directories
    source_files_by_mid = get_source_files(args.search_dir, mids)

    compiled_col_patterns = {}
    for col_lower in col_to_rows:
        compiled_col_patterns[col_lower] = re.compile(r"\b%s\b" % re.escape(col_lower), re.IGNORECASE)

    # 결과 테이블 명 분석
    out_schema, out_tbl_only = split_schema_table(args.out_table)
    fq_out_table = make_fq(out_schema, out_tbl_only)

    for mid, files in source_files_by_mid.items():
        out_suffix = mid
        if args.where:
            out_suffix += "_" + args.where
        if args.chk:
            out_suffix += "_" + args.chk

        print("-" * 80)
        print("-- 검색MID : %s (출력 접미사: %s)" % (mid, out_suffix))
        print("-" * 80)

        mid_print_buffer = []
        mid_print_buffer.append("-" * 80)
        mid_print_buffer.append("-- 검색MID : %s" % mid)
        mid_print_buffer.append("-" * 80)

        mid_exclude_buffer = []
        mid_exclude_buffer.append("-" * 80)
        mid_exclude_buffer.append("-- 제외MID : %s" % mid)
        mid_exclude_buffer.append("-" * 80)

        included_results = []
        excluded_results = []  # 12차 수정: 구조화된 제외 행 수집용
        seen_matches = set() # (filepath, l_num, col_lower) 중복 매칭 방지

        # 집계용 변수 초기화
        total_files_scanned = len(files)
        files_with_matches = set()
        match_line_count = 0
        exclude_line_count = 0
        
        # 검증 통계용 초기화
        total_val, ok_val, nok_val = 0, 0, 0

        for filepath in files:
            queries, open_err, orig_lines, raw_content = open_and_extract_queries(filepath)
            if open_err:
                continue
            
            # If no queries were parsed, fall back to analyzing the raw file lines as a single block
            if not queries and raw_content.strip():
                queries = [{"query_text": raw_content, "query_text_clean": raw_content, "start_line_no": 1}]

            for q_idx, q_item in enumerate(queries, 1):
                raw_query = q_item["query_text"]
                clean_query = q_item.get("query_text_clean", raw_query)
                clean_query_upper = clean_query.upper()
                line_no_offset = q_item["start_line_no"]
                query_lines = raw_query.splitlines()

                for col_lower, rx in compiled_col_patterns.items():
                    if rx.search(clean_query_upper):
                        # Locate exact lines in the query block
                        matched_lines_found = []
                        if line_no_offset is not None and orig_lines:
                            start_idx = line_no_offset - 1
                            end_idx = min(start_idx + len(query_lines) + 10, len(orig_lines))
                            for idx in range(start_idx, end_idx):
                                if rx.search(orig_lines[idx]):
                                    matched_lines_found.append({
                                        "line_number": idx + 1,
                                        "matched_line": orig_lines[idx]
                                    })
                        else:
                            for idx, line in enumerate(query_lines):
                                if rx.search(line):
                                    matched_lines_found.append({
                                        "line_number": idx + 1,
                                        "matched_line": line
                                    })

                        for item in matched_lines_found:
                            l_num = item["line_number"]
                            l_val = item["matched_line"]
                            
                            # 중복 검사 (동일 파일, 동일 라인, 동일 칼럼의 매칭 건 중복 적재 방지)
                            match_key = (filepath, l_num, col_lower)
                            if match_key in seen_matches:
                                continue
                            seen_matches.add(match_key)
                            
                            # Strip comments
                            clean_l_val = strip_comments(l_val)
                            
                            # Check if the column is still present in the clean line
                            if not rx.search(clean_l_val):
                                continue
                            
                            # Omit pure column references
                            orig_col_name = col_to_rows[col_lower][0]["column_name"]
                            vscode_cmd = "code -g %s:%s" % (os.path.abspath(filepath), l_num)
                            
                            # 관련 테이블명 가져오기
                            assoc_tables = sorted(list({r.get("tbl_name") for r in col_to_rows[col_lower] if r.get("tbl_name")}))
                            assoc_tables_str = ", ".join(assoc_tables)

                            if is_pure_column(clean_l_val, orig_col_name):
                                exclude_line_count += 1
                                exclude_str = "[제외] %s %s (테이블: %s)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                
                                # 구조화된 제외 데이터 수집
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query
                                    })
                                    excluded_results.append(result_row)
                                continue

                            # Apply --chk filters
                            is_included = True
                            if args.chk:
                                has_encdec = (
                                    "default.encrypt" in l_val.lower() or 
                                    "default.decrypt" in l_val.lower()
                                )
                                if args.chk == "default":
                                    is_included = has_encdec
                                elif args.chk == "encdec_no":
                                    is_included = not has_encdec
                                elif args.chk == "all":
                                    is_included = True

                            # Generate matching rows
                            if is_included:
                                files_with_matches.add(filepath)
                                match_line_count += 1
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query
                                    })
                                    included_results.append(result_row)
                                    
                                # Output formatting for stdout and print buffer
                                match_str = "[매칭] %s %s (테이블: %s)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                
                                mid_print_buffer.append(match_str)
                                mid_print_buffer.append(content_str)
                                mid_print_buffer.append("-" * 80)
                            else:
                                exclude_line_count += 1
                                # --chk 옵션에 의해 제외된 행도 제외 텍스트로 축적
                                exclude_str = "[제외] %s %s (테이블: %s, CHK필터제외)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                
                                # 구조화된 제외 데이터 수집
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query
                                    })
                                    excluded_results.append(result_row)

        # Define paths
        csv_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s.csv" % (ref_tbl_only, out_suffix)))
        print_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_print.txt" % (ref_tbl_only, out_suffix)))
        ex_txt_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_exclude.txt" % (ref_tbl_only, out_suffix)))

        # all 필터의 분할 리스트 처리
        results_default = []
        results_encdec_no = []
        if args.chk == "all":
            for r in included_results:
                line_lower = r.get("matched_line", "").lower()
                if "default.encrypt" in line_lower or "default.decrypt" in line_lower:
                    results_default.append(r)
                else:
                    results_encdec_no.append(r)
            
            # v08_gm: default 결과 리스트 검증 수행 및 chk_result 필드 주입
            total_val, ok_val, nok_val = verify_default_results(results_default)

        # Output file generation per MID if results are present
        if included_results:
            save_csv(included_results, csv_path, CSV_FIELDNAMES, op_dtm)
            print("[INFO] 파일 저장 완료: %s  (%d 건)" % (csv_path, len(included_results)))

            # all 필터인 경우 분리 CSV 파일 개별 생성
            if args.chk == "all":
                csv_path_default = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_default.csv" % (ref_tbl_only, out_suffix)))
                csv_path_encdec_no = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_encdec_no.csv" % (ref_tbl_only, out_suffix)))
                
                # default 분리 CSV는 chk_result 필드를 포함하여 저장
                save_csv(results_default, csv_path_default, CSV_FIELDNAMES + ["chk_result"], op_dtm)
                print("[INFO] [all분리] 파일 저장 완료: %s  (%d 건 - OK: %d, NOK: %d)" % (csv_path_default, len(results_default), ok_val, nok_val))
                
                save_csv(results_encdec_no, csv_path_encdec_no, CSV_FIELDNAMES, op_dtm)
                print("[INFO] [all분리] 파일 저장 완료: %s  (%d 건)" % (csv_path_encdec_no, len(results_encdec_no)))
        else:
            print("[INFO] '%s' MID에 대해 추출된 매칭 결과 행이 없습니다. (결과 파일 미생성)" % mid)

        # DB 적재 처리 (12차 수정: 결과 데이터가 없더라도 제외 데이터가 존재하면 적재 진행)
        if args.db:
            if included_results:
                # 1) 메인 테이블 적재 (전체 결과 - chk_result 미포함)
                batch_all = build_db_batch(included_results, run_id, mid, op_dtm, include_chk_result=False)
                db_load_table(mysql_conf, fq_out_table, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_all, mid, "결과데이터")

                # all 필터의 경우 파생 테이블에 분리 적재
                if args.chk == "all":
                    # default 테이블은 chk_result 포함
                    fq_out_table_default = make_fq(out_schema, out_tbl_only + "_default")
                    batch_default = build_db_batch(results_default, run_id, mid, op_dtm, include_chk_result=True)
                    db_load_table(mysql_conf, fq_out_table_default, _DDL_CREATE_RESULT_DEFAULT, _SQL_INSERT_RESULT_DEFAULT, batch_default, mid, "결과데이터_default")
                    
                    # encdec_no 테이블은 chk_result 미포함
                    fq_out_table_encdec_no = make_fq(out_schema, out_tbl_only + "_encdec_no")
                    batch_encdec_no = build_db_batch(results_encdec_no, run_id, mid, op_dtm, include_chk_result=False)
                    db_load_table(mysql_conf, fq_out_table_encdec_no, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_encdec_no, mid, "결과데이터_encdec_no")
            
            # 2) 제외 데이터 테이블 적재 (12차 수정 - chk_result 미포함)
            if excluded_results:
                fq_out_table_exclude = make_fq(out_schema, out_tbl_only + "_exclude")
                batch_exclude = build_db_batch(excluded_results, run_id, mid, op_dtm, include_chk_result=False)
                db_load_table(mysql_conf, fq_out_table_exclude, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_exclude, mid, "제외데이터")

        # Exclude file generation per MID if excluded results are present
        if len(mid_exclude_buffer) > 3:
            with open(ex_txt_path, "w", encoding="utf-8") as ef:
                ef.write("\n".join(mid_exclude_buffer) + "\n")
            print("[INFO] 제외행 내용 파일 생성 완료: %s" % ex_txt_path)

        # MID별 실행 결과 상세 요약 화면 출력 및 저장
        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append(" [분석 완료 요약 - MID: %s]" % mid)
        summary_lines.append("=" * 80)
        summary_lines.append("  - 검색 대상 기준 테이블   : %s" % args.ref_table)
        summary_lines.append("  - 검색 대상 소스 파일 수   : %d 개" % total_files_scanned)
        summary_lines.append("  - 매칭 발생 소스 파일 수   : %d 개" % len(files_with_matches))
        summary_lines.append("  - 매칭 건수 (포함)          : %d 건" % match_line_count)
        if args.chk == "all":
            summary_lines.append("     * default 암복호화 매칭 : %d 건" % len(results_default))
            summary_lines.append("     * 일반 가공 칼럼 매칭   : %d 건" % len(results_encdec_no))
        summary_lines.append("  - 매칭 건수 (제외)          : %d 건" % exclude_line_count)
        summary_lines.append("-" * 80)
        summary_lines.append("  1. 생성 파일 정보")
        if included_results:
            summary_lines.append("     - 결과 CSV 파일   : %s (%d 건)" % (csv_path, len(included_results)))
            if args.chk == "all":
                if total_val > 0:
                    summary_lines.append("     - default 분리 CSV : %s (%d 건 - OK: %d, NOK: %d)" % (csv_path_default, len(results_default), ok_val, nok_val))
                else:
                    summary_lines.append("     - default 분리 CSV : %s (%d 건)" % (csv_path_default, len(results_default)))
                summary_lines.append("     - encdec_no 분리   : %s (%d 건)" % (csv_path_encdec_no, len(results_encdec_no)))
            summary_lines.append("     - 화면 출력 파일  : %s (%d 건)" % (print_path, match_line_count))
        else:
            summary_lines.append("     - 결과 CSV 파일   : (생성 없음)")
            summary_lines.append("     - 화면 출력 파일  : (생성 없음)")
            
        if len(mid_exclude_buffer) > 3:
            summary_lines.append("     - 제외 로그 파일  : %s (%d 건)" % (ex_txt_path, exclude_line_count))
        else:
            summary_lines.append("     - 제외 로그 파일  : (생성 없음)")
            
        summary_lines.append("  2. DB 적재 정보")
        if args.db:
            if included_results:
                summary_lines.append("     - 결과 DB 테이블  : %s (%d 건)" % (fq_out_table, len(included_results)))
                if args.chk == "all":
                    fq_out_table_default = make_fq(out_schema, out_tbl_only + "_default")
                    fq_out_table_encdec_no = make_fq(out_schema, out_tbl_only + "_encdec_no")
                    summary_lines.append("     - default DB 테이블: %s (%d 건)" % (fq_out_table_default, len(results_default)))
                    summary_lines.append("     - encdec_no 테이블 : %s (%d 건)" % (fq_out_table_encdec_no, len(results_encdec_no)))
            else:
                summary_lines.append("     - 결과 DB 테이블  : (적재 없음)")
                
            if excluded_results:
                fq_out_table_exclude = make_fq(out_schema, out_tbl_only + "_exclude")
                summary_lines.append("     - 제외 DB 테이블  : %s (%d 건)" % (fq_out_table_exclude, len(excluded_results)))
            else:
                summary_lines.append("     - 제외 DB 테이블  : (적재 없음)")
        else:
            summary_lines.append("     - 결과/제외 DB 테이블 : (적재 없음)")
        summary_lines.append("=" * 80)

        # Print to screen
        for line in summary_lines:
            print(line)

        # Append to print buffer and save print log file
        mid_print_buffer.extend(summary_lines)
        if included_results:
            with open(print_path, "w", encoding="utf-8") as pf:
                pf.write("\n".join(mid_print_buffer) + "\n")
            print("[INFO] 화면출력내용 파일 생성 완료: %s" % print_path)

    print("=" * 80)
    print(" [매칭 분석 공정 완료]")
    print("=" * 80)


if __name__ == "__main__":
    main()
