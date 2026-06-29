#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v09_3cha.py
#
# [실행 형식]
# python p190872_local_chk_v09_3cha.py <검색기준테이블> <검색기준소스테이블> [--where <old|new|all>] [--db] [--conf <설정파일>]
#
# [실행 예시]
# python p190872_local_chk_v09_3cha.py my_db.my_ref_table my_db.my_src_table --where all --db --conf mysql.conf
#
# [수정 이력]
# ─────────────────────────────────────────────────────────────
# v09_3cha (2026-06-29)
#   - p190872_local_chk_v08_3cha.py의 기존 칼럼 단독 매칭 추출로직을 완벽히 유지
#   - Sql v12 full new 02 local.py의 테이블+칼럼 매칭 로직을 추가로 덧붙여 융합 구현
#   - 소스파일 내의 쿼리 단위별 query_text 수집 기능 추가 명세 및 파일/DB 저장 반영
#   - Python 2.7.5 환경 호환성 완벽 지원:
#     * f-string 및 타입 힌팅 전면 제거
#     * codecs.open() 및 Python 2.x 유니코드 수동 인코딩 CSV 라이터 적용
#     * os.makedirs(exist_ok=True) -> os.path.exists() 사전 조건 처리
#     * ConfigParser 하위버전 임포트 호환 적용
#   - 결과 스키마 및 테이블/파일 분리:
#     * 칼럼 단독 매칭: 테이블 <소스테이블>_work 및 out/<소스테이블>_work.csv 생성 및 적재
#     * 테이블+칼럼 매칭: 테이블 <소스테이블>_work_tbl_col 및 out/<소스테이블>_work_tbl_col.csv 생성 및 적재
#     * 테이블 DDL 구조 및 CSV 필드 전체에 tbl_name과 query_text 컬럼 추가 명세
#   - DB 적재 방식 개선: 있으면 mid 기준 삭제(DELETE FROM table WHERE mid = %s) 후 bulk insert(executemany) 하도록 조치
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
            env_fallback = os.path.join(script_dir, "env", "mysql.conf")
            if os.path.isfile(env_fallback):
                path = env_fallback
            else:
                return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path

    cp = configparser.ConfigParser()
    try:
        with codecs.open(path, "r", encoding="utf-8") as f:
            if hasattr(cp, "read_file"):
                cp.read_file(f)
            else:
                cp.readfp(f)
        conf = {}
        for option in cp.options("mysql"):
            conf[option] = cp.get("mysql", option)
        missing = [k for k in ('host', 'user', 'password', 'database') if not conf.get(k)]
        if missing:
            return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
        return conf, None
    except Exception as e:
        return None, "mysql.conf 로드 에러: %s" % str(e)

# ============================================================
# 유틸리티 함수
# ============================================================
def split_schema_table(full_table):
    parts = full_table.split('.')
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", full_table.strip()

def make_fq(schema, table):
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table

# ============================================================
# DB 테이블 조회 로직
# ============================================================
def load_ref_rows_from_db(mysql_conf, ref_table, where_opt="all"):
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
        columns_info = cursor.fetchall()
        existing_cols = {row[0].lower() for row in columns_info}
        select_cols = [row[0] for row in columns_info]
        select_parts = ["`%s`" % col for col in select_cols]

        where_conds = []
        if "tobe_enc_key" in existing_cols:
            where_conds.append("(`tobe_enc_key` IS NOT NULL AND `tobe_enc_key` <> '')")
        else:
            return [], ref_schema, ref_tbl_only, "검색기준테이블에 'tobe_enc_key' 컬럼이 존재하지 않습니다."

        if where_opt == "old":
            if "asis_enc_yn" in existing_cols:
                where_conds.append("`asis_enc_yn` = 'Y'")
            else:
                return [], ref_schema, ref_tbl_only, "where old 조건에 필요한 'asis_enc_yn' 컬럼이 없습니다."
        elif where_opt == "new":
            if "asis_enc_yn" in existing_cols:
                where_conds.append("`asis_enc_yn` = 'N'")
            else:
                return [], ref_schema, ref_tbl_only, "where new 조건에 필요한 'asis_enc_yn' 컬럼이 없습니다."

        where_clause = ""
        if where_conds:
            where_clause = "WHERE " + " AND ".join(where_conds)

        sql = "SELECT %s FROM %s %s" % (", ".join(select_parts), fq_table, where_clause)
        cursor.execute(sql)
        db_rows = cursor.fetchall()

        for db_row in db_rows:
            row_dict = {}
            for idx, col in enumerate(select_cols):
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

