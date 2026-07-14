#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v09_gm.py (2026-07-14 수정)
#
# [수정 사항 요약]
#   - 2026-07-14 추가 수정:
#     * 처리일시(op_dtm)를 검색기준테이블에 등록된 해당 컬럼의 최종작업일시(물리컬럼: 최종작업일시/last_work_dtm/upd_dtm 등) 기준으로 반영되도록 수정.
#     * 기준테이블에 최종작업일시 컬럼이 존재하지 않거나 값이 없을 경우 fallback으로 프로그램의 실행 시각(datetime.now())을 사용하도록 구현.
#   - Python 2.7.5 호환성 전면 적용: 
#     * 모든 타입 힌팅 제거
#     * codecs.open() 사용으로 인코딩 오류 방지
#     * os.makedirs(exist_ok=True) -> os.path.exists() 사전 검사 분기 적용
#     * ConfigParser 임포트 호환성 추가
#   - 17차 추가요청 반영:
#     * default.encrypt/decrypt 함수 첫 번째 인자가 식별자(컬럼)가 아닌 리터럴 상수인 경우(예: '', '1', '산', '#', NULL 등) 'dummy'로 선치환하여 비교 대상에서 완전히 배제
#     * 수정 전 백업 보관 정책 준수 (bak17)
#   - 16차 추가요청 반영:
#     * col is null 및 col is not null 단독 구문 비교 추출 제외 처리
#     * CASE WHEN 조건절 내 컬럼을 비교 탐색 대상에서 배제 처리 (when ... then 부분을 then으로 치환하는 전처리 도입)
#     * 수정 전 백업 보관 정책 준수 (bak16)
#   - 15차 추가요청 반영:
#     * 비교 CSV 파일 추출 시 default.encrypt/decrypt 함수 껍데기 벗기기(정규화) 선처리 도입
#     * 정규화된 컬럼명을 기반으로 기존 13차 비교 패턴(AS, =, CASE, 기타연산자 등)을 실행하여 암복호화 구문이 씌워진 컬럼들도 누락 없이 완벽 매칭
#     * default.decrypt(col1) = column_name_not_col 과 같이 기준테이블에 없는 컬럼과의 비교이더라도 컬럼끼리의 비교인 경우 예외 추출 기능 구현
#     * 수정 전 백업 보관 정책 준수 (bak15)
#   - 14차 추가요청 반영:
#     * 비교 CSV 파일 생성 시 검색 대상 범위를 "default 분리 CSV" 포함 결과 CSV 파일에 포함된 전체 대상으로 조정
#     * default.encrypt, default.decrypt 단어가 들어간 라인은 제외하지 않고 결과 및 비교 대상에 포함하도록 수정
#     * 향후 수정 시 원본 파일 백업 정책 적용
#   - 13차 추가요청 반영:
#     * 동일 라인 내에서 서로 다른 2개 이상의 검색 대상 컬럼(column_name)이 
#       AS(공백 alias 포함), =, CASE, 기타 비교 구문으로 연결된 경우 탐색 로직 구현
#     * 탐색된 건들은 p190872_{ref_tbl_only}_{mid}_diff_cols.csv 파일로 생성 및 {out_table}_diff_cols 테이블에 적재
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
import traceback
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

# 비교 결과 파일 최종 필드 레이아웃 (query_text 제외)
DIFF_CSV_FIELDNAMES = [
    "run_id", "mid", "db_name", "tbl_name", "column_name", "type_name", "integer_idx",
    "mig_dec", "tobe_enc_key", "compare_col1", "compare_col2", "tobe_enc_rsn", "asis_enc_yn",
    "source_file", "line_number", "matched_line", "vscode_open_cmd",
    "op_dtm"
]

# 18차 수정요청: 비교 대상 칼럼명에서 배제할 SQL 예약어 정의
SQL_KEYWORDS = {
    "select", "from", "where", "and", "or", "not", "in", "like", "between", "is", "null",
    "case", "when", "then", "else", "end", "as", "join", "on", "group", "by", "having",
    "order", "union", "all", "exists", "into", "values", "update", "set", "delete",
    "insert", "limit", "offset", "with", "over", "partition", "rows", "range", "preceding",
    "following", "unbounded", "current", "row", "nvl", "decode", "coalesce", "to_char",
    "to_date", "to_number", "substr", "instr", "length", "lpad", "rpad", "trim", "ltrim",
    "rtrim", "replace", "concat", "upper", "lower", "initcap", "dummy", "true", "false",
    "left", "right", "inner", "outer", "full", "cross", "natural", "using", "distinct",
    "avg", "count", "max", "min", "sum", "into", "temp", "temporary", "table", "view",
    "index", "create", "alter", "drop", "truncate", "rename", "add", "column", "key",
    "primary", "foreign", "references", "check", "default", "unique", "constraint",
    "index", "procedure", "function", "trigger", "database", "schema", "user", "grant",
    "revoke", "commit", "rollback", "savepoint", "transaction", "declare", "begin",
    "exception", "loop", "while", "for", "if", "then", "elsif", "else", "end", "exit",
    "return", "goto", "open", "fetch", "close", "cursor", "into", "bulk", "collect",
    "forall", "execute", "immediate", "using", "out", "inout", "returning"
}

SQL_TYPE_TOKENS = {
    "numeric", "numaric", "integer", "int", "smallint", "bigint", "decimal", "number", "string",
    "double", "float", "real", "varchar", "varchar2", "char", "character", "date",
    "timestamp", "datetime", "time", "boolean", "bool", "blob", "clob", "text", "json",
    "binary", "varbinary", "bytea", "tinyint", "mediumint", "long", "short"
}

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
        with codecs.open(path, "r", encoding="utf-8") as f:
            if hasattr(cp, "read_file"):
                cp.read_file(f)
            else:
                cp.readfp(f)
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)
    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."
    
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
def load_ref_rows_from_db(mysql_conf, ref_table, where_opt=None):
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

        # 최종작업일시 컬럼에 해당하는 컬럼 확인 (대소문자 및 영문 명칭 대조)
        work_dtm_col = None
        for candidate in ["최종작업일시", "last_work_dtm", "upd_dtm", "update_dtm", "modify_dtm", "upd_date"]:
            if candidate.lower() in existing_cols:
                work_dtm_col = candidate
                break

        select_parts = []
        for col in REF_TABLE_COLS:
            if col in existing_cols:
                select_parts.append("`%s`" % col)
            else:
                select_parts.append("NULL AS `%s`" % col)

        # 최종작업일시 컬럼 추가 바인딩 (SELECT 목록의 가장 마지막)
        if work_dtm_col:
            select_parts.append("`%s` AS `최종작업일시`" % work_dtm_col)
        else:
            select_parts.append("NULL AS `최종작업일시`")

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
            
            # 최종작업일시를 row_dict에 삽입
            val_dtm = db_row[len(REF_TABLE_COLS)]
            row_dict["최종작업일시"] = str(val_dtm).strip() if val_dtm is not None else ""
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
def preprocess(content):
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            lines[i] = " " * len(line)
        elif re.match(r"(?i)^\s*DBMS_OUTPUT", line):
            lines[i] = " " * len(line)
        elif line.strip().startswith("/*") and line.strip().endswith("*/"):
            lines[i] = " " * len(line)
    content = "\n".join(lines)
    
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
    m = re.match(r"^key(\d+)$", k_lower)
    if m:
        return "e" + m.group(1)
    return col_key

