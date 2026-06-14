#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v01.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001_local_04 (2026-06-14)
#   [수정1] extract_queries_from_file 내부 try-except 예외 처리 보강 (안정성 확보)
#   [수정2] 각 쿼리 단위로 tbl_name 존재 여부와 cols 칼럼명 포함 여부를 동시 만족하는 행만 추출하도록 구조 정밀화
#
# ■ 프로그램 설명
# ─────────────────────────────────────────────────────────────
# 1) 실행 시 파라미터: 스키마.검색기준테이블, [--db], [--conf]
# 2) 서버 MySQL 에서 <검색기준테이블> 전체 데이터 조회
# 3) 조회된 각 행의 source_file 경로를 기반으로 개별 소스 파일 직접 오픈 (예외 처리 강화)
# 4) 각 소스 파일에서 쿼리 단위로 추출 (주석 제거 포함)
# 5) 매칭 조건 (AND 조건):
#    조건1) 쿼리의 소스 또는 타겟 테이블 중 tbl_name 과 일치하는 항목 존재 (대소문자 무시)
#    조건2) cols 에서 파싱된 각 칼럼명이 해당 쿼리 텍스트에 포함 (대소문자 무시, 정규식/in 보완)
# 6) 매칭 결과에 검색기준테이블의 원본 행 전체 칼럼값 포함하여 CSV 생성
# 7) [--db] 옵션 지정 시 검색기준테이블과 동일 스키마에 결과 테이블 적재
# ===============================================================

import os
import re
import sys
import csv
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 / 디렉토리 경로 설정
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR   = os.path.dirname(os.path.abspath(sys.argv[0]))
OUT_DIR      = os.path.join(SCRIPT_DIR, "out")
IN_DIR       = os.path.join(SCRIPT_DIR, "in")

MYSQL_CONF_FILE   = "mysql.conf"

# 검색기준테이블 고정 칼럼 목록
REF_TABLE_COLS = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 결과 CSV / DB 테이블 필드 순서
RESULT_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols", "enc_col_cnt", "ins_cnt", "sel_cnt",
    "base_directory", "src_file_name", "dir_file",
    "crud_type", "sql_type", "match_type",
    "matched_col_name", "matched_col_key",
    "line_number", "matched_line",
    "op_dtm",
]

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


def _mysql_connect(conf: dict):
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
        raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql 또는 mysql-connector-python")


def load_mysql_conf(explicit_path=None) -> tuple:
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), MYSQL_CONF_FILE)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        fallback = os.path.join(SCRIPT_DIR, MYSQL_CONF_FILE)
        if os.path.isfile(fallback):
            path = fallback
        else:
            return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path

    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)

    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."

    conf    = dict(cp["mysql"])
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
    return conf, None


def split_schema_table(full_table: str) -> tuple:
    parts = full_table.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", parts[0].strip()


def make_fq(schema: str, table: str) -> str:
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table


def parse_cols(cols_str: str) -> list:
    result = []
    if not cols_str or not cols_str.strip():
        return result
    for item in cols_str.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            col_name, col_key = item.split(":", 1)
            col_name = col_name.strip()
            col_key  = col_key.strip()
        else:
            col_name = item
            col_key  = ""
        if col_name:
            result.append({"col_name": col_name, "col_key": col_key})
    return result


def load_ref_rows_from_db(mysql_conf: dict, ref_table: str) -> tuple:
    rows      = []
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    fq_table  = make_fq(ref_schema, ref_tbl_only)

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
            return [], ref_schema, "테이블이 존재하지 않습니다: %s" % ref_table

        cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
        existing_cols = {row[0].lower() for row in cursor.fetchall()}

        select_parts = []
        for col in REF_TABLE_COLS:
            if col in existing_cols:
                select_parts.append("`%s`" % col)
            else:
                select_parts.append("NULL AS `%s`" % col)

        sql = "SELECT %s FROM %s ORDER BY tbl_name, no" % (", ".join(select_parts), fq_table)
        cursor.execute(sql)
        db_rows = cursor.fetchall()

        for db_row in db_rows:
            row_dict = {}
            for idx, col in enumerate(REF_TABLE_COLS):
                val = db_row[idx]
                row_dict[col] = str(val).strip() if val is not None else ""
            rows.append(row_dict)

        return rows, ref_schema, None

    except Exception as e:
        return [], ref_schema, "DB 조회 실패: %s" % str(e)
    finally:
        if cursor: try: cursor.close() \
                   except Exception: pass
        if conn: try: conn.close() \
                 except Exception: pass


