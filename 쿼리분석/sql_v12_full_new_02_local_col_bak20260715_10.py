#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# sql_v12_full_new_02_local_col.py (2026-07-14 수정 완료)
#
# [수정 사항 요약 및 이력]
#   - 2026-07-14 (1차 수정): 파라미터 방식 변경
#     * <검색기준테이블> 필수 위치 인자를 제거하고, 쉼표 구분 컬럼 리스트를 받는 '--col' 옵션과
#       컬럼 리스트가 들어있는 텍스트 파일 경로를 받는 '--in' 옵션을 도입.
#       ('--in' 파일의 경로가 명시되지 않은 경우 현재 디렉토리에서 탐색하여 자동 로드)
#     * 필수 위치 인자는 <검색디렉토리> <검색결과테이블명> 2개로 조정.
#   - 2026-07-14 (2차 수정): '--where' 옵션 제거
#     * 검색기준테이블 조회가 불필요해짐에 따라 '--where' 파라미터 및 관련 내부 필터링/출력 분기를 전면 제거.
#   - 2026-07-14 (3차 수정): 결과 산출물 대상 축소 및 '--chk' 옵션 제거
#     * '--chk' 옵션을 제거하고 관련 분기 로직 및 "_default", "_encdec_no", "_exclude" DB 테이블 적재를 전면 생략 처리.
#     * 오직 지정한 <검색결과테이블명> (전체 칼럼 매칭)과 비교DB테이블({결과테이블명}_diff_cols) 두 개만 생성 및 DB 적재하도록 단순화.
#   - 2026-07-14 (4차 수정): 불필요 메타 컬럼 제외 및 출력 시 테이블명 생략
#     * 테이블 생성 및 CSV 파일 출력 시 run_id, db_name, tbl_name, type_name, integer_idx,
#       mig_dec, tobe_enc_key, tobe_enc_rsn, asis_enc_yn 컬럼을 전면 제외하도록 수정.
#     * 화면 출력 및 결과 텍스트 파일 생성 시 매칭/제외 라인 맨 끝의 '(테이블: ...)' 부분을 삭제하고 컬럼명만 깔끔하게 출력하도록 변경.
#   - 2026-07-14 (5차 수정): 비교 파일, 제외 파일 및 비교 DB 테이블 생성 차단
#     * 비교 CSV 파일, 제외 로그 파일 및 비교 DB 테이블(diff_cols)을 생성/적재하지 않도록 출력 로직을 비활성화.
#     * 이에 맞게 최종 요약 리포트 구조를 단순화.
#   - 2026-07-14 (6차 수정): 기존 mid 결과 파일 자동 백업 기능 지원
#     * 분석 시작 시 이미 동일한 명칭의 전체 매칭 CSV 결과 파일 및 화면 출력 로그 텍스트 파일이 있다면
#       해당 파일을 "결과파일명_YYYYMMDD_HHMMSS.확장자" 포맷으로 먼저 복사 백업한 뒤 새로운 결과 파일을 생성하도록 개선.
#   - 2026-07-14 (7차 수정): --mid 미지정 시 fallback 처리 보정
#     * --mid 인자가 주어지지 않았을 때 기존에는 최하위 디렉토리명을 mid로 사용했으나, "all" 키워드로 고정하고 해당 mid에 맞게 파일명 및 DB 테이블 데이터가 적재되도록 수정.
#   - 2026-07-14 (9차 수정): --in 및 --col 동시 지정 시 필터링 로직 추가
#     * --in 파일의 칼럼 리스트 기준으로 하위 소스를 1차 검색한 후, --col 에 정의된 칼럼들이 매칭된 최종 결과만 파일 저장 및 DB 적재하도록 필터 처리.
#   - Python 2.7.5 하위 호환성 전면 적용(타입 힌팅 제거, BOM 마크 codecs.open() 사용 등) 및 기존 암호화 매칭 정밀 규칙 보존.
#
# [실행 예시]
#   1. 컬럼 리스트 직접 입력 검색 및 DB 적재:
#      python sql_v12_full_new_02_local_col.py D:\workspace\enc my_db.my_result_table --col col1,col2,col3 --db --conf D:\workspace\enc\mysql.conf
#   2. 컬럼 파일 입력 검색 (DB 미적재, 로컬 파일만 생성):
#      python sql_v12_full_new_02_local_col.py D:\workspace\enc my_db.my_result_table --in col_list.txt --mid abc
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
    "mid", "column_name",
    "source_file", "line_number", "matched_line", "vscode_open_cmd",
    "op_dtm"
]