# ============================================================
# default 분리 CSV 파일 검증 함수
# ============================================================
def verify_default_results(results):
    ok_cnt = 0
    nok_cnt = 0
    
    for row in results:
        col_name = row.get("column_name", "").strip()
        tobe_enc_key = row.get("tobe_enc_key", "").strip()
        matched_line = row.get("matched_line", "").strip()
        
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
            if has_encrypt:
                if has_key:
                    is_ok = True
            elif has_decrypt:
                if not has_key:
                    is_ok = True
        
        if is_ok:
            row["chk_result"] = "OK"
            ok_cnt += 1
        else:
            row["chk_result"] = "NOK"
            nok_cnt += 1
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
    line = re.sub(r'--.*$', '', line)
    line = re.sub(r'#.*$', '', line)
    line = re.sub(r'/\*.*?\*/', '', line)
    return line.strip()

def is_pure_column(clean_line, col_name):
    line_lower = clean_line.lower().strip()
    col_lower = col_name.lower().strip()
    
    if not re.search(r'\b%s\b' % re.escape(col_lower), line_lower):
        return True
        
    if "'" in line_lower:
        return False
        
    if re.search(r'\bnull\b', line_lower):
        return False
        
    if re.search(r'\b(case|when|then|else|end|if)\b', line_lower):
        return False

    funcs = re.findall(r'\b([a-zA-Z0-9_]+)\s*\(', line_lower)
    if funcs:
        exclude_keywords = {'select', 'where', 'and', 'or', 'on', 'in', 'exists'}
        for f in funcs:
            if f not in exclude_keywords:
                return False

    if '||' in line_lower:
        return False
    if re.search(r'[\+\-\*/]', line_lower):
        return False

    as_pattern = re.compile(
        r'\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\s+as\s+(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\b',
        re.IGNORECASE
    )
    for m in as_pattern.finditer(line_lower):
        left, right = m.group(1), m.group(2)
        if left == col_lower or right == col_lower:
            if left != right:
                return False

    no_as_pattern = re.compile(
        r'\b(?!select|from|where|and|or|on|as)\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\s+(?!select|from|where|and|or|on|as)\b(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\b',
        re.IGNORECASE
    )
    for m in no_as_pattern.finditer(line_lower):
        left, right = m.group(1), m.group(2)
        if left == col_lower or right == col_lower:
            if left != right:
                return False

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

    return True

# ============================================================
# 서로 다른 컬럼 비교 탐색 로직 (13차/19차 추가요청 반영)
# ============================================================
def strip_cast_expressions(expr):
    if not expr:
        return expr

    result = []
    pos = 0
    while pos < len(expr):
        m = re.search(r"(?i)\bcast\s*\(", expr[pos:])
        if not m:
            result.append(expr[pos:])
            break

        start = pos + m.start()
        result.append(expr[pos:start])
        open_idx = start + len(m.group(0)) - 1
        depth = 1
        idx = open_idx + 1
        while idx < len(expr) and depth > 0:
            if expr[idx] == '(':
                depth += 1
            elif expr[idx] == ')':
                depth -= 1
            idx += 1

        if depth != 0:
            result.append(expr[open_idx + 1:])
            break

        inner = expr[open_idx + 1:idx - 1]
        first_arg = inner.strip()
        m_as = re.search(r"(?i)^\s*(.+?)\s+as\b", inner)
        if m_as:
            first_arg = m_as.group(1).strip()
        result.append(first_arg)
        pos = idx

    return "".join(result)


def normalize_diff_expression(expr):
    if not expr:
        return expr

    normalized = strip_cast_expressions(expr)
    normalized = re.sub(r"(?i)\s*::\s*[a-zA-Z0-9_]+", "", normalized)

    normalized = re.sub(
        r"(?i)default\.decrypt\s*\(\s*([a-zA-Z0-9_.]+)\s*\)",
        r"\1",
        normalized
    )
    normalized = re.sub(
        r"(?i)default\.encrypt\s*\(\s*([a-zA-Z0-9_.]+)\s*,\s*[^)]*?\)",
        r"\1",
        normalized
    )
    normalized = re.sub(
        r"(?i)default\.decrypt\s*\(\s*(?:'[^']*'|\"[^\"]*\"|[0-9]+|\bnull\b|[^a-zA-Z0-9_.\s]+)\s*\)",
        "'dummy'",
        normalized
    )
    normalized = re.sub(
        r"(?i)default\.encrypt\s*\(\s*(?:'[^']*'|\"[^\"]*\"|[0-9]+|\bnull\b|[^a-zA-Z0-9_.\s]+)\s*,\s*[^)]*?\)",
        "'dummy'",
        normalized
    )

    return normalized.strip()


def is_default_encdec_token(token):
    if not token:
        return False
    token = token.strip().lower()
    return token.startswith("default.encrypt") or token.startswith("default.decrypt") or token in {"encrypt", "decrypt"}