_DDL_DROP_RESULT = "DROP TABLE IF EXISTS {table};"

_DDL_CREATE_RESULT = """
CREATE TABLE {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT    COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                   COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `db_name`          VARCHAR(200)  NULL                       COMMENT '기준테이블: DB명',
  `tbl_name`         VARCHAR(500)  NOT NULL                   COMMENT '기준테이블: 테이블명',
  `operation`        VARCHAR(50)   NULL                       COMMENT '기준테이블: 오퍼레이션',
  `no`               INT           NULL                       COMMENT '기준테이블: 순번',
  `source_file`      VARCHAR(500)  NULL                       COMMENT '기준테이블: 소스파일 경로',
  `process_yn`       VARCHAR(1)    NULL                       COMMENT '기준테이블: 처리여부',
  `process_desc`     VARCHAR(500)  NULL                       COMMENT '기준테이블: 처리설명',
  `cols`             VARCHAR(2000) NULL                       COMMENT '기준테이블: 칼럼목록',
  `enc_col_cnt`      INT           NULL                       COMMENT '기준테이블: 암호화 칼럼 수',
  `ins_cnt`          INT           NULL                       COMMENT '기준테이블: INSERT 건수',
  `sel_cnt`          INT           NULL                       COMMENT '기준테이블: SELECT 건수',
  `base_directory`   VARCHAR(500)  NOT NULL                   COMMENT '소스파일 디렉토리 경로',
  `src_file_name`    VARCHAR(500)  NOT NULL                   COMMENT '소스 파일명',
  `dir_file`         TEXT          NOT NULL                   COMMENT '소스파일 전체경로',
  `crud_type`        VARCHAR(1)    NULL                       COMMENT 'C/R/U/D',
  `sql_type`         VARCHAR(30)   NULL                       COMMENT 'INSERT/SELECT/UPDATE/...',
  `match_type`       VARCHAR(10)   NULL                       COMMENT 'SOURCE/TARGET (매칭된 위치)',
  `matched_col_name` VARCHAR(500)  NOT NULL                   COMMENT '매칭된 칼럼명',
  `matched_col_key`  VARCHAR(200)  NULL                       COMMENT '매칭된 칼럼 키값',
  `line_number`      INT           NULL                       COMMENT '소스파일 전체 기준 절대 행번호',
  `matched_line`     TEXT          NULL                       COMMENT '매칭된 라인 내용',
  `op_dtm`           DATETIME      NOT NULL                   COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`        (`run_id`),
  KEY `idx_tbl_name`      (`tbl_name`(191)),
  KEY `idx_src_file`      (`src_file_name`(191)),
  KEY `idx_matched_col`   (`matched_col_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='source_file 기반 매칭 결과';
"""

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt,
   base_directory, src_file_name, dir_file, crud_type, sql_type, match_type,
   matched_col_name, matched_col_key, line_number, matched_line, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def build_result_table(ref_table_name: str, ref_schema: str) -> tuple:
    ref_tbl_only = ref_table_name.split(".")[-1]
    table_only = "%s_%s_match" % (PROGRAM_NAME, ref_tbl_only)
    fq         = make_fq(ref_schema, table_only)
    return ref_schema, table_only, fq


def db_insert_result_all(result_buffer: list, run_id: str, op_dtm: str,
                         mysql_conf: dict, ref_table_name: str, ref_schema: str) -> tuple:
    _, _, fq_table = build_result_table(ref_table_name, ref_schema)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        cursor.execute(_DDL_DROP_RESULT.format(table=fq_table))
        conn.commit()
        cursor.execute(_DDL_CREATE_RESULT.format(table=fq_table))
        conn.commit()

        batch = []
        for r in result_buffer:
            def to_int(v):
                try: return int(v) if v not in (None, "") else None
                except Exception: return None

            batch.append((
                run_id, r["db_name"], r["tbl_name"], r["operation"], to_int(r["no"]), r["source_file"],
                r["process_yn"], r["process_desc"], r["cols"], to_int(r["enc_col_cnt"]), to_int(r["ins_cnt"]), to_int(r["sel_cnt"]),
                r["base_directory"], r["src_file_name"], r["dir_file"], r["crud_type"], r["sql_type"], r["match_type"],
                r["matched_col_name"], r["matched_col_key"], to_int(r["line_number"]), r["matched_line"], op_dtm,
            ))

        if batch:
            cursor.executemany(_SQL_INSERT_RESULT.format(table=fq_table), batch)
            conn.commit()

        return len(batch), None
    except Exception as e:
        if conn: try: conn.rollback() \
                 except Exception: pass
        return 0, str(e)
    finally:
        if cursor: try: cursor.close() \
                   except Exception: pass
        if conn: try: conn.close() \
                 except Exception: pass