def load_source_files_from_db(mysql_conf, src_table):
    files = []
    conn = None
    cursor = None
    src_schema, src_tbl_only = split_schema_table(src_table)
    fq_table = make_fq(src_schema, src_tbl_only)

    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        if src_schema:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (src_schema, src_tbl_only)
            )
        else:
            cursor.execute("SHOW TABLES LIKE %s", (src_tbl_only,))
        row_chk = cursor.fetchone()
        exists = (row_chk[0] > 0) if row_chk else False
        if not exists:
            return [], "소스테이블이 존재하지 않습니다: %s" % src_table

        cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
        existing_cols = {row[0].lower() for row in cursor.fetchall()}
        if "local_file" not in existing_cols:
            return [], "소스테이블에 'local_file' 컬럼이 존재하지 않습니다: %s" % src_table

        select_parts = ["`local_file`"]
        id_col = "id" if "id" in existing_cols else None
        mid_col = "mid" if "mid" in existing_cols else None
        source_file_col = "source_file" if "source_file" in existing_cols else None
        if id_col:
            select_parts.append("`%s`" % id_col)
        if mid_col:
            select_parts.append("`%s`" % mid_col)
        if source_file_col:
            select_parts.append("`%s`" % source_file_col)

        sql = "SELECT DISTINCT %s FROM %s WHERE `local_file` IS NOT NULL AND `local_file` <> ''" % (
            ", ".join(select_parts), fq_table
        )
        cursor.execute(sql)
        db_rows = cursor.fetchall()
        for row in db_rows:
            file_info = {
                "local_file": row[0].strip(),
                "id": "",
                "mid": "",
                "source_file": ""
            }
            curr_idx = 1
            if id_col:
                file_info["id"] = str(row[curr_idx]).strip() if row[curr_idx] is not None else ""
                curr_idx += 1
            if mid_col:
                file_info["mid"] = str(row[curr_idx]).strip() if row[curr_idx] is not None else ""
                curr_idx += 1
            if source_file_col:
                file_info["source_file"] = str(row[curr_idx]).strip() if row[curr_idx] is not None else ""
            files.append(file_info)

        return files, None
    except Exception as e:
        return [], "소스테이블 조회 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

# ============================================================
# Sql v12 정밀 매칭 파서 로직 및 상수 정의
# ============================================================
EXCLUDE_PATTERNS = [
    "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)",
    "sidtest.ad1901_rgb_ac190212_svc",
]

RESERVED_WORDS = {
    "SET","WHERE","AND","OR","ON","WHEN","THEN","ELSE",
    "VALUES","SELECT","UPDATE","INSERT","DELETE","MERGE",
    "USING","FROM","JOIN","INTO","GROUP","ORDER","BY",
    "HAVING","TABLE","OVERWRITE","POSITION","SUBSTRING",
    "CAST","TRIM","COUNT","SUM","MAX","MIN","AVG","SESSION"
}

ONLY_FROM_DUAL_PATTERN = re.compile(
    r"^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$",
    re.IGNORECASE | re.DOTALL
)

TEMP_CREATE_PAT = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY|TEMP)\s+(?:TABLE|VIEW)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(;]+)",
    re.IGNORECASE
)

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

END_IF_PATTERN = re.compile(r"^\s*END\s+IF\b", re.IGNORECASE)
INNER_DML_RE   = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|REPLACE|ALTER)\b",
    re.IGNORECASE
)