def is_real_compare_column_token(token):
    if not token:
        return False

    normalized = token.strip()
    if not normalized:
        return False

    normalized = normalized.strip("'\"")
    if not normalized:
        return False

    if normalized.lower() in {"dummy", "null", "true", "false"}:
        return False

    if is_default_encdec_token(normalized):
        return False

    if normalized in SQL_TYPE_TOKENS or normalized in SQL_KEYWORDS:
        return False

    if re.fullmatch(r"[0-9]+", normalized):
        return False

    if re.fullmatch(r"[\W_]+", normalized):
        return False

    if re.search(r"[\u3131-\u318E\uAC00-\uD7A3]", normalized):
        return False

    if re.search(r"[^a-zA-Z0-9_]", normalized):
        return False

    return True


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
            p3_2_2 = r"\belse\b.*?\b(?:[a-zA-Z0-9_]+\.)?%s\b.*?\bend\s+(?:as\s+)?(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col2), re.escape(col1))
            
            if re.search(p3_1_1, clean_line) or re.search(p3_1_2, clean_line) or re.search(p3_2_1, clean_line) or re.search(p3_2_2, clean_line):
                return "3) CASE 문 비교"

            # 4) 서로 다른 칼럼 비교하는 구문 (비교연산자)
            operators = [r"!=", r"<>", r">=", r"<=", r">", r"<", r"\blike\b", r"\bin\b"]
            for op in operators:
                p4_1 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s*%s\s*(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col1), op, re.escape(col2))
                p4_2 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s*%s\s*(?:[a-zA-Z0-9_]+\.)?%s\b" % (re.escape(col2), op, re.escape(col1))
                if re.search(p4_1, clean_line) or re.search(p4_2, clean_line):
                    return "4) 기타 비교 구문 (%s)" % op.replace(r"\b", "")
                    
    return None

def remove_if_condition(s):
    # s 내의 모든 if(cond, val1, val2) 에서 cond를 제거하고 빈 칸으로 치환
    pos = 0
    while True:
        pos = s.lower().find("if(", pos)
        if pos == -1:
            break
        start_idx = pos + 3
        depth = 1
        first_comma_idx = -1
        idx = start_idx
        while idx < len(s) and depth > 0:
            ch = s[idx]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 1:
                if first_comma_idx == -1:
                    first_comma_idx = idx
            idx += 1
        
        if first_comma_idx != -1:
            s = s[:start_idx] + " " + s[first_comma_idx:]
            pos = start_idx + 1
        else:
            pos += 3
    return s


def normalize_compare_token(token):
    if not token:
        return None

    token = token.strip().lower()
    token = re.sub(r"(?i)\s*::\s*[a-zA-Z0-9_]+", "", token)
    if "." in token:
        token = token.split(".")[-1]
    token = re.sub(r"[^a-zA-Z0-9_]+", "", token)

    if not token:
        return None

    if token in SQL_KEYWORDS or token in SQL_TYPE_TOKENS:
        return None

    if re.search(r"^(?:decimal|int|string|numeric|numaric|varchar|char|date|timestamp|datetime|time|boolean|bool|blob|clob|text|json|binary|varbinary|bytea|tinyint|smallint|mediumint|bigint|float|double|real|long|short)$", token):
        return None

    if re.fullmatch(r"[0-9]+", token):
        return None

    if re.fullmatch(r"[\W_]+", token):
        return None

    if re.search(r"[\u3131-\u318E\uAC00-\uD7A3]", token):
        return None

    return token


def find_matched_columns_in_expression(expr, matched_cols, exclude_cols=None):
    if not expr or not matched_cols:
        return []

    exclude_set = set(exclude_cols or [])
    candidates = []
    for token in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)?\b", expr):
        normalized = normalize_compare_token(token)
        if not normalized:
            continue
        if normalized in exclude_set:
            continue
        if normalized not in matched_cols:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates


def extract_ordered_pair_from_equal_expression(norm_l_val_lower):
    # 비교식은 좌변/우변 순서를 그대로 유지해야 함
    norm_l_val_lower = re.sub(r"(?i)\s*::\s*[a-zA-Z0-9_]+", "", norm_l_val_lower)

    m = re.search(r"\b([a-zA-Z0-9_.]+)\b\s*(?:=|!=|<>|>=|<=|>|<|\blike\b|\bin\b)\s*(?!['\"0-9]|null\b)\b([a-zA-Z0-9_.]+)\b", norm_l_val_lower)
    if m:
        left_col = normalize_compare_token(m.group(1))
        right_col = normalize_compare_token(m.group(2))
        if left_col and right_col and left_col != right_col:
            return left_col, right_col

    m_alias = re.search(r"\b([a-zA-Z0-9_.]+)\b\s+(?:as\s+)?\b([a-zA-Z0-9_.]+)\b", norm_l_val_lower)
    if m_alias:
        left_col = normalize_compare_token(m_alias.group(1))
        right_col = normalize_compare_token(m_alias.group(2))
        if left_col and right_col and left_col != right_col:
            return left_col, right_col

    return None

# ============================================================
# 소스 디렉토리 탐색 및 바이너리 제외
# ============================================================
def is_binary_file(filepath):
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                return True
    except Exception:
        return True
    return False

def get_source_files(search_dir, mids=None):
    result = {}
    search_dir = os.path.abspath(search_dir)
    allowed_exts = {".uld", ".ld", ".sh", ".sql", ".hql"}
    
    if not mids:
        default_mid = os.path.basename(os.path.normpath(search_dir))
        files = []
        if os.path.isdir(search_dir):
            for root, _, filenames in os.walk(search_dir):
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in allowed_exts:
                        continue
                    filepath = os.path.join(root, f)
                    if not is_binary_file(filepath):
                        files.append(filepath)
        result[default_mid] = files
    else:
        for mid in mids:
            mid = mid.strip()
            if not mid:
                continue
            mid_dir = os.path.join(search_dir, mid)
            files = []
            if os.path.isdir(mid_dir):
                for root, _, filenames in os.walk(mid_dir):
                    for f in filenames:
                        ext = os.path.splitext(f)[1].lower()
                        if ext not in allowed_exts:
                            continue
                        filepath = os.path.join(root, f)
                        if not is_binary_file(filepath):
                            files.append(filepath)
            else:
                print("[WARN] 디렉토리가 존재하지 않습니다: %s" % mid_dir)
            result[mid] = files
    return result

# ============================================================
# DB 테이블 DDL 및 적재 모듈 (9차, 10차, 11차 및 12차 수정)
# ============================================================
_DDL_CREATE_RESULT = """
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
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_DDL_CREATE_DIFF_COLS = """
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
  `compare_col1`     VARCHAR(500)  NULL                     COMMENT '비교첫번째칼럼추출(컬럼명:변환키)',
  `compare_col2`     VARCHAR(500)  NULL                     COMMENT '비교두번째칼럼추출(컬럼명:변환키)',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과(비교컬럼)';