def save_result_csv(result_buffer: list, ref_table_name: str, op_dtm: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    ref_tbl_only = ref_table_name.split(".")[-1]
    csv_file = "%s_%s_match.csv" % (PROGRAM_NAME, ref_tbl_only)
    csv_path = os.path.join(OUT_DIR, csv_file)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDNAMES)
        writer.writeheader()
        for r in result_buffer:
            row = dict(r)
            row["op_dtm"] = op_dtm
            writer.writerow(row)
    return csv_path


# ============================================================
# SQL 파싱 컴포넌트
# ============================================================
EXCLUDE_PATTERNS = ["insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)", "sidtest.ad1901_rgb_ac190212_svc"]
RESERVED_WORDS = {
    "SET","WHERE","AND","OR","ON","WHEN","THEN","ELSE","VALUES","SELECT","UPDATE","INSERT",
    "DELETE","MERGE","USING","FROM","JOIN","INTO","GROUP","ORDER","BY","HAVING","TABLE",
    "OVERWRITE","POSITION","SUBSTRING","CAST","TRIM","COUNT","SUM","MAX","MIN","AVG","SESSION"
}
ONLY_FROM_DUAL_PATTERN = re.compile(r"^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$", re.IGNORECASE | re.DOTALL)
MAIN_QUERY_START = re.compile(
    r"\b(CREATE\s+OR\s+REPLACE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|"
    r"CREATE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|CREATE\s+TABLE|CREATE\s+VIEW|"
    r"ALTER\s+TABLE|ALTER\s+VIEW|DROP\s+TABLE|DROP\s+VIEW|TRUNCATE\s+TABLE|REPLACE\s+VIEW|"
    r"MERGE\s+INTO|MERGE|UPSERT|INSERT|UPDATE|DELETE|SELECT|WITH|EXECUTE)\b", re.IGNORECASE
)
END_IF_PATTERN = re.compile(r"^\s*END\s+IF\b", re.IGNORECASE)
INNER_DML_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|REPLACE|ALTER)\b", re.IGNORECASE)


def preprocess(content: str) -> str:
    content = "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))
    content = "\n".join(line for line in content.splitlines() if not re.match(r"(?i)^\s*DBMS_OUTPUT", line))
    content = "\n".join(line for line in content.splitlines() if not (line.strip().startswith("/*") and line.strip().endswith("*/")))
    pattern = re.compile(r"('(?:[^']|'')*')|(\"(?:[^\"]|\"\")*\")|(--[^\n]*$)|(/\*.*?\*/)", re.MULTILINE | re.DOTALL | re.VERBOSE)
    return pattern.sub(lambda m: m.group(0) if (m.group(1) or m.group(2)) else "", content)


def extract_execute_immediate(content: str) -> list:
    return [m.group(1).strip() for m in re.finditer(r"\bEXECUTE\s+IMMEDIATE\s+'(.*?)'", content, re.IGNORECASE | re.DOTALL) if m.group(1).strip()]