# 비교 결과 파일 최종 필드 레이아웃 (query_text 제외)
DIFF_CSV_FIELDNAMES = [
    "mid", "column_name", "compare_col1", "compare_col2",
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
        default_mid = "all"
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
# DB 테이블 DDL 및 적재 모듈 (결과 테이블과 diff_cols 비교 테이블만 생성)
# ============================================================
_DDL_CREATE_RESULT = """
CREATE TABLE IF NOT EXISTS {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `mid`              VARCHAR(100)  NOT NULL                 COMMENT '검색 MID',
  `column_name`      VARCHAR(500)  NULL,
  `source_file`      VARCHAR(500)  NULL,
  `line_number`      INT           NULL,
  `matched_line`     TEXT          NULL,
  `vscode_open_cmd`  VARCHAR(1000) NULL,
  `query_text`       LONGTEXT      NULL,
  `op_dtm`           DATETIME      NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_mid`       (`mid`),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과';
"""

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (mid, column_name, source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s)
"""

_DDL_CREATE_DIFF_COLS = """
CREATE TABLE IF NOT EXISTS {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `mid`              VARCHAR(100)  NOT NULL                 COMMENT '검색 MID',
  `column_name`      VARCHAR(500)  NULL,
  `compare_col1`     VARCHAR(500)  NULL                     COMMENT '비교첫번째칼럼추출(컬럼명:변환키)',
  `compare_col2`     VARCHAR(500)  NULL                     COMMENT '비교두번째칼럼추출(컬럼명:변환키)',
  `source_file`      VARCHAR(500)  NULL,
  `line_number`      INT           NULL,
  `matched_line`     TEXT          NULL,
  `vscode_open_cmd`  VARCHAR(1000) NULL,
  `query_text`       LONGTEXT      NULL,
  `op_dtm`           DATETIME      NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_mid`       (`mid`),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과(비교컬럼)';
"""

_SQL_INSERT_DIFF_COLS = """
INSERT INTO {table}
  (mid, column_name, compare_col1, compare_col2,
   source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    cursor.execute("ALTER TABLE %s ADD COLUMN `compare_col1` VARCHAR(500) NULL COMMENT '비교첫번째칼럼추출(컬럼명:변환키)' AFTER `column_name`" % fq_table)
                    conn.commit()
                except Exception as alter_err:
                    print("[WARNING] [%s] compare_col1 컬럼 추가 실패: %s" % (table_label, str(alter_err)))
            if "compare_col2" not in columns:
                try:
                    print("[DB_LOAD] [%s] compare_col2 컬럼 추가 시도" % table_label)
                    cursor.execute("ALTER TABLE %s ADD COLUMN `compare_col2` VARCHAR(500) NULL COMMENT '비교두번째칼럼추출(컬럼명:변환키)' AFTER `compare_col1`" % fq_table)
                    conn.commit()
                except Exception as alter_err:
                    print("[WARNING] [%s] compare_col2 컬럼 추가 실패: %s" % (table_label, str(alter_err)))
        
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
                raise retry_err
                
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

def backup_existing_file(filepath):
    if not filepath or not os.path.isfile(filepath):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = os.path.dirname(filepath)
    base_name = os.path.basename(filepath)
    name, ext = os.path.splitext(base_name)
    backup_name = "%s_%s%s" % (name, timestamp, ext)
    backup_path = os.path.join(dir_name, backup_name)
    try:
        import shutil
        shutil.copy2(filepath, backup_path)
        print("[BACKUP] 기존 결과 파일을 백업하였습니다: %s -> %s" % (filepath, backup_path))
    except Exception as e:
        print("[WARNING] 기존 결과 파일 백업 실패: %s (%s)" % (filepath, str(e)))

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

def build_db_batch(results, mid, op_dtm):
    return [
        (
            mid,
            r.get("column_name"),
            r.get("source_file"),
            to_int(r.get("line_number")),
            r.get("matched_line"),
            r.get("vscode_open_cmd"),
            r.get("query_text"),
            op_dtm
        )
        for r in results
    ]

def build_db_batch_diff_cols(results, mid, op_dtm):
    return [
        (
            mid,
            r.get("column_name"),
            r.get("compare_col1"),
            r.get("compare_col2"),
            r.get("source_file"),
            to_int(r.get("line_number")),
            r.get("matched_line"),
            r.get("vscode_open_cmd"),
            r.get("query_text"),
            op_dtm
        )
        for r in results
    ]

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Query Analyzer Script (Col/File Mode)")
    parser.add_argument("search_dir", help="검색디렉토리")
    parser.add_argument("out_table", help="검색결과테이블명")
    parser.add_argument("--col", help="쉼표(,)로 구분된 검색 대상 컬럼 리스트", default=None)
    parser.add_argument("--in", dest="in_file", help="검색 대상 컬럼 리스트가 작성된 파일 경로", default=None)
    parser.add_argument("--mid", help="검색디렉토리 하위 MID값 (쉼표 구분)", default=None)
    parser.add_argument("--db", action="store_true", help="DB 적재 활성화")
    parser.add_argument("--conf", help="mysql.conf 파일 경로", default=None)

    args = parser.parse_args()

    print("=" * 80)
    print(" [DEBUG] 수신된 전체 실행 인자 (sys.argv):")
    print("  %s" % str(sys.argv))
    print("=" * 80)

    # 1. 컬럼 리스트 수집
    if not args.col and not args.in_file:
        print("[ERROR] --col 옵션 또는 --in 옵션 중 하나는 반드시 지정해야 합니다.")
        sys.exit(1)

    cols = []
    filter_cols_set = None

    if args.in_file and args.col:
        filepath = args.in_file.strip().replace("\\", os.sep).replace("/", os.sep)
        if not os.path.dirname(filepath):
            filepath = os.path.join(os.getcwd(), filepath)
        filepath = os.path.abspath(filepath)
        
        if not os.path.isfile(filepath):
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            fallback = os.path.join(script_dir, args.in_file)
            if os.path.isfile(fallback):
                filepath = fallback
            else:
                print("[ERROR] 컬럼 파일을 찾을 수 없습니다: %s" % filepath)
                sys.exit(1)
                
        try:
            with codecs.open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str or line_str.startswith("#"):
                        continue
                    for c in line_str.split(","):
                        c_clean = c.strip()
                        if c_clean:
                            cols.append(c_clean)
        except Exception as e:
            print("[ERROR] 컬럼 파일 읽기 실패: %s" % str(e))
            sys.exit(1)
            
        filter_cols_set = set([c.strip().lower() for c in args.col.split(",") if c.strip()])
    elif args.col:
        cols = [c.strip() for c in args.col.split(",") if c.strip()]
    else:
        filepath = args.in_file.strip().replace("\\", os.sep).replace("/", os.sep)
        if not os.path.dirname(filepath):
            filepath = os.path.join(os.getcwd(), filepath)
        filepath = os.path.abspath(filepath)
        
        if not os.path.isfile(filepath):
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            fallback = os.path.join(script_dir, args.in_file)
            if os.path.isfile(fallback):
                filepath = fallback
            else:
                print("[ERROR] 컬럼 파일을 찾을 수 없습니다: %s" % filepath)
                sys.exit(1)
                
        try:
            with codecs.open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str or line_str.startswith("#"):
                        continue
                    for c in line_str.split(","):
                        c_clean = c.strip()
                        if c_clean:
                            cols.append(c_clean)
        except Exception as e:
            print("[ERROR] 컬럼 파일 읽기 실패: %s" % str(e))
            sys.exit(1)

    print("[INFO] 검색 대상 컬럼 리스트 조회 완료: %d 개" % len(cols))
    if filter_cols_set:
        print("[INFO] 필터 대상 컬럼 리스트 수집 완료: %d 개 (%s)" % (len(filter_cols_set), args.col))
    print("-" * 80)

    unique_ref_rows = []
    seen_cols = set()
    for col_name in cols:
        c_lower = col_name.strip().lower()
        if c_lower not in seen_cols:
            seen_cols.add(c_lower)
            unique_ref_rows.append({"column_name": col_name})
            
    ref_rows = unique_ref_rows
    print("[INFO] 중복 제거 후 검색 대상 컬럼 수: %d 개" % len(ref_rows))
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
        if re.match(r"^[a-zA-Z0-9_]+$", col_lower):
            compiled_col_patterns[col_lower] = re.compile(r"\b%s\b" % re.escape(col_lower), re.IGNORECASE)
        else:
            compiled_col_patterns[col_lower] = re.compile(re.escape(col_lower), re.IGNORECASE)

    out_schema, out_tbl_only = split_schema_table(args.out_table)
    fq_out_table = make_fq(out_schema, out_tbl_only)

    for mid, files in source_files_by_mid.items():
        out_suffix = mid

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
        diff_cols_results = []
        
        seen_matches = set()
        seen_diff_matches = set()

        total_files_scanned = len(files)
        files_with_matches = set()
        match_line_count = 0
        exclude_line_count = 0
        diff_cols_line_count = 0

        for filepath in files:
            queries, open_err, orig_lines, raw_content = open_and_extract_queries(filepath)
            if open_err:
                continue
            
            if not queries and raw_content.strip():
                queries = [{"query_text": raw_content, "query_text_clean": raw_content, "start_line_no": 1}]

            line_to_matched_cols = {}
            line_info_map = {}

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

                            # 9차 수정: --in 과 --col 이 모두 기입된 경우 결과 필터링
                            if filter_cols_set is not None and col_lower not in filter_cols_set:
                                continue
                            
                            clean_l_val = strip_comments(l_val)
                            
                            if not rx.search(clean_l_val):
                                continue
                            
                            orig_col_name = col_to_rows[col_lower][0]["column_name"]
                            vscode_cmd = "code -g %s:%s" % (os.path.abspath(filepath), l_num)
                            
                            assoc_tables = sorted(list({r.get("tbl_name") for r in col_to_rows[col_lower] if r.get("tbl_name")}))
                            assoc_tables_str = ", ".join(assoc_tables)

                            has_default_encdec = (
                                "default.encrypt" in l_val.lower() or 
                                "default.decrypt" in l_val.lower()
                            )
                            
                            is_pure = is_pure_column(clean_l_val, orig_col_name)
                            if has_default_encdec:
                                is_pure = False

                            if is_pure:
                                exclude_line_count += 1
                                exclude_str = "[제외] %s %s" % (vscode_cmd, orig_col_name)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query
                                    })
                                    excluded_results.append(result_row)
                                continue

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

                            if is_included:
                                files_with_matches.add(filepath)
                                match_line_count += 1
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "mid": mid,
                                        "source_file": os.path.abspath(filepath),
                                        "line_number": l_num,
                                        "matched_line": l_val.strip(),
                                        "vscode_open_cmd": vscode_cmd,
                                        "query_text": raw_query
                                    })
                                    included_results.append(result_row)
                                    
                                match_str = "[매칭] %s %s" % (vscode_cmd, orig_col_name)
                                content_str = "[내용] %s" % l_val.strip()
                                
                                mid_print_buffer.append(match_str)
                                mid_print_buffer.append(content_str)
                                mid_print_buffer.append("-" * 80)

            # 라인 단위로 서로 다른 컬럼 비교 탐색 수행 (diff_cols 추출)
            for l_num, matched_cols in line_to_matched_cols.items():
                info = line_info_map[l_num]
                if "row_number" in info["matched_line"].lower():
                    continue
                clean_l_val = info["clean_l_val"]
                
                clean_l_val = re.sub(
                    r"(?i)\bis\s+(?:not\s+)?null\b",
                    " ",
                    clean_l_val
                )
                clean_l_val = re.sub(
                    r"(?i)\bwhen\b.*?\bthen\b",
                    "then",
                    clean_l_val
                )

                l_val_lower = info["matched_line"].lower()
                
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
                matched_pair = None

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
                    if len(matched_cols) >= 2:
                        match_type = check_diff_cols_match(norm_l_val_lower, matched_cols)
                        if match_type:
                            cols_list = list(matched_cols)
                            cols_pos = [(norm_l_val_lower.find(c), c) for c in cols_list]
                            cols_pos = [p for p in cols_pos if p[0] != -1]
                            cols_pos.sort(key=lambda x: x[0])
                            if len(cols_pos) >= 2:
                                matched_pair = (cols_pos[0][1], cols_pos[1][1])
                            else:
                                sorted_cols = sorted(cols_list)
                                matched_pair = (sorted_cols[0], sorted_cols[1])
                    
                    if not match_type and len(matched_cols) >= 1:
                        for col_lower in matched_cols:
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
                    pair_in_order = list(matched_pair)
                    if not all(is_real_compare_column_token(c) for c in pair_in_order):
                        continue
                    sorted_cols_str = ", ".join(sorted(pair_in_order))

                    diff_key = (filepath, l_num, sorted_cols_str)
                    if diff_key in seen_diff_matches:
                        continue
                    seen_diff_matches.add(diff_key)
                    
                    rep_col = matched_pair[0]
                    if rep_col not in col_to_rows and len(matched_pair) > 1:
                        rep_col = matched_pair[1]
                    
                    if rep_col not in col_to_rows:
                        continue
                        
                    rep_row = col_to_rows[rep_col][0]
                    
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
                    
                    compare_col1 = ""
                    compare_col2 = ""
                    if len(pair_in_order) >= 2:
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
                        "op_dtm": op_dtm
                    }
                    diff_cols_results.append(diff_row)
                    diff_cols_line_count += 1

        csv_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s.csv" % (out_tbl_only, out_suffix)))
        print_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_print.txt" % (out_tbl_only, out_suffix)))

        # 전체 매칭 결과 CSV 저장
        if included_results:
            backup_existing_file(csv_path)
            save_csv(included_results, csv_path, CSV_FIELDNAMES, op_dtm)
            print("[INFO] 파일 저장 완료: %s  (%d 건)" % (csv_path, len(included_results)))
        else:
            print("[INFO] '%s' MID에 대해 추출된 매칭 결과 행이 없습니다." % mid)

        # DB 적재 수행 (요청 3번: 결과 테이블만 적재)
        if args.db:
            if included_results:
                                print("[DB_LOAD] 결과데이터 적재 시작: mid=%s, rows=%d" % (mid, len(included_results)))
                                batch_all = build_db_batch(included_results, mid, op_dtm)
                                db_load_table(mysql_conf, fq_out_table, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch_all, mid, "결과데이터")

        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append(" [분석 완료 요약 - MID: %s]" % mid)
        summary_lines.append("=" * 80)
        summary_lines.append("  - 검색 대상 소스 파일 수   : %d 개" % total_files_scanned)
        summary_lines.append("  - 매칭 발생 소스 파일 수   : %d 개" % len(files_with_matches))
        summary_lines.append("  - 매칭 건수 (포함)          : %d 건" % match_line_count)
        summary_lines.append("-" * 80)
        summary_lines.append("  1. 생성 파일 정보")
        if included_results:
            summary_lines.append("     - 결과 CSV 파일   : %s (%d 건)" % (csv_path, len(included_results)))
            summary_lines.append("     - 화면 출력 파일  : %s (%d 건)" % (print_path, match_line_count))
        else:
            summary_lines.append("     - 결과 CSV 파일   : (생성 없음)")
            summary_lines.append("     - 화면 출력 파일  : (생성 없음)")
            
        summary_lines.append("  2. DB 적재 정보")
        if args.db:
            if included_results:
                summary_lines.append("     - 결과 DB 테이블  : %s (%d 건)" % (fq_out_table, len(included_results)))
            else:
                summary_lines.append("     - 결과 DB 테이블  : (적재 없음)")
        else:
            summary_lines.append("     - 결과 DB 테이블      : (적재 없음)")
        summary_lines.append("=" * 80)

        for line in summary_lines:
            print(line)

        mid_print_buffer.extend(summary_lines)
        if included_results:
            backup_existing_file(print_path)
            with codecs.open(print_path, "w", encoding="utf-8") as pf:
                pf.write("\n".join(mid_print_buffer) + "\n")
            print("[INFO] 화면출력내용 파일 생성 완료: %s" % print_path)

    print("=" * 80)
    print(" [매칭 분석 공정 완료]")
    print("=" * 80)


if __name__ == "__main__":
    main()