"""

_SQL_INSERT_DIFF_COLS = """
INSERT INTO {table}
  (run_id, mid, db_name, tbl_name, column_name, type_name, integer_idx,
   mig_dec, tobe_enc_key, compare_col1, compare_col2, tobe_enc_rsn, asis_enc_yn,
   source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

def db_load_table(mysql_conf, fq_table, ddl_create, sql_insert, batch, mid, table_label):
    conn, cursor = None, None
    batch_size = len(batch) if batch is not None else 0
    print("[DB_LOAD] [%s] 시작: table=%s, mid=%s, rows=%d" % (table_label, fq_table, mid, batch_size))
    try:
        print("[DB_LOAD] [%s] MySQL 연결 시도: %s" % (table_label, fq_table))
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        print("[DB_LOAD] [%s] MySQL 연결 성공" % table_label)
        
        print("[DB_LOAD] [%s] DDL 실행 시작: %s" % (table_label, fq_table))
        cursor.execute(ddl_create.format(table=fq_table))
        conn.commit()
        print("[DB_LOAD] [%s] DDL 실행 완료" % table_label)
        

        if "diff_cols" in fq_table.lower():
            print("[DB_LOAD] [%s] diff_cols 테이블 컬럼 확인 시작" % table_label)
            cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
            columns = [row[0].lower() for row in cursor.fetchall()]
            if "compare_col1" not in columns:
                try:
                    print("[DB_LOAD] [%s] compare_col1 컬럼 추가 시도" % table_label)
                    cursor.execute("ALTER TABLE %s ADD COLUMN `compare_col1` VARCHAR(500) NULL COMMENT '비교첫번째칼럼추출(컬럼명:변환키)' AFTER `tobe_enc_key`" % fq_table)
                    conn.commit()
                    print("[INFO] 테이블 %s 에 compare_col1 컬럼을 자동으로 추가했습니다." % fq_table)
                except Exception as alter_err:
                    print("[WARNING] [%s] compare_col1 컬럼 추가 실패: %s" % (table_label, str(alter_err)))
            else:
                print("[DB_LOAD] [%s] compare_col1 컬럼은 이미 존재함" % table_label)
            if "compare_col2" not in columns:
                try:
                    print("[DB_LOAD] [%s] compare_col2 컬럼 추가 시도" % table_label)
                    cursor.execute("ALTER TABLE %s ADD COLUMN `compare_col2` VARCHAR(500) NULL COMMENT '비교두번째칼럼추출(컬럼명:변환키)' AFTER `compare_col1`" % fq_table)
                    conn.commit()
                    print("[INFO] 테이블 %s 에 compare_col2 컬럼을 자동으로 추가했습니다." % fq_table)
                except Exception as alter_err:
                    print("[WARNING] [%s] compare_col2 컬럼 추가 실패: %s" % (table_label, str(alter_err)))
            else:
                print("[DB_LOAD] [%s] compare_col2 컬럼은 이미 존재함" % table_label)
        
        try:
            print("[DB_LOAD] [%s] DELETE 실행 시작: table=%s, mid=%s" % (table_label, fq_table, mid))
            cursor.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_table, (mid,))
            conn.commit()
            print("[DB_LOAD] [%s] DELETE 완료" % table_label)
            
            if batch:
                print("[DB_LOAD] [%s] INSERT 실행 시작: rows=%d" % (table_label, batch_size))
                cursor.executemany(sql_insert.format(table=fq_table), batch)
                conn.commit()
                print("[DB_LOAD] [%s] INSERT 완료" % table_label)
            else:
                print("[DB_LOAD] [%s] INSERT 대상이 없어 건너뜁니다." % table_label)
            print("[INFO] DB 적재 완료 [%s]: %s (DELETE/INSERT mid=%s, %d 건)" % (table_label, fq_table, mid, batch_size))
            return len(batch), None
        except Exception as insert_err:
            print("[WARNING] [%s] 테이블 %s 데이터 적재 실패 (%s). 테이블을 재생성(DROP & CREATE) 후 다시 시도합니다." % (table_label, fq_table, str(insert_err)))
            print("[TRACE] [%s] 적재 실패 상세\n%s" % (table_label, traceback.format_exc()), file=sys.stderr)
            try:
                print("[DB_LOAD] [%s] 재생성 시도: DROP TABLE %s" % (table_label, fq_table))
                conn.rollback()
                cursor.execute("DROP TABLE IF EXISTS %s" % fq_table)
                conn.commit()
                
                print("[DB_LOAD] [%s] 재생성 후 DDL 실행 시작" % table_label)
                cursor.execute(ddl_create.format(table=fq_table))
                conn.commit()
                print("[DB_LOAD] [%s] 재생성 후 DDL 실행 완료" % table_label)
                

                print("[DB_LOAD] [%s] 재생성 후 DELETE 실행 시작" % table_label)
                cursor.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_table, (mid,))
                conn.commit()
                print("[DB_LOAD] [%s] 재생성 후 DELETE 완료" % table_label)
                
                if batch:
                    print("[DB_LOAD] [%s] 재생성 후 INSERT 실행 시작: rows=%d" % (table_label, batch_size))
                    cursor.executemany(sql_insert.format(table=fq_table), batch)
                    conn.commit()
                    print("[DB_LOAD] [%s] 재생성 후 INSERT 완료" % table_label)
                else:
                    print("[DB_LOAD] [%s] 재생성 후 INSERT 대상이 없어 건너뜁니다." % table_label)
                print("[INFO] 테이블 재생성 후 DB 적재 완료 [%s]: %s (DELETE/INSERT mid=%s, %d 건)" % (table_label, fq_table, mid, batch_size))
                return len(batch), None
            except Exception as retry_err:
                print("[ERROR] [%s] 테이블 재생성 후 DB 적재 역시 실패하였습니다: %s" % (table_label, str(retry_err)), file=sys.stderr)
                print("[TRACE] [%s] 재생성 후 실패 상세\n%s" % (table_label, traceback.format_exc()), file=sys.stderr)
                raise retry_err
                
    except Exception as e:
        print("[ERROR] DB 적재 실패 [%s]: %s" % (table_label, str(e)), file=sys.stderr)
        print("[TRACE] [%s] DB 적재 실패 상세\n%s" % (table_label, traceback.format_exc()), file=sys.stderr)
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
        f = open(filepath, "wb")
        f.write(codecs.BOM_UTF8)
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            row = dict(r)
            row_op_dtm = row.get("op_dtm", "").strip()
            if not row_op_dtm or row_op_dtm.upper() == "NONE":
                row_op_dtm = op_dtm
            row["op_dtm"] = row_op_dtm
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
                row_op_dtm = row.get("op_dtm", "").strip()
                if not row_op_dtm or row_op_dtm.upper() == "NONE":
                    row_op_dtm = op_dtm
                row["op_dtm"] = row_op_dtm
                writer.writerow(row)