def extract_queries_from_file(file_path: str) -> tuple:
    """
    [안정성 강화] 파일 입출력 및 파싱 구간 전체 예외 격리 처리
    """
    queries_with_offset = []
    total_lines = 0
    orig_lines = []
    
    if not os.path.isfile(file_path):
        return queries_with_offset, total_lines, orig_lines

    try:
        # 파일 인코딩 예외 처리 안전 기지화
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        
        orig_lines  = raw.splitlines()
        total_lines = len(orig_lines)
        content     = preprocess(raw)
        ei_queries  = extract_execute_immediate(content)

        masked = re.sub(r"\bEXECUTE\s+IMMEDIATE\s+'.*?'", "EXECUTE_IMMEDIATE_MASKED", content, flags=re.IGNORECASE | re.DOTALL)
        pos, length, last_orig_idx = 0, len(masked), 0

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

            query = masked[start:end].strip()
            if query and ";" in query:
                lower_q = query.lower()
                if any(p.lower() in lower_q for p in EXCLUDE_PATTERNS) or ONLY_FROM_DUAL_PATTERN.match(query):
                    pos = end; continue
                if keyword.upper().startswith("ALTER") and not re.match(r"ALTER\s+(TABLE|VIEW)\b", query, re.IGNORECASE):
                    pos = end; continue

                start_line_no = 1
                first_query_line = query.splitlines()[0].strip()
                if first_query_line:
                    for idx in range(last_orig_idx, len(orig_lines)):
                        if first_query_line in orig_lines[idx]:
                            start_line_no = idx + 1; last_orig_idx = idx; break

                queries_with_offset.append((query, query, start_line_no))
            pos = end

        for ei_q in ei_queries:
            queries_with_offset.append((ei_q, ei_q, None))
            
    except Exception as e:
        # 오류 발생 시 빈 상태를 리턴하여 메인 프로세스가 중단되지 않도록 보장
        print("[WARN] 파일 읽기/파싱 중 예외 발생 (건너뜀): %s -> %s" % (file_path, str(e)))
        
    return queries_with_offset, total_lines, orig_lines


def detect_real_sql_type(query: str) -> str:
    q = query.strip().upper().split()
    first = q[0] if q else "UNKNOWN"
    if first in ("DECLARE", "BEGIN"):
        m = INNER_DML_RE.search(query)
        return m.group(1).upper() if m else "UNKNOWN"
    if first == "WITH":
        qu = query.upper()
        for kw in ("INSERT","UPDATE","DELETE","MERGE"):
            if re.search(r"\b%s\b" % kw, qu): return kw
        return "SELECT"
    return first


def classify_crud_type(sql_type: str) -> str:
    u = sql_type.upper()
    if u in ("CREATE", "INSERT", "MERGE", "REPLACE", "UPSERT", "EXECUTE"): return "C"
    elif u == "SELECT": return "R"
    elif u in ("UPDATE", "ALTER"): return "U"
    elif u in ("DELETE", "DROP", "TRUNCATE"): return "D"
    return "R"


def clean_table(name: str):
    if not name: return None
    name = re.split(r"\s+", name.strip())[0].rstrip(";,").replace("(", "").replace(")", "")
    upper = name.upper()
    if not name or upper in RESERVED_WORDS or upper == "DUAL" or name.isdigit() or re.match(r"^\d", name): return None
    return name


def strip_inline_comments(sql: str) -> str:
    return re.sub(r"/\*.*?\*/", "", re.sub(r"--[^\n]*", "", sql), flags=re.DOTALL)

def remove_string_literals(sql: str) -> str:
    return re.sub(r'"[^"]*"', '""', re.sub(r"'[^']*'", "''", sql))

def extract_paren_content(sql: str, start: int) -> tuple:
    depth = 0
    for i in range(start, len(sql)):
        if sql[i] == "(": depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0: return sql[start + 1:i], i
    return sql[start + 1:], len(sql) - 1

def strip_select_columns(sql: str) -> str:
    result, i, sql_up, length = [], 0, sql.upper(), len(sql)
    while i < length:
        m = re.search(r"\bSELECT\b", sql_up[i:], re.IGNORECASE)
        if not m: result.append(sql[i:]); break
        sel_pos = i + m.start()
        result.extend([sql[i:sel_pos], "SELECT "])
        j, depth, found_from = sel_pos + len("SELECT"), 0, False
        while j < length:
            ch = sql[j]
            if ch == "(": depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0: break
            elif depth == 0:
                if re.match(r"\bFROM\b", sql_up[j:], re.IGNORECASE):
                    result.append("__COLS__ "); i = j; found_from = True; break
                if ch == ";": result.append(sql[j:j+1]); i = j + 1; found_from = True; break
            j += 1
        if not found_from: result.append(sql[j:]); break
    return "".join(result)