def preprocess(content):
    content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith("#")
    )
    content = "\n".join(
        line for line in content.splitlines()
        if not re.match(r"(?i)^\s*DBMS_OUTPUT", line)
    )
    content = "\n".join(
        line for line in content.splitlines()
        if not (line.strip().startswith("/*") and line.strip().endswith("*/"))
    )
    pattern = re.compile(
        r"""
        ('(?:[^']|'')*') |
        ("(?:[^"]|"")*") |
        (--[^\n]*$)       |
        (/\*.*?\*/)
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )
    def replacer(m):
        if m.group(1) or m.group(2):
            return m.group(0)
        return ""
    return pattern.sub(replacer, content)

def extract_execute_immediate(content):
    results = []
    pattern = re.compile(
        r"\bEXECUTE\s+IMMEDIATE\s+'(.*?)'",
        re.IGNORECASE | re.DOTALL
    )
    for m in pattern.finditer(content):
        inner = m.group(1).strip()
        if inner:
            results.append(inner)
    return results

def extract_queries_from_text(raw):
    queries_with_offset = []
    content     = preprocess(raw)
    ei_queries  = extract_execute_immediate(content)

    masked = re.sub(
        r"\bEXECUTE\s+IMMEDIATE\s+'.*?'",
        "EXECUTE_IMMEDIATE_MASKED",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    pos    = 0
    length = len(masked)
    last_orig_idx = 0
    orig_lines = raw.splitlines()

    while pos < length:
        match = MAIN_QUERY_START.search(masked, pos)
        if not match:
            break
        keyword = match.group(1).upper()
        start   = match.start()

        if keyword.startswith("END"):
            line_start = masked.rfind("\n", 0, start) + 1
            line_end   = masked.find("\n", start)
            if line_end == -1:
                line_end = length
            if END_IF_PATTERN.match(masked[line_start:line_end]):
                pos = line_end
                continue

        end    = start
        depth  = 0
        in_str = False
        q_char = None
        while end < length:
            ch = masked[end]
            if ch in ("'", '"'):
                if not in_str:
                    in_str = True
                    q_char = ch
                elif q_char == ch:
                    in_str = False
            elif not in_str:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(depth - 1, 0)
                elif ch == ";" and depth == 0:
                    end += 1
                    break
            end += 1

        query = masked[start:end].strip()
        if query:
            if ";" not in query:
                pos = end
                continue
            lower_q = query.lower()
            if any(p.lower() in lower_q for p in EXCLUDE_PATTERNS):
                pos = end
                continue
            if ONLY_FROM_DUAL_PATTERN.match(query):
                pos = end
                continue
            if keyword.upper().startswith("ALTER") and \
               not re.match(r"ALTER\s+(TABLE|VIEW)\b", query, re.IGNORECASE):
                pos = end
                continue

            # 파일 전체 기준 쿼리 시작 라인번호 산출
            start_line_no = 1
            first_query_line = query.splitlines()[0].strip()
            if first_query_line:
                for idx in range(last_orig_idx, len(orig_lines)):
                    if first_query_line in orig_lines[idx]:
                        start_line_no = idx + 1
                        last_orig_idx = idx
                        break

            queries_with_offset.append({
                "query_text": raw[start:end].strip(),
                "query_text_clean": query,
                "start_line_no": start_line_no
            })
        pos = end

    # EXECUTE IMMEDIATE 쿼리 (라인번호 특정 불가 → 1)
    for ei_q in ei_queries:
        queries_with_offset.append({
            "query_text": ei_q,
            "query_text_clean": ei_q,
            "start_line_no": 1
        })

    return queries_with_offset

def open_and_extract_queries(source_file_path):
    try:
        with codecs.open(source_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        orig_lines = content.splitlines()
        queries = extract_queries_from_text(content)
        return queries, None, orig_lines, content
    except Exception as e:
        return [], str(e), [], ""

def strip_comments(line):
    line = re.sub(r"/\*.*?\*/", "", line)
    line = re.split(r"--|#", line)[0]
    return line

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
# Sql v12 테이블 및 컬럼 정밀 파싱 함수군
# ============================================================
def clean_table(name):
    if not name:
        return None
    name  = name.strip()
    name  = re.split(r"\s+", name)[0]
    name  = name.rstrip(";,").replace("(", "").replace(")", "")
    upper = name.upper()
    if (not name
            or upper in RESERVED_WORDS
            or upper == "DUAL"
            or name.isdigit()
            or re.match(r"^\d", name)):
        return None
    return name

def strip_inline_comments(sql):
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql

def remove_string_literals(sql):
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r'"[^"]*"', '""', sql)
    return sql

def extract_paren_content(sql, start):
    depth = 0
    i     = start
    while i < len(sql):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1:i], i
        i += 1
    return sql[start + 1:], len(sql) - 1

def strip_select_columns(sql):
    result = []
    i      = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r"\bSELECT\b", sql_up[i:], re.IGNORECASE)
        if not m:
            result.append(sql[i:])
            break
        sel_pos = i + m.start()
        result.append(sql[i:sel_pos])
        result.append("SELECT ")
        j          = sel_pos + len("SELECT")
        depth      = 0
        found_from = False
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    break
            elif depth == 0:
                if re.match(r"\bFROM\b", sql_up[j:], re.IGNORECASE):
                    result.append("__COLS__ ")
                    i          = j
                    found_from = True
                    break
                if ch == ";":
                    result.append(sql[j:j + 1])
                    i          = j + 1
                    found_from = True
                    break
            j += 1
        if not found_from:
            result.append(sql[j:])
            break
    return "".join(result)

def strip_update_set(sql):
    result = []
    i      = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r"\bSET\b", sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        set_pos = i + m.start()
        result.append(sql[i:set_pos])
        result.append("SET ")
        j     = set_pos + len("SET")
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bWHEN\b", up)
                        or re.match(r"\bON\b", up) or re.match(r"\bFROM\b", up)
                        or ch == ";"):
                    break
            j += 1
        result.append("__SET__ ")
        i = j
    return "".join(result)

def strip_insert_col_list(sql):
    pattern = re.compile(
        r"(INSERT\s+(?:OVERWRITE\s+)?(?:TABLE\s+)?[\w${}.\-]+)"
        r"(\s*\([^)]*\))"
        r"(\s*(?:WITH|SELECT|VALUES)\b)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(r"\1 __INSERT_COLS__\3", sql)

def strip_function_args(sql):
    result = []
    i      = 0
    length = len(sql)
    sql_up = sql.upper()
    SKIP = {
        "FROM","JOIN","USING","WITH","ON","AS",
        "SELECT","WHERE","HAVING","SET",
        "INSERT","UPDATE","DELETE","MERGE",
        "CREATE","TABLE","VIEW","INTO",
        "WHEN","THEN","ELSE","AND","OR","NOT",
        "EXISTS","IN","ANY","ALL","CASE"
    }
    while i < length:
        m = re.search(r"(\b\w+)\s*\(", sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        fn_start    = i + m.start()
        fn_name     = m.group(1).upper()
        paren_start = i + m.end() - 1
        if fn_name in SKIP:
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        if fn_start > 0 and sql[fn_start - 1] in (".", "}", "$"):
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        result.append(sql[i:fn_start + len(m.group(1))])
        inner, end_pos = extract_paren_content(sql, paren_start)
        result.append("(__FUNC_ARGS__)")
        i = end_pos + 1
    return "".join(result)

def _extract_sources_from_set_subqueries(sql):
    sources = set()
    sql_up  = sql.upper()
    length  = len(sql)
    for set_m in re.finditer(r"\bSET\b", sql_up):
        j     = set_m.end()
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
                if depth == 1:
                    inner, end_pos = extract_paren_content(sql, j)
                    inner_up = inner.upper()
                    if re.search(r"\bSELECT\b", inner_up) and re.search(r"\bFROM\b", inner_up):
                        sources.update(extract_sources_recursive(inner))
                    j     = end_pos + 1
                    depth = 0
                    continue
                else:
                    j += 1
                    continue
            elif ch == ")":
                depth = max(depth - 1, 0)
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bFROM\b", up)
                        or re.match(r"\bWHEN\b", up) or ch == ";"):
                    break
            j += 1
    return sources

def extract_sources_recursive(query):
    sources = set()
    query   = strip_inline_comments(query)
    q       = remove_string_literals(query)
    q       = strip_select_columns(q)
    sources.update(_extract_sources_from_set_subqueries(q))
    q       = strip_update_set(q)
    q       = strip_insert_col_list(q)
    q       = strip_function_args(q)

    length     = len(q)
    kw_pattern = re.compile(r"\b(FROM|JOIN|USING)\b", re.IGNORECASE)
    CLAUSE_END = {
        "WHERE","ON","WHEN","SET","HAVING","GROUP","ORDER",
        "UNION","INTERSECT","EXCEPT","LIMIT","SELECT",
        "INSERT","UPDATE","DELETE","MERGE","WITH",
        "INNER","LEFT","RIGHT","FULL","CROSS",
        "JOIN","FROM","USING"
    }

    for kw_m in kw_pattern.finditer(q):
        j = kw_m.end()
        while j < length and q[j] in " \t\n\r":
            j += 1
        if j >= length:
            continue

        if q[j] == "(":
            inner, end_pos = extract_paren_content(q, j)
            sources.update(extract_sources_recursive(inner))
            j = end_pos + 1
            alias_m = re.match(r"[\s]+(\w+)", q[j:])
            if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                j += alias_m.end()
            while j < length and q[j] in " \t\n\r":
                j += 1
            if j >= length or q[j] != ",":
                continue
            j += 1

        while j < length:
            while j < length and q[j] in " \t\n\r":
                j += 1
            if j >= length or q[j] in (";", ")"):
                break
            if q[j] == "(":
                inner, end_pos = extract_paren_content(q, j)
                sources.update(extract_sources_recursive(inner))
                j = end_pos + 1
                alias_m = re.match(r"[\s]+(\w+)", q[j:])
                if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                    j += alias_m.end()
            else:
                tok_m = re.match(r"([^\s,;()\n]+)", q[j:])
                if not tok_m:
                    break
                token    = tok_m.group(1)
                token_up = token.upper().rstrip(",;")
                if token_up in CLAUSE_END:
                    break
                tbl = clean_table(token)
                if tbl:
                    sources.add(tbl)
                j += tok_m.end()
                alias_m = re.match(r"[\s]+([^\s,;()\n]+)", q[j:])
                if alias_m:
                    alias_word = alias_m.group(1).upper()
                    if alias_word not in CLAUSE_END and not alias_word.startswith(","):
                        j += alias_m.end()

            while j < length and q[j] in " \t\n\r":
                j += 1
            if j < length and q[j] == ",":
                j += 1
            else:
                break

    return sources

def extract_target_tables(query):
    targets  = set()
    patterns = [
        r"\bINSERT\s+OVERWRITE\s+TABLE\s+([^\s(]+)",
        r"\bINSERT\s+OVERWRITE\s+(?!TABLE\b)([^\s(]+)",
        r"\bINSERT\s+INTO\s+TABLE\s+([^\s(]+)",
        r"\bINSERT\s+INTO\s+(?!TABLE\b)([^\s(]+)",
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?"
        r"(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)",
        r"(?<![_\w])\bUPDATE\s+([^\s(]+)",
        r"\bDELETE\s+FROM\s+([^\s(]+)",
        r"\bMERGE\s+INTO\s+([^\s(]+)",
        r"\bMERGE\s+(?!INTO\b)([^\s(]+)",
        r"\bALTER\s+TABLE\s+([^\s(]+)",
        r"\bTRUNCATE\s+TABLE\s+([^\s(]+)",
        r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([^\s;]+)",
        r"\bDROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?([^\s;]+)",
    ]
    POST_KW = {
        "PARTITION","CLUSTER","STORED","LOCATION","ROW","FORMAT",
        "FIELDS","LINES","TERMINATED","WITH","SELECT","AS","SET",
        "WHERE","VALUES","ON","USING","IF"
    }
    for pat in patterns:
        for m in re.finditer(pat, query, re.IGNORECASE):
            raw = m.group(1).strip().rstrip(";,")
            if not raw or raw.upper() in POST_KW:
                continue
            tbl = clean_table(raw)
            if tbl:
                targets.add(tbl)
    return targets

# ============================================================
# 결과 테이블 동적 구성 및 DDL
# ============================================================
def setup_result_table(mysql_conf, ref_table, out_table_name):
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    out_schema = ref_schema if ref_schema else mysql_conf.get("database")
    fq_out_table = make_fq(out_schema, out_table_name)
    
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        
        # 'DROP TABLE' 대신 'CREATE TABLE IF NOT EXISTS'를 사용하여 mid 기준 삭제/누적 처리 지원
        ddl = """
        CREATE TABLE IF NOT EXISTS %s (
          `id_auto`            BIGINT        NOT NULL AUTO_INCREMENT,
          `id`                 VARCHAR(200)  NULL COMMENT '검색기준소스테이블 ID',
          `mid`                VARCHAR(200)  NULL COMMENT '검색기준소스테이블 MID',
          `source_file`        VARCHAR(500)  NULL COMMENT '검색기준소스테이블 SOURCE_FILE',
          `tbl_name`           VARCHAR(500)  NULL COMMENT '검색된 테이블명',
          `column_name`        VARCHAR(500)  NULL,
          `tobe_enc_key`       VARCHAR(200)  NULL,
          `conv_tobe_enc_key`   VARCHAR(200)  NULL COMMENT 'Converted tobe_enc_key (e.g. e1)',
          `line_number`        INT           NULL COMMENT '소스전체기준 라인',
          `vscode_open_cmd`    VARCHAR(1000) NULL COMMENT 'vscode 이동 실행 명령어',
          `matched_line`       TEXT          NULL COMMENT '매칭된 행 내용',
          `query_text`         LONGTEXT      NULL COMMENT '쿼리문 원본',
          `run_id`             VARCHAR(30)   NULL,
          `op_dtm`             DATETIME      NULL,
          PRIMARY KEY (`id_auto`),
          KEY `idx_run_id` (`run_id`),
          KEY `idx_col_name` (`column_name`(191)),
          KEY `idx_tbl_name` (`tbl_name`(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='3차 암호화 대상 검출 결과';
        """ % fq_out_table
        
        cursor.execute(ddl)
        conn.commit()
        
        col_names = [
            "id", "mid", "source_file", "tbl_name", "column_name", "tobe_enc_key", "conv_tobe_enc_key",
            "line_number", "vscode_open_cmd", "matched_line", "query_text", "run_id", "op_dtm"
        ]
        return col_names, fq_out_table, None
    except Exception as e:
        return [], "", "결과 테이블 생성 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

def insert_results_to_db(mysql_conf, fq_out_table, col_names, results, mids_to_delete):
    if not results and not mids_to_delete:
        return 0, None
    
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        
        # 1. 있으면 mid 기준 삭제 처리
        if mids_to_delete:
            for mid in mids_to_delete:
                if mid:
                    cursor.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_out_table, (mid,))
            conn.commit()
            
        # 2. 신규 적재 진행
        if results:
            cols_str = ", ".join(["`%s`" % col for col in col_names])
            placeholders = ", ".join(["%s"] * len(col_names))
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (fq_out_table, cols_str, placeholders)
            
            batch = []
            for r in results:
                row_data = []
                for col in col_names:
                    row_data.append(r.get(col, None))
                batch.append(row_data)
                
            cursor.executemany(sql, batch)
            conn.commit()
            return len(batch), None
        return 0, None
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return 0, "DB 적재 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

# ============================================================
# CSV 저장 모듈 (Python 2.7.5 대응 수동 인코딩 방식)
# ============================================================
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

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="3차 암호화 대상 검출 프로그램 (v09_3cha)")
    parser.add_argument("ref_table", help="검색기준테이블 (schema.table)")
    parser.add_argument("src_table", help="검색기준소스테이블 (schema.table)")
    parser.add_argument("--where", choices=["old", "new", "all"], default="all", help="검색기준테이블 조회 필터")
    parser.add_argument("--db", action="store_true", help="DB 적재 활성화 여부")
    parser.add_argument("--conf", help="mysql.conf 파일 경로", default=None)

    args = parser.parse_args()

    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    out_dir = os.path.join(script_dir, "out")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    print("=" * 80)
    print(" [3차 암호화 대상 검출 분석 시작]")
    print("=" * 80)
    print("  검색 기준 테이블   : %s" % args.ref_table)
    print("  검색 기준 소스테이블: %s" % args.src_table)
    print("  WHERE 필터 조건     : %s" % args.where)
    print("  DB 적재 여부        : %s" % ("YES (--db)" if args.db else "NO"))
    print("-" * 80)

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버(pymysql 또는 mysql-connector-python)가 설치되어 있지 않습니다.")
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

    # 1. 검색기준테이블 조회
    print("[INFO] 검색기준테이블 조회 중: %s ..." % args.ref_table)
    ref_rows, ref_schema, ref_tbl_only, db_err = load_ref_rows_from_db(mysql_conf, args.ref_table, args.where)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[WARN] 검색기준테이블에서 조회된 데이터가 없습니다. (빈 매칭 데이터로 처리 진행)")
        ref_rows = []
    else:
        print("[INFO] 조회 완료: %d 행" % len(ref_rows))

    # column_name 중복 제거하여 검색 속도 향상 및 중복 결과 방지 (칼럼 단독 매칭용)
    unique_ref_rows = []
    seen_cols = set()
    col_to_row = {}
    
    # 테이블+칼럼 동시 매칭용 쌍 데이터 구성
    tbl_col_pairs = []

    for r in ref_rows:
        col_name = r.get("column_name", "").strip()
        tbl_name = r.get("tbl_name", "").strip()
        if not col_name:
            continue
        c_lower = col_name.lower()
        
        if c_lower not in seen_cols:
            seen_cols.add(c_lower)
            col_to_row[c_lower] = r
            unique_ref_rows.append(r)
            
        if tbl_name:
            tbl_col_pairs.append({
                "tbl_name": tbl_name,
                "column_name": col_name,
                "ref_row": r
            })
            
    print("[INFO] 중복 제거 후 검색기준 칼럼 수: %d 개" % len(unique_ref_rows))
    print("[INFO] 테이블+칼럼 매칭 기준 쌍 수: %d 개" % len(tbl_col_pairs))

    # 2. 소스 파일 목록 가져오기
    print("[INFO] 검색기준소스테이블에서 local_file 목록 로딩 중: %s ..." % args.src_table)
    files_info, src_err = load_source_files_from_db(mysql_conf, args.src_table)
    if src_err:
        print("[ERROR] %s" % src_err)
        sys.exit(1)
    print("[INFO] 로딩된 소스 파일 수: %d 개" % len(files_info))
    print("-" * 80)

    # 3. 정규식 컴파일
    compiled_col_patterns = {}
    for col_lower in col_to_row:
        compiled_col_patterns[col_lower] = re.compile(r"\b%s\b" % re.escape(col_lower), re.IGNORECASE)

    # 4. 소스 파일 매칭 탐색 루프
    included_results = []       # 칼럼 단독 매칭 결과
    tbl_col_results = []        # 테이블+칼럼 매칭 결과
    
    seen_matches = set()
    seen_tbl_col_matches = set()
    
    total_files = len(files_info)
    matched_file_count_col = 0
    matched_file_count_tbl_col = 0
    total_matches_col = 0
    total_matches_tbl_col = 0
    
    mid_print_buffer_col = []
    mid_print_buffer_tbl_col = []
    
    screen_match_print_count_col = 0
    screen_match_print_count_tbl_col = 0
    
    # mid 수집
    mids_in_batch = set()
    for f_info in files_info:
        if f_info.get("mid"):
            mids_in_batch.add(f_info["mid"])

    print("[INFO] 소스 파일 매칭 검색을 시작합니다...")
    for idx, f_info in enumerate(files_info, 1):
        filepath = f_info["local_file"]
        filepath_abs = os.path.abspath(filepath)
        if not os.path.isfile(filepath_abs):
            print("[%d/%d] [WARN] 파일이 존재하지 않습니다 (Skip): %s" % (idx, total_files, filepath))
            continue

        queries, open_err, orig_lines, raw_content = open_and_extract_queries(filepath_abs)
        if open_err:
            print("[%d/%d] [WARN] 파일 오픈 실패 (Skip): %s, 에러: %s" % (idx, total_files, filepath, open_err))
            continue

        file_start_msg = "[진행] ID: %s, local_file: %s" % (f_info["id"], filepath)
        print(file_start_msg)
        mid_print_buffer_col.append(file_start_msg)
        mid_print_buffer_tbl_col.append(file_start_msg)

        if not queries and raw_content.strip():
            queries = [{"query_text": raw_content, "query_text_clean": raw_content, "start_line_no": 1}]

        file_matched_col = False
        file_matched_tbl_col = False

        for q_item in queries:
            raw_query = q_item["query_text"]
            clean_query = q_item.get("query_text_clean", raw_query)
            clean_query_upper = clean_query.upper()
            line_no_offset = q_item["start_line_no"]
            query_lines = raw_query.splitlines()

            # ───────────────────────────────────────────────────
            # A) 기존 칼럼 단독 매칭 처리
            # ───────────────────────────────────────────────────
            for col_lower, rx in compiled_col_patterns.items():
                if rx.search(clean_query_upper):
                    matched_lines_found = []
                    if line_no_offset is not None and orig_lines:
                        start_idx = line_no_offset - 1
                        end_idx = min(start_idx + len(query_lines) + 10, len(orig_lines))
                        for l_idx in range(start_idx, end_idx):
                            if rx.search(orig_lines[l_idx]):
                                matched_lines_found.append({
                                    "line_number": l_idx + 1,
                                    "matched_line": orig_lines[l_idx]
                                })
                    else:
                        for l_idx, line in enumerate(query_lines):
                            if rx.search(line):
                                matched_lines_found.append({
                                    "line_number": l_idx + 1,
                                    "matched_line": line
                                })

                    for item in matched_lines_found:
                        l_num = item["line_number"]
                        l_val = item["matched_line"]
                        
                        match_key = (filepath_abs, l_num, col_lower)
                        if match_key in seen_matches:
                            continue
                        seen_matches.add(match_key)

                        clean_l_val = strip_comments(l_val)
                        if not rx.search(clean_l_val):
                            continue

                        orig_col_name = col_to_row[col_lower]["column_name"]
                        orig_tbl_name = col_to_row[col_lower].get("tbl_name", "")
                        vscode_cmd = "code -g %s:%s" % (filepath_abs, l_num)
                        file_matched_col = True
                        total_matches_col += 1

                        ref_row = col_to_row[col_lower]
                        tobe_enc_key = ref_row.get("tobe_enc_key", "")
                        conv_key = convert_key_to_code(tobe_enc_key)

                        result_row = {
                            "id": f_info["id"],
                            "mid": f_info["mid"],
                            "source_file": f_info.get("source_file", ""),
                            "tbl_name": orig_tbl_name,
                            "column_name": orig_col_name,
                            "tobe_enc_key": tobe_enc_key,
                            "conv_tobe_enc_key": conv_key,
                            "line_number": l_num,
                            "vscode_open_cmd": vscode_cmd,
                            "matched_line": l_val.strip(),
                            "query_text": raw_query,
                            "run_id": run_id,
                            "op_dtm": op_dtm
                        }
                        included_results.append(result_row)
                        
                        match_str = "[매칭] %s %s: %s" % (vscode_cmd, orig_tbl_name, orig_col_name)
                        content_str = "[내용] %s" % l_val.strip()
                        
                        if screen_match_print_count_col < 10:
                            print(match_str)
                            print(content_str)
                            print("-" * 80)
                            screen_match_print_count_col += 1
                        elif screen_match_print_count_col == 10:
                            print("[INFO] 상위 10개 칼럼 단독 매칭 결과만 화면에 출력되었습니다. 전체 결과는 파일 및 DB를 확인하세요.")
                            screen_match_print_count_col += 1
                        
                        mid_print_buffer_col.append(match_str)
                        mid_print_buffer_col.append(content_str)
                        mid_print_buffer_col.append("-" * 80)

            # ───────────────────────────────────────────────────
            # B) 신규 테이블+칼럼 동시 매칭 처리
            # ───────────────────────────────────────────────────
            # 쿼리에서 소스타겟 테이블 리스트(리니지 정보)를 먼저 추출
            sources = extract_sources_recursive(clean_query)
            targets = extract_target_tables(clean_query)
            
            src_upper = set(s.upper() for s in sources if s)
            tgt_upper = set(t.upper() for t in targets if t)
            
            for pair in tbl_col_pairs:
                tbl = pair["tbl_name"]
                col = pair["column_name"]
                ref_row = pair["ref_row"]
                
                tbl_up = tbl.upper()
                col_up = col.upper()
                
                # 테이블 매칭 체크 (O(1) 해시 셋 비교)
                if tbl_up in tgt_upper or tbl_up in src_upper:
                    col_rx = compiled_col_patterns.get(col.lower())
                    if col_rx and col_rx.search(clean_query_upper):
                        matched_lines_found = []
                        if line_no_offset is not None and orig_lines:
                            start_idx = line_no_offset - 1
                            end_idx = min(start_idx + len(query_lines) + 10, len(orig_lines))
                            for l_idx in range(start_idx, end_idx):
                                if col_rx.search(orig_lines[l_idx]):
                                    matched_lines_found.append({
                                        "line_number": l_idx + 1,
                                        "matched_line": orig_lines[l_idx]
                                    })
                        else:
                            for l_idx, line in enumerate(query_lines):
                                if col_rx.search(line):
                                    matched_lines_found.append({
                                        "line_number": l_idx + 1,
                                        "matched_line": line
                                    })

                        for item in matched_lines_found:
                            l_num = item["line_number"]
                            l_val = item["matched_line"]
                            
                            match_key = (filepath_abs, l_num, tbl_up, col_up)
                            if match_key in seen_tbl_col_matches:
                                continue
                            seen_tbl_col_matches.add(match_key)

                            clean_l_val = strip_comments(l_val)
                            if not col_rx.search(clean_l_val):
                                continue

                            vscode_cmd = "code -g %s:%s" % (filepath_abs, l_num)
                            file_matched_tbl_col = True
                            total_matches_tbl_col += 1

                            tobe_enc_key = ref_row.get("tobe_enc_key", "")
                            conv_key = convert_key_to_code(tobe_enc_key)

                            result_row = {
                                "id": f_info["id"],
                                "mid": f_info["mid"],
                                "source_file": f_info.get("source_file", ""),
                                "tbl_name": tbl,
                                "column_name": col,
                                "tobe_enc_key": tobe_enc_key,
                                "conv_tobe_enc_key": conv_key,
                                "line_number": l_num,
                                "vscode_open_cmd": vscode_cmd,
                                "matched_line": l_val.strip(),
                                "query_text": raw_query,
                                "run_id": run_id,
                                "op_dtm": op_dtm
                            }
                            tbl_col_results.append(result_row)
                            
                            match_str = "[매칭(T+C)] %s %s: %s" % (vscode_cmd, tbl, col)
                            content_str = "[내용] %s" % l_val.strip()
                            
                            if screen_match_print_count_tbl_col < 10:
                                print(match_str)
                                print(content_str)
                                print("-" * 80)
                                screen_match_print_count_tbl_col += 1
                            elif screen_match_print_count_tbl_col == 10:
                                print("[INFO] 상위 10개 테이블+칼럼 매칭 결과만 화면에 출력되었습니다. 전체 결과는 파일 및 DB를 확인하세요.")
                                screen_match_print_count_tbl_col += 1
                            
                            mid_print_buffer_tbl_col.append(match_str)
                            mid_print_buffer_tbl_col.append(content_str)
                            mid_print_buffer_tbl_col.append("-" * 80)

        # C) 파일 매칭 통계
        if file_matched_col:
            matched_file_count_col += 1
        else:
            vscode_cmd = "code -g %s:1" % filepath_abs
            result_row = {
                "id": f_info["id"],
                "mid": f_info["mid"],
                "source_file": f_info.get("source_file", ""),
                "tbl_name": "",
                "column_name": "",
                "tobe_enc_key": "",
                "conv_tobe_enc_key": "",
                "line_number": 1,
                "vscode_open_cmd": vscode_cmd,
                "matched_line": "",
                "query_text": "",
                "run_id": run_id,
                "op_dtm": op_dtm
            }
            included_results.append(result_row)

        if file_matched_tbl_col:
            matched_file_count_tbl_col += 1
        else:
            vscode_cmd = "code -g %s:1" % filepath_abs
            result_row = {
                "id": f_info["id"],
                "mid": f_info["mid"],
                "source_file": f_info.get("source_file", ""),
                "tbl_name": "",
                "column_name": "",
                "tobe_enc_key": "",
                "conv_tobe_enc_key": "",
                "line_number": 1,
                "vscode_open_cmd": vscode_cmd,
                "matched_line": "",
                "query_text": "",
                "run_id": run_id,
                "op_dtm": op_dtm
            }
            tbl_col_results.append(result_row)

    print("-" * 80)
    print("[INFO] 매칭 탐색 종료")
    print("  - 전체 조사 파일 수: %d 개" % total_files)
    print("  - [칼럼 매칭] 매칭 발견 파일 수: %d 개, 추출 건수: %d 건" % (matched_file_count_col, total_matches_col))
    print("  - [테이블+칼럼 매칭] 매칭 발견 파일 수: %d 개, 추출 건수: %d 건" % (matched_file_count_tbl_col, total_matches_tbl_col))
    print("-" * 80)

    # 5. 결과 테이블 구성
    _, src_tbl_only = split_schema_table(args.src_table)
    
    # 5-1. 칼럼 단독 매칭 테이블 설정
    out_table_col = "%s_work" % src_tbl_only
    print("[INFO] 칼럼 단독 매칭 결과 테이블 구성 중: %s ..." % out_table_col)
    cols_col, fq_out_col, setup_err_col = setup_result_table(mysql_conf, args.ref_table, out_table_col)
    if setup_err_col:
        print("[ERROR] %s" % setup_err_col)
        sys.exit(1)
        
    # 5-2. 테이블+칼럼 매칭 테이블 설정
    out_table_tbl_col = "%s_work_tbl_col" % src_tbl_only
    print("[INFO] 테이블+칼럼 매칭 결과 테이블 구성 중: %s ..." % out_table_tbl_col)
    cols_tbl_col, fq_out_tbl_col, setup_err_tbl_col = setup_result_table(mysql_conf, args.ref_table, out_table_tbl_col)
    if setup_err_tbl_col:
        print("[ERROR] %s" % setup_err_tbl_col)
        sys.exit(1)
        
    print("[INFO] 결과 테이블 레이아웃 구성 완료.")

    # 6. CSV 파일 및 화면출력 파일 저장
    # 6-1. 칼럼 단독 매칭 결과 저장
    csv_filename_col = "%s.csv" % out_table_col
    csv_filepath_col = os.path.join(out_dir, csv_filename_col)
    print("[INFO] 칼럼 매칭 CSV 저장 처리 중: %s" % csv_filepath_col)
    save_csv(included_results, csv_filepath_col, cols_col, op_dtm)
    
    print_filename_col = "%s_print.txt" % out_table_col
    print_filepath_col = os.path.join(out_dir, print_filename_col)
    try:
        with open(print_filepath_col, "w") as pf:
            pf.write("\n".join(mid_print_buffer_col) + "\n")
    except Exception as e:
        print("[WARN] 칼럼 매칭 화면 출력 파일 저장 에러: %s" % str(e))

    # 6-2. 테이블+칼럼 매칭 결과 저장
    csv_filename_tbl_col = "%s.csv" % out_table_tbl_col
    csv_filepath_tbl_col = os.path.join(out_dir, csv_filename_tbl_col)
    print("[INFO] 테이블+칼럼 매칭 CSV 저장 처리 중: %s" % csv_filepath_tbl_col)
    save_csv(tbl_col_results, csv_filepath_tbl_col, cols_tbl_col, op_dtm)
    
    print_filename_tbl_col = "%s_print.txt" % out_table_tbl_col
    print_filepath_tbl_col = os.path.join(out_dir, print_filename_tbl_col)
    try:
        with open(print_filepath_tbl_col, "w") as pf:
            pf.write("\n".join(mid_print_buffer_tbl_col) + "\n")
    except Exception as e:
        print("[WARN] 테이블+칼럼 매칭 화면 출력 파일 저장 에러: %s" % str(e))
        
    print("[INFO] 파일 저장 완료.")

    # 7. DB 테이블 적재 (DELETE & INSERT mid 기준)
    if args.db:
        print("[INFO] DB 적재를 진행합니다...")
        
        # 7-1. 칼럼 단독 매칭 적재
        print("[INFO] 칼럼 단독 매칭 데이터 적재 중: %s" % fq_out_col)
        loaded_count_col, db_err_col = insert_results_to_db(mysql_conf, fq_out_col, cols_col, included_results, list(mids_in_batch))
        if db_err_col:
            print("[ERROR] %s" % db_err_col)
            sys.exit(1)
        print("[INFO] 칼럼 단독 매칭 DB 적재 완료: %d 행" % loaded_count_col)

        # 7-2. 테이블+칼럼 매칭 적재
        print("[INFO] 테이블+칼럼 매칭 데이터 적재 중: %s" % fq_out_tbl_col)
        loaded_count_tbl_col, db_err_tbl_col = insert_results_to_db(mysql_conf, fq_out_tbl_col, cols_tbl_col, tbl_col_results, list(mids_in_batch))
        if db_err_tbl_col:
            print("[ERROR] %s" % db_err_tbl_col)
            sys.exit(1)
        print("[INFO] 테이블+칼럼 매칭 DB 적재 완료: %d 행" % loaded_count_tbl_col)
    else:
        print("[INFO] --db 옵션이 지정되지 않아 DB 적재는 생략되었습니다.")

    print("=" * 80)
    print(" [작업이 정상적으로 종료되었습니다]")
    print("=" * 80)

if __name__ == "__main__":
    main()