def to_int(v):
    try:
        if v is None or str(v).strip() == "" or str(v).strip().lower() == "none":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None

def build_db_batch(results, run_id, mid, op_dtm, include_chk_result=False):
    batch = []
    for r in results:
        r_op_dtm = r.get("op_dtm", "").strip()
        if not r_op_dtm or r_op_dtm.upper() == "NONE":
            r_op_dtm = op_dtm
        if include_chk_result:
            batch.append((
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
                r.get("query_text"),
                r.get("chk_result", ""),
                r_op_dtm
            ))
        else:
            batch.append((
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
                r.get("query_text"),
                r_op_dtm
            ))
    return batch

def build_db_batch_diff_cols(results, run_id, mid, op_dtm):
    batch = []
    for r in results:
        r_op_dtm = r.get("op_dtm", "").strip()
        if not r_op_dtm or r_op_dtm.upper() == "NONE":
            r_op_dtm = op_dtm
        batch.append((
            run_id,
            mid,
            r.get("db_name"),
            r.get("tbl_name"),
            r.get("column_name"),
            r.get("type_name"),
            to_int(r.get("integer_idx")),
            r.get("mig_dec"),
            r.get("tobe_enc_key"),
            r.get("compare_col1"),
            r.get("compare_col2"),
            r.get("tobe_enc_rsn"),
            r.get("asis_enc_yn"),
            r.get("source_file"),
            to_int(r.get("line_number")),
            r.get("matched_line"),
            r.get("vscode_open_cmd"),
            r.get("query_text"),
            r_op_dtm
        ))
    return batch

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Query Analyzer Script (v08_gm - 17차 수정)")
    parser.add_argument("ref_table", nargs='?', default="my_db.my_ref_table", help="검색기준테이블")
    parser.add_argument("search_dir", nargs='?', default="D:\\workspace\\enc", help="검색디렉토리")
    parser.add_argument("out_table", nargs='?', default="my_db.my_result_table", help="검색결과테이블명")
    parser.add_argument("--mid", help="검색디렉토리 하위 MID값 (쉼표 구분)", default=None)
    parser.add_argument("--db", action="store_true", help="DB 적재 활성화")
    parser.add_argument("--conf", help="mysql.conf 파일 경로", default=None)
    parser.add_argument("--where", choices=["old", "new", "all"], help="검색기준테이블 조회 필터", default=None)
    parser.add_argument("--chk", choices=["default", "encdec_no", "all"], help="암호화/복호화 포함 및 제외 필터", default=None)

    args = parser.parse_args()

    print("=" * 80)
    print(" [DEBUG] 수신된 전체 실행 인자 (sys.argv):")
    print("  %s" % str(sys.argv))
    print("=" * 80)

    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    out_dir = os.path.join(script_dir, "out")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

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

    col_to_rows = {}
    for r in ref_rows:
        col_name = r.get("column_name", "").strip()
        if not col_name:
            continue
        c_lower = col_name.lower()
        if c_lower not in col_to_rows:
            col_to_rows[c_lower] = []
        col_to_rows[c_lower].append(r)

    mids = None
    if args.mid:
        mids = [m.strip() for m in args.mid.split(",") if m.strip()]

    source_files_by_mid = get_source_files(args.search_dir, mids)

    compiled_col_patterns = {}
    for col_lower in col_to_rows:
        compiled_col_patterns[col_lower] = re.compile(r"\b%s\b" % re.escape(col_lower), re.IGNORECASE)

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
        excluded_results = []
        diff_cols_results = [] # 13차 추가요청: 서로 다른 컬럼 비교용 결과
        
        seen_matches = set()
        seen_diff_matches = set() # (filepath, l_num, sorted_cols_str)

        total_files_scanned = len(files)
        files_with_matches = set()
        match_line_count = 0
        exclude_line_count = 0
        diff_cols_line_count = 0
        
        total_val, ok_val, nok_val = 0, 0, 0

        for filepath in files:
            queries, open_err, orig_lines, raw_content = open_and_extract_queries(filepath)
            if open_err:
                continue
            
            if not queries and raw_content.strip():
                queries = [{"query_text": raw_content, "query_text_clean": raw_content, "start_line_no": 1}]

            # 동일 파일 내에서 라인별 매칭 정보를 수집하기 위한 임시 맵
            # (line_number) -> set(col_lower)
            line_to_matched_cols = {}
            line_info_map = {} # (line_number) -> {"matched_line": l_val, "query_text": raw_query, "clean_l_val": clean_l_val}

            for q_idx, q_item in enumerate(queries, 1):
                raw_query = q_item["query_text"]
                clean_query = q_item.get("query_text_clean", raw_query)
                clean_query_upper = clean_query.upper()
                line_no_offset = q_item["start_line_no"]
                query_lines = raw_query.splitlines()

                for col_lower, rx in compiled_col_patterns.items():
                    if rx.search(clean_query_upper):
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
                            
                            match_key = (filepath, l_num, col_lower)
                            if match_key in seen_matches:
                                continue
                            seen_matches.add(match_key)
                            
                            clean_l_val = strip_comments(l_val)
                            
                            if not rx.search(clean_l_val):
                                continue
                            
                            orig_col_name = col_to_rows[col_lower][0]["column_name"]
                            vscode_cmd = "code -g %s:%s" % (os.path.abspath(filepath), l_num)
                            
                            assoc_tables = sorted(list({r.get("tbl_name") for r in col_to_rows[col_lower] if r.get("tbl_name")}))
                            assoc_tables_str = ", ".join(assoc_tables)

                            # default.encrypt/decrypt 포함 여부 확인
                            has_default_encdec = (
                                "default.encrypt" in l_val.lower() or 
                                "default.decrypt" in l_val.lower()
                            )
                            
                            is_pure = is_pure_column(clean_l_val, orig_col_name)
                            if has_default_encdec:
                                is_pure = False # 제외 방지

                            if is_pure:
                                exclude_line_count += 1
                                exclude_str = "[제외] %s %s (테이블: %s)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                
                                for ref_row in col_to_rows[col_lower]:
                                    final_dtm = ref_row.get("최종작업일시", "").strip()
                                    if not final_dtm or final_dtm.upper() == "NONE":
                                        final_dtm = op_dtm
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query,
                                        "op_dtm": final_dtm
                                    })
                                    excluded_results.append(result_row)
                                continue

                            # 결과 및 비교 대상만 line_to_matched_cols에 등록
                            if l_num not in line_to_matched_cols:
                                line_to_matched_cols[l_num] = set()
                            line_to_matched_cols[l_num].add(col_lower)
                            
                            if l_num not in line_info_map:
                                line_info_map[l_num] = {
                                    "matched_line": l_val,
                                    "query_text": raw_query,
                                    "clean_l_val": clean_l_val
                                }

                            is_included = True
                            if args.chk:
                                if args.chk == "default":
                                    is_included = has_default_encdec
                                elif args.chk == "encdec_no":
                                    is_included = not has_default_encdec
                                elif args.chk == "all":
                                    is_included = True

                            if is_included:
                                files_with_matches.add(filepath)
                                match_line_count += 1
                                for ref_row in col_to_rows[col_lower]:
                                    final_dtm = ref_row.get("최종작업일시", "").strip()
                                    if not final_dtm or final_dtm.upper() == "NONE":
                                        final_dtm = op_dtm
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query,
                                        "op_dtm": final_dtm
                                    })
                                    included_results.append(result_row)
                                    
                                match_str = "[매칭] %s %s (테이블: %s)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                
                                mid_print_buffer.append(match_str)
                                mid_print_buffer.append(content_str)
                                mid_print_buffer.append("-" * 80)
                            else:
                                exclude_line_count += 1
                                exclude_str = "[제외] %s %s (테이블: %s, CHK필터제외)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                
                                for ref_row in col_to_rows[col_lower]:
                                    final_dtm = ref_row.get("최종작업일시", "").strip()
                                    if not final_dtm or final_dtm.upper() == "NONE":
                                        final_dtm = op_dtm
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query,
                                        "op_dtm": final_dtm
                                    })
                                    excluded_results.append(result_row)

            # 13차, 15차 및 16차 추가요청: 쿼리 분석 완료 후 라인 단위로 서로 다른 컬럼 비교 탐색 수행
            for l_num, matched_cols in line_to_matched_cols.items():
                info = line_info_map[l_num]
                # 18차 수정보완3: row_number() 가 포함된 행은 비교 대상에서 제외 (오탐 방지)
                if "row_number" in info["matched_line"].lower():
                    continue
                clean_l_val = info["clean_l_val"]
                
                # 16차 수정요청: is null 단독 구문 및 case when 조건절 전처리 제거
                # 1) 'is null' 또는 'is not null' 제거
                clean_l_val = re.sub(
                    r"(?i)\bis\s+(?:not\s+)?null\b",
                    " ",
                    clean_l_val
                )
                # 2) case when ... then 구문에서 when 절 조건부만 제거하고 then만 남김
                clean_l_val = re.sub(
                    r"(?i)\bwhen\b.*?\bthen\b",
                    "then",
                    clean_l_val
                )

                l_val_lower = info["matched_line"].lower()
                
                # 19차 수정요청: CAST / default.encrypt/decrypt 를 비교대상 추출에서 정규화
                norm_l_val = normalize_diff_expression(clean_l_val)
                norm_l_val = re.sub(
                    r"(?i)\bis\s+(?:not\s+)?null\b",
                    " ",
                    norm_l_val
                )
                norm_l_val = re.sub(
                    r"(?i)\bwhen\b.*?\bthen\b",
                    "then",
                    norm_l_val
                )
                norm_l_val = remove_if_condition(norm_l_val)
                norm_l_val_lower = norm_l_val.lower()
                
                match_type = None
                matched_pair = None # (col1, col2)

                eq_pair = extract_ordered_pair_from_equal_expression(norm_l_val_lower)
                if eq_pair:
                    left_col = normalize_compare_token(eq_pair[0])
                    right_col = normalize_compare_token(eq_pair[1])
                    if left_col and right_col and left_col != right_col:
                        matched_pair = (left_col, right_col)
                        if re.search(r"\s*(!=|<>|>=|<=|>|<|\blike\b|\bin\b)\s*", norm_l_val_lower):
                            match_type = "4) 기타 비교 구문"
                        else:
                            match_type = "5) 비교식 (=)"
                if not match_type:
                    # 1) 일반 13차 비교 규칙 적용 (norm_l_val에 대해 검사)
                    if len(matched_cols) >= 2:
                        match_type = check_diff_cols_match(norm_l_val_lower, matched_cols)
                        if match_type:
                            # determine original left-to-right order by locating first occurrences
                            cols_list = list(matched_cols)
                            cols_pos = [(norm_l_val_lower.find(c), c) for c in cols_list]
                            cols_pos = [p for p in cols_pos if p[0] != -1]
                            cols_pos.sort(key=lambda x: x[0])
                            if len(cols_pos) >= 2:
                                matched_pair = (cols_pos[0][1], cols_pos[1][1])
                            else:
                                # fallback to deterministic ordering
                                sorted_cols = sorted(cols_list)
                                matched_pair = (sorted_cols[0], sorted_cols[1])
                    
                    # 2) 15차 예외 및 추가 비교 규칙 적용 (기준테이블 미등록 컬럼과의 비교 검출)
                    if not match_type and len(matched_cols) >= 1:
                        for col_lower in matched_cols:
                            # 정규화된 norm_l_val 상에서 col_lower 와 비교되는 상대방 컬럼 추적
                            # (단, 우변/좌변이 숫자, 따옴표 리터럴, null인 경우는 배제)
                            pat_1a = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s*(?:=|\!=|<>|>=|<=|>|<|\blike\b)\s*(?!\s*(?:['\"0-9]|null\b))\b([a-zA-Z0-9_.]+)\b" % re.escape(col_lower)
                            pat_1b = r"\b([a-zA-Z0-9_.]+)\b\s*(?:=|\!=|<>|>=|<=|>|<|\blike\b)\s*(?!\s*(?:['\"0-9]|null\b))\b(?:[a-zA-Z0-9_]+\.)?%s\b" % re.escape(col_lower)
                            pat_2 = r"\b(?:[a-zA-Z0-9_]+\.)?%s\b\s+(?:as\s+)?(?!\s*(?:['\"0-9]|null\b))\b([a-zA-Z0-9_.]+)\b" % re.escape(col_lower)
                            
                            m_1a = re.search(pat_1a, norm_l_val_lower)
                            m_1b = re.search(pat_1b, norm_l_val_lower)
                            m_2 = re.search(pat_2, norm_l_val_lower)
                            
                            target_col2 = None
                            if m_1a:
                                target_col2 = m_1a.group(1).strip().lower()
                                match_type = "5) default 암복호화 비교 (=)"
                            elif m_1b:
                                target_col2 = m_1b.group(1).strip().lower()
                                match_type = "5) default 암복호화 비교 (=)"
                            elif m_2:
                                target_col2 = m_2.group(1).strip().lower()
                                match_type = "6) default 암복호화 AS/Alias 문"
                            else:
                                # 3) 복합 식 AS/Alias 컬럼 매핑 (예: max(...) as alias_col)
                                alias_col = None
                                prefix_part = ""
                                m_as = re.search(r"\bas\s+([a-zA-Z0-9_]+)\b", norm_l_val_lower)
                                if m_as:
                                    alias_col = m_as.group(1).strip().lower()
                                    prefix_part = norm_l_val_lower[:m_as.start()]
                                else:
                                    m_no_as = re.search(r"\)\s+([a-zA-Z0-9_]+)\s*$", norm_l_val_lower)
                                    if m_no_as:
                                        alias_col = m_no_as.group(1).strip().lower()
                                        prefix_part = norm_l_val_lower[:m_no_as.start()]
                                        
                                if alias_col:
                                    if re.search(r"\b%s\b" % re.escape(col_lower), prefix_part):
                                        target_col2 = alias_col
                                        match_type = "6) default 암복호화 AS/Alias 문"
                                
                            if target_col2:
                                if "." in target_col2:
                                    target_col2 = target_col2.split(".")[-1]
                                if not is_real_compare_column_token(target_col2):
                                    target_col2 = None
                                    match_type = None
                                else:
                                    # SQL 예약어 필터링
                                    if target_col2 in SQL_KEYWORDS:
                                        target_col2 = None
                                        match_type = None
                                    if target_col2 and target_col2 != col_lower:
                                        matched_pair = (col_lower, target_col2)
                                        break

                            if not matched_pair and not target_col2:
                                fallback_cols = find_matched_columns_in_expression(norm_l_val_lower, matched_cols, {col_lower})
                                if fallback_cols:
                                    matched_pair = (col_lower, fallback_cols[0])
                                    match_type = "6) default 암복호화 함수 인자 컬럼"
                                    break

                if match_type and matched_pair:
                    # preserve the left-to-right order for compare_col1/compare_col2
                    pair_in_order = list(matched_pair)
                    if not all(is_real_compare_column_token(c) for c in pair_in_order):
                        continue
                    # for uniqueness key, keep sorted representation to avoid order variants
                    sorted_cols_str = ", ".join(sorted(pair_in_order))

                    diff_key = (filepath, l_num, sorted_cols_str)
                    if diff_key in seen_diff_matches:
                        continue
                    seen_diff_matches.add(diff_key)
                    
                    # 기준 정보 수집 (기준 테이블에 등록된 컬럼 기준)
                    rep_col = matched_pair[0]
                    if rep_col not in col_to_rows and len(matched_pair) > 1:
                        rep_col = matched_pair[1]
                    
                    if rep_col not in col_to_rows:
                        continue
                        
                    rep_row = col_to_rows[rep_col][0]
                    
                    # db_name, tbl_name 수집
                    assoc_tbls = set()
                    assoc_dbs = set()
                    for c in matched_pair:
                        if c in col_to_rows:
                            for r in col_to_rows[c]:
                                if r.get("tbl_name"): assoc_tbls.add(r.get("tbl_name"))
                                if r.get("db_name"): assoc_dbs.add(r.get("db_name"))
                        else:
                            if rep_row.get("tbl_name"): assoc_tbls.add(rep_row.get("tbl_name"))
                            if rep_row.get("db_name"): assoc_dbs.add(rep_row.get("db_name"))
                    
                    # 17차 수정: 비교 첫번째/두번째 칼럼 추출 및 컨버전 정보
                    compare_col1 = ""
                    compare_col2 = ""
                    if len(pair_in_order) >= 2:
                        # maintain left-to-right: first element -> compare_col1, second -> compare_col2
                        c1 = pair_in_order[0]
                        if c1 in col_to_rows:
                            orig_c1 = col_to_rows[c1][0]["column_name"]
                            key1 = col_to_rows[c1][0].get("tobe_enc_key", "")
                            conv_k1 = convert_key_to_code(key1)
                            if not conv_k1:
                                conv_k1 = "99"
                            compare_col1 = "%s:%s" % (orig_c1, conv_k1)
                        else:
                            compare_col1 = "%s:99" % c1

                        c2 = pair_in_order[1]
                        if c2 in col_to_rows:
                            orig_c2 = col_to_rows[c2][0]["column_name"]
                            key2 = col_to_rows[c2][0].get("tobe_enc_key", "")
                            conv_k2 = convert_key_to_code(key2)
                            if not conv_k2:
                                conv_k2 = "99"
                            compare_col2 = "%s:%s" % (orig_c2, conv_k2)
                        else:
                            compare_col2 = "%s:99" % c2

                    vscode_cmd = "code -g %s:%s" % (os.path.abspath(filepath), l_num)
                    
                    final_dtm = rep_row.get("최종작업일시", "").strip()
                    if not final_dtm or final_dtm.upper() == "NONE":
                        final_dtm = op_dtm
                    diff_row = {
                        "run_id": run_id,
                        "mid": mid,
                        "db_name": ", ".join(sorted(list(assoc_dbs))),
                        "tbl_name": ", ".join(sorted(list(assoc_tbls))),
                        "column_name": sorted_cols_str,
                        "type_name": rep_row.get("type_name", ""),
                        "integer_idx": rep_row.get("integer_idx", ""),
                        "mig_dec": rep_row.get("mig_dec", ""),
                        "tobe_enc_key": rep_row.get("tobe_enc_key", ""),
                        "compare_col1": compare_col1,
                        "compare_col2": compare_col2,
                        "tobe_enc_rsn": "유형: %s / %s" % (match_type, rep_row.get("tobe_enc_rsn", "")),
                        "asis_enc_yn": rep_row.get("asis_enc_yn", ""),
                        "source_file": os.path.abspath(filepath),
                        "line_number": l_num,
                        "matched_line": info["matched_line"].strip(),
                        "vscode_open_cmd": vscode_cmd,
                        "query_text": info["query_text"],
                        "op_dtm": final_dtm
                    }
                    diff_cols_results.append(diff_row)
                    diff_cols_line_count += 1

        csv_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s.csv" % (ref_tbl_only, out_suffix)))
        print_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_print.txt" % (ref_tbl_only, out_suffix)))
        ex_txt_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_exclude.txt" % (ref_tbl_only, out_suffix)))
        diff_csv_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_diff_cols.csv" % (ref_tbl_only, out_suffix)))

        results_default = []
        results_encdec_no = []
        if args.chk == "all":
            for r in included_results:
                line_lower = r.get("matched_line", "").lower()
                if "default.encrypt" in line_lower or "default.decrypt" in line_lower:
                    results_default.append(r)
                else:
                    results_encdec_no.append(r)
            
            total_val, ok_val, nok_val = verify_default_results(results_default)

        if included_results:
            save_csv(included_results, csv_path, CSV_FIELDNAMES, op_dtm)
            print("[INFO] 파일 저장 완료: %s  (%d 건)" % (csv_path, len(included_results)))

            if args.chk == "all":
                csv_path_default = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_default.csv" % (ref_tbl_only, out_suffix)))
                csv_path_encdec_no = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_encdec_no.csv" % (ref_tbl_only, out_suffix)))
                
                save_csv(results_default, csv_path_default, CSV_FIELDNAMES + ["chk_result"], op_dtm)
                print("[INFO] [all분리] 파일 저장 완료: %s  (%d 건 - OK: %d, NOK: %d)" % (csv_path_default, len(results_default), ok_val, nok_val))
                
                save_csv(results_encdec_no, csv_path_encdec_no, CSV_FIELDNAMES, op_dtm)
                print("[INFO] [all분리] 파일 저장 완료: %s  (%d 건)" % (csv_path_encdec_no, len(results_encdec_no)))
        else:
            print("[INFO] '%s' MID에 대해 추출된 매칭 결과 행이 없습니다. (결과 파일 미생성)" % mid)

        if diff_cols_results:
            save_csv(diff_cols_results, diff_csv_path, DIFF_CSV_FIELDNAMES, op_dtm)
            print("[INFO] 파일 저장 완료 (서로 다른 컬럼 비교): %s  (%d 건)" % (diff_csv_path, len(diff_cols_results)))
        else:
            print("[INFO] '%s' MID에 대해 추출된 서로 다른 컬럼 비교 매칭 결과가 없습니다. (비교 결과 파일 미생성)" % mid)

        if args.db:
            if included_results:
                print("[DB_LOAD] 결과데이터 적재 시작: mid=%s, rows=%d" % (mid, len(included_results)))
                batch_all = build_db_batch(included_results, run_id, mid, op_dtm, include_chk_result=False)
                db_load_table(mysql_conf, fq_out_table, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_all, mid, "결과데이터")

                if args.chk == "all":
                    fq_out_table_default = make_fq(out_schema, out_tbl_only + "_default")
                    print("[DB_LOAD] 결과데이터_default 적재 시작: mid=%s, rows=%d" % (mid, len(results_default)))
                    batch_default = build_db_batch(results_default, run_id, mid, op_dtm, include_chk_result=True)
                    db_load_table(mysql_conf, fq_out_table_default, _DDL_CREATE_RESULT_DEFAULT, _SQL_INSERT_RESULT_DEFAULT, batch_default, mid, "결과데이터_default")
                    
                    fq_out_table_encdec_no = make_fq(out_schema, out_tbl_only + "_encdec_no")
                    print("[DB_LOAD] 결과데이터_encdec_no 적재 시작: mid=%s, rows=%d" % (mid, len(results_encdec_no)))
                    batch_encdec_no = build_db_batch(results_encdec_no, run_id, mid, op_dtm, include_chk_result=False)
                    db_load_table(mysql_conf, fq_out_table_encdec_no, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_encdec_no, mid, "결과데이터_encdec_no")
            
            if excluded_results:
                fq_out_table_exclude = make_fq(out_schema, out_tbl_only + "_exclude")
                print("[DB_LOAD] 제외데이터 적재 시작: mid=%s, rows=%d" % (mid, len(excluded_results)))
                batch_exclude = build_db_batch(excluded_results, run_id, mid, op_dtm, include_chk_result=False)
                db_load_table(mysql_conf, fq_out_table_exclude, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_exclude, mid, "제외데이터")

            if diff_cols_results:
                fq_out_table_diff_cols = make_fq(out_schema, out_tbl_only + "_diff_cols")
                print("[DB_LOAD] 비교데이터(diff_cols) 적재 시작: mid=%s, rows=%d" % (mid, len(diff_cols_results)))
                batch_diff_cols = build_db_batch_diff_cols(diff_cols_results, run_id, mid, op_dtm)
                db_load_table(mysql_conf, fq_out_table_diff_cols, _DDL_CREATE_DIFF_COLS, _SQL_INSERT_DIFF_COLS, batch_diff_cols, mid, "비교데이터(diff_cols)")

        if len(mid_exclude_buffer) > 3:
            with codecs.open(ex_txt_path, "w", encoding="utf-8") as ef:
                ef.write("\n".join(mid_exclude_buffer) + "\n")
            print("[INFO] 제외행 내용 파일 생성 완료: %s" % ex_txt_path)

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
        summary_lines.append("  - 매칭 건수 (서로다른컬럼비교): %d 건" % diff_cols_line_count)
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
            
        if diff_cols_results:
            summary_lines.append("     - 비교 CSV 파일   : %s (%d 건)" % (diff_csv_path, len(diff_cols_results)))
        else:
            summary_lines.append("     - 비교 CSV 파일   : (생성 없음)")

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

            if diff_cols_results:
                fq_out_table_diff_cols = make_fq(out_schema, out_tbl_only + "_diff_cols")
                summary_lines.append("     - 비교 DB 테이블  : %s (%d 건)" % (fq_out_table_diff_cols, len(diff_cols_results)))
            else:
                summary_lines.append("     - 비교 DB 테이블  : (적재 없음)")
        else:
            summary_lines.append("     - 결과/제외/비교 DB 테이블 : (적재 없음)")
        summary_lines.append("=" * 80)

        for line in summary_lines:
            print(line)

        mid_print_buffer.extend(summary_lines)
        if included_results or diff_cols_results:
            with codecs.open(print_path, "w", encoding="utf-8") as pf:
                pf.write("\n".join(mid_print_buffer) + "\n")
            print("[INFO] 화면출력내용 파일 생성 완료: %s" % print_path)

    print("=" * 80)
    print(" [매칭 분석 공정 완료]")
    print("=" * 80)


if __name__ == "__main__":
    main()