def strip_update_set(sql: str) -> str:
    result, i, sql_up, length = [], 0, sql.upper(), len(sql)
    while i < length:
        m = re.search(r"\bSET\b", sql_up[i:])
        if not m: result.append(sql[i:]); break
        set_pos = i + m.start()
        result.extend([sql[i:set_pos], "SET "])
        j, depth = set_pos + len("SET"), 0
        while j < length:
            ch = sql[j]
            if ch == "(": depth += 1
            elif ch == ")":
                if depth == 0: break
                depth -= 1
            elif depth == 0:
                up = sql_up[j:]
                if any(re.match(r"\b%s\b" % kw, up) for kw in ("WHERE","WHEN","ON","FROM")) or ch == ";": break
            j += 1
        result.append("__SET__ "); i = j
    return "".join(result)

def strip_insert_col_list(sql: str) -> str:
    return re.sub(r"(INSERT\s+(?:OVERWRITE\s+)?(=?TABLE\s+)?[\w${}.\-]+)(\s*\([^)]*\))(\s*(?:WITH|SELECT|VALUES)\b)", r"\1 __INSERT_COLS__\4", sql, flags=re.IGNORECASE | re.DOTALL)

def strip_function_args(sql: str) -> str:
    result, i, length, sql_up = [], 0, len(sql), sql.upper()
    SKIP = {"FROM","JOIN","USING","WITH","ON","AS","SELECT","WHERE","HAVING","SET","INSERT","UPDATE","DELETE","MERGE","CREATE","TABLE","VIEW","INTO","WHEN","THEN","ELSE","AND","OR","NOT","EXISTS","IN","ANY","ALL","CASE"}
    while i < length:
        m = re.search(r"(\b\w+)\s*\(", sql_up[i:])
        if not m: result.append(sql[i:]); break
        fn_start, paren_start = i + m.start(), i + m.end() - 1
        if m.group(1).upper() in SKIP or (fn_start > 0 and sql[fn_start - 1] in (".", "}", "$")):
            result.append(sql[i:paren_start + 1]); i = paren_start + 1; continue
        result.append(sql[i:fn_start + len(m.group(1))])
        _, end_pos = extract_paren_content(sql, paren_start)
        result.append("(__FUNC_ARGS__)"); i = end_pos + 1
    return "".join(result)


def extract_sources_recursive(query: str) -> set:
    sources = set()
    query = strip_inline_comments(query)
    q = strip_function_args(strip_insert_col_list(strip_update_set(strip_select_columns(remove_string_literals(query)))))
    
    length, kw_pattern = len(q), re.compile(r"\b(FROM|JOIN|USING)\b", re.IGNORECASE)
    CLAUSE_END = {"WHERE","ON","WHEN","SET","HAVING","GROUP","ORDER","UNION","INTERSECT","EXCEPT","LIMIT","SELECT","INSERT","UPDATE","DELETE","MERGE","WITH","INNER","LEFT","RIGHT","FULL","CROSS","JOIN","FROM","USING"}
    
    for kw_m in kw_pattern.finditer(q):
        j = kw_m.end()
        while j < length and q[j] in " \t\n\r": j += 1
        if j >= length: continue
        if q[j] == "(":
            inner, end_pos = extract_paren_content(q, j)
            sources.update(extract_sources_recursive(inner))
            j = end_pos + 1
            alias_m = re.match(r"[\s]+(\w+)", q[j:])
            if alias_m and alias_m.group(1).upper() not in CLAUSE_END: j += alias_m.end()
            while j < length and q[j] in " \t\n\r": j += 1
            if j >= length or q[j] != ",": continue
            j += 1
        while j < length:
            while j < length and q[j] in " \t\n\r": j += 1
            if j >= length or q[j] in (";", ")"): break
            if q[j] == "(":
                inner, end_pos = extract_paren_content(q, j)
                sources.update(extract_sources_recursive(inner))
                j = end_pos + 1
                alias_m = re.match(r"[\s]+(\w+)", q[j:])
                if alias_m and alias_m.group(1).upper() not in CLAUSE_END: j += alias_m.end()
            else:
                tok_m = re.match(r"([^\s,;()\n]+)", q[j:])
                if not tok_m: break
                token_up = tok_m.group(1).upper().rstrip(",;")
                if token_up in CLAUSE_END: break
                tbl = clean_table(tok_m.group(1))
                if tbl: sources.add(tbl)
                j += tok_m.end()
                alias_m = re.match(r"[\s]+([^\s,;()\n]+)", q[j:])
                if alias_m and alias_m.group(1).upper() not in CLAUSE_END and not alias_m.group(1).upper().startswith(","): j += alias_m.end()
            while j < length and q[j] in " \t\n\r": j += 1
            if j < length and q[j] == ",": j += 1
            else: break
    return sources


def extract_target_tables(query: str) -> set:
    targets = set()
    patterns = [
        r"\bINSERT\s+OVERWRITE\s+TABLE\s+([^\s(]+)", r"\bINSERT\s+OVERWRITE\s+(?!TABLE\b)([^\s(]+)",
        r"\bINSERT\s+INTO\s+TABLE\s+([^\s(]+)", r"\bINSERT\s+INTO\s+(?!TABLE\b)([^\s(]+)",
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(=?TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)",
        r"(?<![_\w])\bUPDATE\s+([^\s(]+)", r"\bDELETE\s+FROM\s+([^\s(]+)",
        r"\bMERGE\s+INTO\s+([^\s(]+)", r"\bMERGE\s+(?!INTO\b)([^\s(]+)",
        r"\bALTER\s+TABLE\s+([^\s(]+)", r"\bTRUNCATE\s+TABLE\s+([^\s(]+)",
        r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([^\s;]+)", r"\bDROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?([^\s;]+)"
    ]
    POST_KW = {"PARTITION","CLUSTER","STORED","LOCATION","ROW","FORMAT","FIELDS","LINES","TERMINATED","WITH","SELECT","AS","SET","WHERE","VALUES","ON","USING","IF"}
    for pat in patterns:
        for m in re.finditer(pat, query, re.IGNORECASE):
            raw = m.group(1).strip().rstrip(";,")
            if not raw or raw.upper() in POST_KW: continue
            tbl = clean_table(raw)
            if tbl: targets.add(tbl)
    return targets


# ============================================================
# 대소문자 무시 정밀 매칭 코어 로직
# ============================================================
def build_match_rows_for_single_query(
    query_text: str,
    sources: set,
    targets: set,
    crud_type: str,
    sql_type: str,
    base_directory: str,
    src_file_name: str,
    dir_file: str,
    ref_row: dict,
    compiled_col_patterns: dict,
    query_start_line_no,
    orig_lines: list = None
) -> tuple:
    """
    tbl_name이 존재하면서 동시에 각 쿼리 내에 cols의 칼럼명이 대소문자 무시 조건에 맞을 때만 추출
    """
    results = []
    src_upper = {str(s).strip().upper() for s in sources if s}
    tgt_upper = {str(t).strip().upper() for t in targets if t}
    query_text_upper = query_text.upper()

    tbl_name = ref_row.get("tbl_name", "")
    cols_str = ref_row.get("cols", "")
    if not tbl_name:
        return results, False

    tbl_up = str(tbl_name).strip().upper()

    # [조건 1] 테이블명 매칭 검사 (SOURCE 또는 TARGET)
    match_type = None
    if tbl_up in tgt_upper:
        match_type = "TARGET"
    elif tbl_up in src_upper:
        match_type = "SOURCE"

    if match_type is None:
        return results, False

    col_items = parse_cols(cols_str)
    if not col_items:
        # cols가 없는 경우 테이블 매칭 성공만으로 1행 생성
        results.append(_make_result_row(
            ref_row, base_directory, src_file_name, dir_file,
            crud_type, sql_type, match_type,
            matched_col_name="", matched_col_key="", line_number=None, matched_line=""
        ))
        return results, True

    # [조건 2] 칼럼 존재 여부 파악 및 실제 추출 버퍼 생성
    valid_col_matches = []
    
    for col_item in col_items:
        col_name = col_item["col_name"]
        col_key  = col_item["col_key"]
        col_up   = col_name.strip().upper()

        rx = compiled_col_patterns.get(col_up)
        if rx is None:
            try:
                rx = re.compile(r"\b%s\b" % re.escape(col_name.strip()), re.IGNORECASE)
                compiled_col_patterns[col_up] = rx
            except Exception: pass

        # 정규식 경계검사 또는 무조건 포함검사 (대소문자 제거)
        col_in_query = False
        if rx and rx.search(query_text):
            col_in_query = True
        elif col_up in query_text_upper:
            col_in_query = True

        if col_in_query:
            line_number  = None
            matched_line = ""
            if query_start_line_no is not None and orig_lines:
                start_idx = query_start_line_no - 1
                for idx in range(start_idx, len(orig_lines)):
                    if (rx and rx.search(orig_lines[idx])) or (col_up in orig_lines[idx].upper()):
                        line_number  = idx + 1
                        matched_line = orig_lines[idx].strip()
                        break
            
            if not matched_line:
                for line in query_text.splitlines():
                    if (rx and rx.search(line)) or (col_up in line.upper()):
                        matched_line = line.strip()
                        break

            valid_col_matches.append(_make_result_row(
                ref_row, base_directory, src_file_name, dir_file,
                crud_type, sql_type, match_type,
                matched_col_name=col_name, matched_col_key=col_key,
                line_number=line_number, matched_line=matched_line
            ))

    # 테이블 조건과 칼럼 조건이 최종 동시에 부합하는 경우에만 데이터셋 반환
    if valid_col_matches:
        return valid_col_matches, True
    
    return results, False


def _make_result_row(ref_row: dict, base_directory: str, src_file_name: str,
                     dir_file: str, crud_type: str, sql_type: str,
                     match_type: str, matched_col_name: str, matched_col_key: str,
                     line_number, matched_line: str) -> dict:
    row = {col: ref_row.get(col, "") for col in REF_TABLE_COLS}
    row.update({
        "base_directory": base_directory, "src_file_name": src_file_name, "dir_file": dir_file,
        "crud_type": crud_type, "sql_type": sql_type, "match_type": match_type,
        "matched_col_name": matched_col_name, "matched_col_key": matched_col_key,
        "line_number": line_number if line_number is not None else "", "matched_line": matched_line
    })
    return row


def parse_args() -> tuple:
    args      = sys.argv[1:]
    ref_table = None
    use_db    = False
    conf_path = None

    i = 0
    while i < len(args):
        if args[i] == "--db":
            use_db = True; i += 1
        elif args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]; i += 2
            else:
                print("[오류] --conf 다음에 mysql.conf 파일 경로를 지정하세요.")
                sys.exit(1)
        else:
            if ref_table is None:
                ref_table = args[i]
            i += 1

    if ref_table is None:
        print("사용법: python3 %s.py <스키마.검색기준테이블> [--db] [--conf mysql.conf 경로]" % PROGRAM_NAME)
        sys.exit(1)

    return ref_table, use_db, conf_path


# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    ref_table, use_db, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [source_file 지정 경로 직접 추적 매칭 시작]")
    print("=" * 70)
    print("  검색 기준 테이블   : %s" % ref_table)
    print("  처리일시 (op_dtm)  : %s" % op_dtm)
    print("  실행 ID (run_id)   : %s" % run_id)
    print("  DB 적재 여부       : %s" % ("YES (--db)" if use_db else "NO (파일만 생성)"))
    print("-" * 70)

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 누락되었습니다.")
        sys.exit(1)

    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    # 검색기준테이블 로드
    ref_rows, ref_schema, db_err = load_ref_rows_from_db(mysql_conf, ref_table)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[ERROR] 검색기준테이블 데이터가 비어 있습니다.")
        sys.exit(1)

    unique_tbls = len({r["tbl_name"] for r in ref_rows if r["tbl_name"]})
    print("[INFO] 기준테이블 전체 %d 행 / 고유 테이블 %d 개 로드 완료" % (len(ref_rows), unique_tbls))

    # cols 목록 요건 출력 및 파일 백업
    os.makedirs(IN_DIR, exist_ok=True)
    in_csv_path = os.path.join(IN_DIR, "%s_search_input.csv" % PROGRAM_NAME)
    with open(in_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=REF_TABLE_COLS)
        writer.writeheader()
        writer.writerows(ref_rows)

    compiled_col_patterns = {}
    result_buffer = []
    
    # 지표 집계용
    scanned_files_set = set()
    total_queries_cnt = 0
    total_lines_cnt   = 0
    matched_file_counts = {}
    
    # 각 ref_row 별 매칭 여부 체크 플래그
    ref_matched_flags = [False] * len(ref_rows)

    # 파일별 캐싱 처리 객체
    file_queries_cache = {}

    print("[INFO] source_file 연계 소스 코드 매칭 분석 진행 중...")
    
    for idx, ref_row in enumerate(ref_rows):
        file_path = ref_row.get("source_file", "").strip()
        
        if not file_path:
            continue

        # 파일 데이터 캐싱 풀 가동
        if file_path not in file_queries_cache:
            queries, t_lines, o_lines = extract_queries_from_file(file_path)
            file_queries_cache[file_path] = (queries, t_lines, o_lines)
            if t_lines > 0:
                scanned_files_set.add(file_path)
                total_queries_cnt += len(queries)
                total_lines_cnt   += t_lines

        queries_with_offset, _, orig_lines = file_queries_cache[file_path]
        
        base_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)

        row_any_matched = False
        
        for query, raw_query, query_start_line_no in queries_with_offset:
            sql_type  = detect_real_sql_type(query)
            crud_type = classify_crud_type(sql_type)
            sources   = extract_sources_recursive(query)
            targets   = extract_target_tables(query)

            match_rows, is_tbl_ok = build_match_rows_for_single_query(
                query_text=raw_query, sources=sources, targets=targets,
                crud_type=crud_type, sql_type=sql_type,
                base_directory=base_dir, src_file_name=file_name, dir_file=file_path,
                ref_row=ref_row, compiled_col_patterns=compiled_col_patterns,
                query_start_line_no=query_start_line_no, orig_lines=orig_lines
            )
            
            if is_tbl_ok and match_rows:
                row_any_matched = True
                result_buffer.extend(match_rows)
                matched_file_counts[file_path] = matched_file_counts.get(file_path, 0) + len(match_rows)

        if row_any_matched:
            ref_matched_flags[idx] = True

    # ── 미매칭 행 보존 법칙 (요건3/4 NULL 행 주입) ──
    null_row_cnt = 0
    for idx, ref_row in enumerate(ref_rows):
        if not ref_matched_flags[idx]:
            col_items = parse_cols(ref_row.get("cols", ""))
            if col_items:
                for col_item in col_items:
                    result_buffer.append(_make_result_row(
                        ref_row, base_directory="", src_file_name="", dir_file="",
                        crud_type="", sql_type="", match_type="",
                        matched_col_name=col_item["col_name"], matched_col_key=col_item["col_key"],
                        line_number=None, matched_line=""
                    ))
                    null_row_cnt += 1
            else:
                result_buffer.append(_make_result_row(
                    ref_row, base_directory="", src_file_name="", dir_file="",
                    crud_type="", sql_type="", match_type="",
                    matched_col_name="", matched_col_key="", line_number=None, matched_line=""
                ))
                null_row_cnt += 1

    print("-" * 70)
    print("[INFO] 소스 추적 완료 요약:")
    print("  - 유효 스캔 파일 수 : %8d 개" % len(scanned_files_set))
    print("  - 총 추출 쿼리 수   : %8d 건" % total_queries_cnt)
    print("  - 분석 총 라인 수   : %8d 줄" % total_lines_cnt)
    print("  - 탐색 매칭 성공 건 : %8d 건" % (len(result_buffer) - null_row_cnt))
    print("  - 보존된 미매칭 행수: %8d 건" % null_row_cnt)
    print("  - 최종 결과 행 합계 : %8d 건" % len(result_buffer))
    print("-" * 70)

    if matched_file_counts:
        print("[INFO] 파일별 매칭 레코드 생성 현황:")
        for fpath, cnt in sorted(matched_file_counts.items()):
            print("  - %-60s (%d 건)" % (fpath, cnt))
        print("-" * 70)

    # 결과 CSV 출력
    csv_output_path = save_result_csv(result_buffer, ref_table, op_dtm)
    print("[INFO] CSV 저장 완료: %s" % csv_output_path)

    # DB 적재
    db_inserted = 0
    if use_db:
        db_inserted, db_err_msg = db_insert_result_all(result_buffer, run_id, op_dtm, mysql_conf, ref_table, ref_schema)
        if db_err_msg:
            print("[ERROR] DB 테이블 생성 및 마이그레이션 실패: %s" % db_err_msg)
        else:
            print("[INFO] MySQL 마이그레이션 적재 완료: %d 건" % db_inserted)

    print("=" * 70)
    print(" p190872_local_chk_v01 프로세스 정상 종료 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()