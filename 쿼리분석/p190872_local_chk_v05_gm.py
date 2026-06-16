#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v05_gm.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v05_gm (2026-06-16)
#   [추출 조건 및 테이블명 변경]
#   - 파일명 및 프로그램 식별자를 p190872_local_chk_v05_gm 으로 변경
#   - 파싱 칼럼 기준(col_name) 검색 시 기존 LIKE(in 연산) 방식을 제거하고 정규식 완전일치(\b단어\b) 조건으로 롤백/수정
#   - 결과 DB 테이블명 생성 규칙을 변경하여 프로그램명이 포함되도록 수정 ({PROGRAM_NAME}_{테이블명}_...)
#   - (접수 요건 추가): 테이블명 생성 규칙을 {ref_tbl_only}_{구분}_{tb_add_gbn} 형태로 변경 (tb_add_gbn = "v05")
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

MYSQL_CONF_FILE = "mysql.conf"

# 검색기준테이블 고정 칼럼 목록
REF_TABLE_COLS = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 파일1 cols 파싱 결과 필드
COLS_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc",
    "col_name", "col_key",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 파일2 query_text 결과 필드
QUERY_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc",
    "query_seq", "query_text",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 파일3 매칭 결과 최종 필드 레이아웃 (단건 모수 유지형)
MATCH_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc",
    "col_name", "col_key",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
    "query_seq", "match_type", "line_number", "matched_line",
    "vscode_open_cmd",
]

# 파일4 암호화 코드 맵핑 변환 결과 필드 레이아웃 (다건 전수 확장형)
ENC_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc",
    "col_name", "col_key", "enc_code",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
    "query_seq", "match_type", "line_number", "matched_line",
    "vscode_open_cmd",
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
        raise ImportError(
            "MySQL 드라이버가 없습니다. pip install pymysql 또는 mysql-connector-python을 설치하세요."
        )


# ============================================================
# mysql.conf 로드
# ============================================================
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


# ============================================================
# 스키마.테이블 분리 유틸
# ============================================================
def split_schema_table(full_table: str) -> tuple:
    parts = full_table.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", parts[0].strip()


def make_fq(schema: str, table: str) -> str:
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table


# ============================================================
# cols 파싱: "col_01:k1,col_bb:k2" → [{"col_name":..,"col_key":..}, ...]
# ============================================================
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


# ============================================================
# 파싱 칼럼 키값 코드 변환 함수
# ============================================================
def convert_key_to_code(col_key: str) -> str:
    if not col_key:
        return ""
    k_lower = col_key.strip().lower()
    if k_lower == "key1":   return "e1"
    elif k_lower == "key2": return "e2"
    elif k_lower == "key3": return "e3"
    elif k_lower == "key4": return "e4"
    return col_key


# ============================================================
# 검색기준테이블 전체 조회
# ============================================================
def load_ref_rows_from_db(mysql_conf: dict, ref_table: str) -> tuple:
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

        sql = "SELECT %s FROM %s ORDER BY tbl_name, no" % (", ".join(select_parts), fq_table)
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
# 소스 파싱: 전처리 (주석 제거, 문자열 리터럴 유지)
# ============================================================
def preprocess(content: str) -> str:
    content = "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))
    content = "\n".join(line for line in content.splitlines() if not re.match(r"(?i)^\s*DBMS_OUTPUT", line))
    content = "\n".join(line for line in content.splitlines() if not (line.strip().startswith("/*") and line.strip().endswith("*/")))
    pattern = re.compile(r"('(?:[^']|'')*')|(\"(?:[^\"]|\"\")*\")|(--[^\n]*$)|(/\*.*?\*/)", re.MULTILINE | re.DOTALL | re.VERBOSE)
    return pattern.sub(lambda m: m.group(0) if (m.group(1) or m.group(2)) else "", content)


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


def extract_queries_from_text(raw: str) -> list:
    result     = []
    orig_lines = raw.splitlines()
    content    = preprocess(raw)

    ei_queries = []
    ei_pattern = re.compile(r"\bEXECUTE\s+IMMEDIATE\s+'(.*?)'", re.IGNORECASE | re.DOTALL)
    for m in ei_pattern.finditer(content):
        inner = m.group(1).strip()
        if inner: ei_queries.append(inner)

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

            result.append({"query_text": query, "start_line_no": start_line_no})
        pos = end

    for ei_q in ei_queries:
        result.append({"query_text": ei_q, "start_line_no": None})

    return result


def open_and_extract_queries(source_file_path: str) -> tuple:
    if not source_file_path or not source_file_path.strip():
        return [], "source_file 경로가 비어 있습니다.", [], ""
    path = source_file_path.strip().replace("\\", os.sep).replace("/", os.sep)
    if not os.path.isfile(path):
        return [], "파일을 찾을 수 없습니다: %s" % path, [], ""

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception as e:
        return [], "파일 접근 실패: %s / %s" % (path, str(e)), [], ""

    try:
        queries = extract_queries_from_text(raw)
    except Exception as e:
        return [], "쿼리 추출 오류: %s" % str(e), [], ""

    return queries, None, raw.splitlines(), raw


# ============================================================
# DDL / INSERT 스키마 선언 정의 
# ============================================================
_DDL_DROP   = "DROP TABLE IF EXISTS {table};"

_DDL_CREATE_COLS = """
CREATE TABLE {table} (
  `id`           BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`       VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `db_name`      VARCHAR(200)  NULL                     COMMENT '기준테이블: DB명',
  `tbl_name`     VARCHAR(500)  NOT NULL                 COMMENT '기준테이블: 테이블명',
  `operation`    VARCHAR(50)   NULL                     COMMENT '기준테이블: 오퍼레이션',
  `no`           INT           NULL                     COMMENT '기준테이블: 순번',
  `source_file`  VARCHAR(500)  NULL                     COMMENT '기준테이블: 소스파일 경로',
  `process_yn`   VARCHAR(1)    NULL                     COMMENT '기준테이블: 처리여부',
  `process_desc` VARCHAR(500)  NULL                     COMMENT '기준테이블: 처리설명',
  `col_name`     VARCHAR(500)  NULL                     COMMENT 'cols 파싱: 칼럼명',
  `col_key`      VARCHAR(200)  NULL                     COMMENT 'cols 파싱: 키값',
  `enc_col_cnt`  INT           NULL                     COMMENT '기준테이블: 암호화 칼럼 수',
  `ins_cnt`      INT           NULL                     COMMENT '기준테이블: INSERT 건수',
  `sel_cnt`      INT           NULL                     COMMENT '기준테이블: SELECT 건수',
  `op_dtm`       DATETIME      NOT NULL                 COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`   (`run_id`),
  KEY `idx_tbl_name` (`tbl_name`(191)),
  KEY `idx_col_name` (`col_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='검색기준테이블 cols 파싱 결과';
"""

_SQL_INSERT_COLS = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, col_name, col_key,
   enc_col_cnt, ins_cnt, sel_cnt, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_DDL_CREATE_QUERY = """
CREATE TABLE {table} (
  `id`           BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`       VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `db_name`      VARCHAR(200)  NULL                     COMMENT '기준테이블: DB명',
  `tbl_name`     VARCHAR(500)  NOT NULL                 COMMENT '기준테이블: 테이블명',
  `operation`    VARCHAR(50)   NULL                     COMMENT '기준테이블: 오퍼레이션',
  `no`           INT           NULL                     COMMENT '기준테이블: 순번',
  `source_file`  VARCHAR(500)  NULL                     COMMENT '기준테이블: 소스파일 경로',
  `process_yn`   VARCHAR(1)    NULL                     COMMENT '기준테이블: 처리여부',
  `process_desc` VARCHAR(500)  NULL                     COMMENT '기준테이블: 처리설명',
  `query_seq`    INT           NULL                     COMMENT '파일 내 쿼리 순번',
  `query_text`   LONGTEXT      NULL                     COMMENT '추출된 쿼리 텍스트',
  `enc_col_cnt`  INT           NULL                     COMMENT '기준테이블: 암호화 칼럼 수',
  `ins_cnt`      INT           NULL                     COMMENT '기준테이블: INSERT 건수',
  `sel_cnt`      INT           NULL                     COMMENT '기준테이블: SELECT 건수',
  `op_dtm`       DATETIME      NOT NULL                 COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`   (`run_id`),
  KEY `idx_tbl_name` (`tbl_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='검색기준테이블 쿼리 추출 결과';
"""

_SQL_INSERT_QUERY = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, query_seq, query_text,
   enc_col_cnt, ins_cnt, sel_cnt, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_DDL_CREATE_MATCH = """
CREATE TABLE {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `db_name`          VARCHAR(200)  NULL                     COMMENT '기준테이블: DB명',
  `tbl_name`         VARCHAR(500)  NOT NULL                 COMMENT '기준테이블: 테이블명',
  `operation`        VARCHAR(50)   NULL                     COMMENT '기준테이블: 오퍼레이션',
  `no`               INT           NULL                     COMMENT '기준테이블: 순번',
  `source_file`      VARCHAR(500)  NULL                     COMMENT '기준테이블: 소스파일 경로',
  `process_yn`       VARCHAR(1)    NULL                     COMMENT '기준테이블: 처리여부',
  `process_desc`     VARCHAR(500)  NULL                     COMMENT '기준테이블: 처리설명',
  `col_name`         VARCHAR(500)  NULL                     COMMENT 'cols 파싱: 칼럼명',
  `col_key`          VARCHAR(200)  NULL                     COMMENT 'cols 파싱: 키값',
  `enc_col_cnt`      INT           NULL                     COMMENT '기준테이블: 암호화 칼럼 수',
  `ins_cnt`          INT           NULL                     COMMENT '기준테이블: INSERT 건수',
  `sel_cnt`          INT           NULL                     COMMENT '기준테이블: SELECT 건수',
  `query_seq`        INT           NULL                     COMMENT '매칭 쿼리 순번',
  `match_type`       VARCHAR(20)   NULL                     COMMENT 'SOURCE / TARGET 구분',
  `line_number`      INT           NULL                     COMMENT '소스 절대 행번호',
  `matched_line`     TEXT          NULL                     COMMENT '매칭 라인 텍스트 내용',
  `vscode_open_cmd`  VARCHAR(1000) NULL                     COMMENT 'VS Code 다이렉트 바로가기 커맨드',
  `op_dtm`           DATETIME      NOT NULL                 COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`    (`run_id`),
  KEY `idx_tbl_name`  (`tbl_name`(191)),
  KEY `idx_col_name`  (`col_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스/타겟 및 칼럼 매칭 연계 결과';
"""

_SQL_INSERT_MATCH = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, col_name, col_key, enc_col_cnt, ins_cnt, sel_cnt,
   query_seq, match_type, line_number, matched_line, vscode_open_cmd, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_DDL_CREATE_ENC = """
CREATE TABLE {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
  `db_name`          VARCHAR(200)  NULL                     COMMENT '기준테이블: DB명',
  `tbl_name`         VARCHAR(500)  NOT NULL                 COMMENT '기준테이블: 테이블명',
  `operation`        VARCHAR(50)   NULL                     COMMENT '기준테이블: 오퍼레이션',
  `no`               INT           NULL                     COMMENT '기준테이블: 순번',
  `source_file`      VARCHAR(500)  NULL                     COMMENT '기준테이블: 소스파일 경로',
  `process_yn`       VARCHAR(1)    NULL                     COMMENT '기준테이블: 처리여부',
  `process_desc`     VARCHAR(500)  NULL                     COMMENT '기준테이블: 처리설명',
  `col_name`         VARCHAR(500)  NULL                     COMMENT 'cols 파싱: 칼럼명',
  `col_key`          VARCHAR(200)  NULL                     COMMENT 'cols 파싱: 원본키값',
  `enc_code`         VARCHAR(200)  NULL                     COMMENT '코드 변환 맵핑값 (e1~e4)',
  `enc_col_cnt`      INT           NULL                     COMMENT '기준테이블: 암호화 칼럼 수',
  `ins_cnt`          INT           NULL                     COMMENT '기준테이블: INSERT 건수',
  `sel_cnt`          INT           NULL                     COMMENT '기준테이블: SELECT 건수',
  `query_seq`        INT           NULL                     COMMENT '매칭 쿼리 순번',
  `match_type`       VARCHAR(20)   NULL                     COMMENT 'SOURCE / TARGET 구분',
  `line_number`      INT           NULL                     COMMENT '소스 절대 행번호',
  `matched_line`     TEXT          NULL                     COMMENT '매칭 라인 텍스트 내용',
  `vscode_open_cmd`  VARCHAR(1000) NULL                     COMMENT 'VS Code 다이렉트 바로가기 커맨드',
  `op_dtm`           DATETIME      NOT NULL                 COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`    (`run_id`),
  KEY `idx_tbl_name`  (`tbl_name`(191)),
  KEY `idx_enc_code`  (`enc_code`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='암호화 코드 키값 맵핑 변환 결과';
"""

_SQL_INSERT_ENC = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, col_name, col_key, enc_code, enc_col_cnt, ins_cnt, sel_cnt,
   query_seq, match_type, line_number, matched_line, vscode_open_cmd, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def build_table_names(ref_schema: str, ref_tbl_only: str) -> dict:
    # PROGRAM_NAME(예: p190872_local_chk_v05_gm)에서 정규식으로 "v05" 파트만 추출
    # 매칭 실패 시 기본값으로 "v05"를 사용하도록 설계
    match = re.search(r'_(v\d+)(?:_|$)', PROGRAM_NAME)
    tb_add_gbn = match.group(1) if match else "v05"

    # 요건 반영: {ref_tbl_only}_{구분}_{tb_add_gbn} 형식으로 변경
    cols_only  = "%s_cols_%s"  % (ref_tbl_only, tb_add_gbn)
    query_only = "%s_query_%s" % (ref_tbl_only, tb_add_gbn)
    match_only = "%s_match_%s" % (ref_tbl_only, tb_add_gbn)
    enc_only   = "%s_enc_%s"   % (ref_tbl_only, tb_add_gbn)
    
    return {
        "cols_only":  cols_only, "query_only": query_only, "match_only": match_only, "enc_only": enc_only,
        "cols_fq":    make_fq(ref_schema, cols_only),
        "query_fq":   make_fq(ref_schema, query_only),
        "match_fq":   make_fq(ref_schema, match_only),
        "enc_fq":     make_fq(ref_schema, enc_only),
    }


def db_load_table(mysql_conf: dict, fq_table: str, ddl_create: str, sql_insert: str, batch: list, table_label: str) -> tuple:
    conn, cursor = None, None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        cursor.execute(_DDL_DROP.format(table=fq_table))
        conn.commit()
        cursor.execute(ddl_create.format(table=fq_table))
        conn.commit()
        if batch:
            cursor.executemany(sql_insert.format(table=fq_table), batch)
            conn.commit()
        print("[INFO] DB 적재 완료 [%s]: %s  (%d 건)" % (table_label, fq_table, len(batch)))
        return len(batch), None
    except Exception as e:
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
    try: return int(v) if v not in (None, "") else None
    except Exception: return None


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
            if ref_table is None: ref_table = args[args_idx] if 'args_idx' in locals() else args[i]
            ref_table = args[i]
            i += 1

    if ref_table is None:
        print("사용법: python3 %s.py <스키마.검색기준테이블> [--db] [--conf mysql.conf 경로]" % PROGRAM_NAME)
        sys.exit(1)

    return ref_table, use_db, conf_path


# ============================================================
# MAIN
# ============================================================
def main():
    ref_table, use_db, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [검색기준테이블 조회 → cols 파싱 + query_text 추출 파일 생성]")
    print("=" * 70)
    print("  검색 기준 테이블   : %s" % ref_table)
    print("  처리일시 (op_dtm)  : %s" % op_dtm)
    print("  실행 ID (run_id)   : %s" % run_id)
    print("  DB 적재 여부       : %s" % ("YES (--db)" if use_db else "NO (파일만 생성)"))
    print("-" * 70)

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다.")
        sys.exit(1)

    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    print("[INFO] MySQL 접속 정보")
    print("  드라이버           : %s" % _MYSQL_DRIVER)
    print("  호스트             : %s:%s" % (mysql_conf.get("host"), mysql_conf.get("port", 3306)))
    print("  데이터베이스       : %s" % mysql_conf.get("database"))
    print("-" * 70)

    print("[INFO] 검색기준테이블 조회 중: %s ..." % ref_table)
    ref_rows, ref_schema, ref_tbl_only, db_err = load_ref_rows_from_db(mysql_conf, ref_table)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[ERROR] 검색기준테이블에서 조회된 데이터가 없습니다.")
        sys.exit(1)

    print("[INFO] 조회 완료: %d 행" % len(ref_rows))
    print("-" * 70)

    print("[INFO] 검색기준 cols 목록: 화면출력 생략")
    print("  " + "-" * 110)
    for i, ref_row in enumerate(ref_rows, 1):
        tbl    = ref_row.get("tbl_name", "")
        cols   = ref_row.get("cols", "")
        parsed = parse_cols(cols)
    print("-" * 70)

    tbl_names      = build_table_names(ref_schema, ref_tbl_only)
    os.makedirs(OUT_DIR, exist_ok=True)
    csv_cols_path  = os.path.join(OUT_DIR, "%s_cols_v05.csv"  % ref_tbl_only)
    csv_query_path = os.path.join(OUT_DIR, "%s_query_v05.csv" % ref_tbl_only)
    csv_match_path = os.path.join(OUT_DIR, "%s_match_v05.csv" % ref_tbl_only)
    csv_enc_path   = os.path.join(OUT_DIR, "%s_enc_v05.csv"   % ref_tbl_only)

    cols_buffer  = []
    query_buffer = []
    match_buffer = []
    enc_buffer   = []

    stat_total      = len(ref_rows)
    stat_ok, stat_skip, stat_err, stat_no_query = 0, 0, 0, 0
    error_log       = []
    compiled_col_patterns = {}

    print("[INFO] source_file 오픈 및 쿼리 추출 시작 ...")

    for ref_row in ref_rows:
        src_file = ref_row.get("source_file", "").strip()
        tbl_name = ref_row.get("tbl_name", "").strip()
        tbl_up   = tbl_name.upper()

        base_ref = {col: ref_row.get(col, "") for col in REF_TABLE_COLS if col != "cols"}

        # ── [파일1 적재] cols 분리 전처리 ──
        current_row_cols = []
        col_items = parse_cols(ref_row.get("cols", ""))
        if col_items:
            for col_item in col_items:
                row = dict(base_ref)
                row["col_name"], row["col_key"] = col_item["col_name"], col_item["col_key"]
                cols_buffer.append(row)
                current_row_cols.append(col_item)
        else:
            row = dict(base_ref)
            row["col_name"], row["col_key"] = "", ""
            cols_buffer.append(row)

        # ── [파일2 추출 및 파일3/파일4 전수 매칭 결합 엔진] ──
        if not src_file:
            stat_skip += 1
            msg = "source_file 비어있음 (tbl_name=%s)" % tbl_name
            error_log.append((src_file, msg))
            
            row_q = dict(base_ref); row_q["query_seq"], row_q["query_text"] = None, ""
            query_buffer.append(row_q)
            
            for c_item in (current_row_cols if current_row_cols else [{"col_name": "", "col_key": ""}]):
                row_m = dict(base_ref)
                row_m["col_name"], row_m["col_key"] = c_item["col_name"], c_item["col_key"]
                row_m.update({"query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                match_buffer.append(row_m)
                
                row_e = dict(base_ref)
                row_e["col_name"], row_e["col_key"] = c_item["col_name"], c_item["col_key"]
                row_e.update({"enc_code": convert_key_to_code(c_item["col_key"]), "query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                enc_buffer.append(row_e)
            continue

        queries, open_err, orig_lines, raw_content = open_and_extract_queries(src_file)
        raw_content_upper = raw_content.upper()

        if open_err:
            stat_err += 1
            error_log.append((src_file, open_err))
            print("  [WARN] %s" % open_err)
            
            row_q = dict(base_ref); row_q["query_seq"], row_q["query_text"] = None, open_err
            query_buffer.append(row_q)
            
            for c_item in (current_row_cols if current_row_cols else [{"col_name": "", "col_key": ""}]):
                row_m = dict(base_ref)
                row_m["col_name"], row_m["col_key"] = c_item["col_name"], c_item["col_key"]
                row_m.update({"query_seq": "", "match_type": "", "line_number": "", "matched_line": open_err, "vscode_open_cmd": ""})
                match_buffer.append(row_m)
                
                row_e = dict(base_ref)
                row_e["col_name"], row_e["col_key"] = c_item["col_name"], c_item["col_key"]
                row_e.update({"enc_code": convert_key_to_code(c_item["col_key"]), "query_seq": "", "match_type": "", "line_number": "", "matched_line": open_err, "vscode_open_cmd": ""})
                enc_buffer.append(row_e)
            continue

        if not queries:
            stat_no_query += 1
            error_log.append((src_file, "쿼리 추출 결과 없음"))
            
            row_q = dict(base_ref); row_q["query_seq"], row_q["query_text"] = None, ""
            query_buffer.append(row_q)
            
            for c_item in (current_row_cols if current_row_cols else [{"col_name": "", "col_key": ""}]):
                row_m = dict(base_ref)
                row_m["col_name"], row_m["col_key"] = c_item["col_name"], c_item["col_key"]
                row_m.update({"query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                match_buffer.append(row_m)
                
                row_e = dict(base_ref)
                row_e["col_name"], row_e["col_key"] = c_item["col_name"], c_item["col_key"]
                row_e.update({"enc_code": convert_key_to_code(c_item["col_key"]), "query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                enc_buffer.append(row_e)
            continue

        stat_ok += 1
        
        # 파일3용 단건 매칭 여부 추적 사전 구조 구성
        file3_match_success_map = { (c["col_name"], c["col_key"]): False for c in current_row_cols } if current_row_cols else { ("", ""): False }
        # 파일4용 다건 매칭 여부 추적 사전 구조 구성
        file4_match_success_map = { (c["col_name"], c["col_key"]): False for c in current_row_cols } if current_row_cols else { ("", ""): False }

        is_table_in_file = tbl_up in raw_content_upper

        for q_idx, q_item in enumerate(queries, 1):
            raw_query = q_item["query_text"]
            query_text_upper = raw_query.upper()
            line_no_offset = q_item["start_line_no"]

            row_q = dict(base_ref)
            row_q["query_seq"], row_q["query_text"] = q_idx, raw_query
            query_buffer.append(row_q)

            if is_table_in_file:
                if current_row_cols:
                    for c_item in current_row_cols:
                        c_name, c_key = c_item["col_name"], c_item["col_key"]
                        c_up = c_name.strip().upper()

                        # 정규식 캐싱 및 컴파일
                        rx = compiled_col_patterns.get(c_up)
                        if rx is None:
                            try:
                                rx = re.compile(r"\b%s\b" % re.escape(c_name.strip()), re.IGNORECASE)
                                compiled_col_patterns[c_up] = rx
                            except Exception:
                                pass

                        # 요건 반영: LIKE 방식이 아닌 일치하는 단어가 있을 때 추출하도록 변경 (\b 완전일치)
                        col_in_query = False
                        if rx and rx.search(query_text_upper):
                            col_in_query = True

                        if col_in_query:
                            # ─── 파일4 전용 다건 전수 라인 추출 프로세스 시작 ───
                            matched_lines_found = []
                            if line_no_offset is not None and orig_lines:
                                start_idx = line_no_offset - 1
                                for idx in range(start_idx, len(orig_lines)):
                                    if rx.search(orig_lines[idx]):
                                        matched_lines_found.append({
                                            "line_number": idx + 1,
                                            "matched_line": orig_lines[idx].strip()
                                        })
                                    if ";" in orig_lines[idx] and idx > start_idx + 1:
                                        if (idx - start_idx) >= len(raw_query.splitlines()):
                                            break
                            
                            if not matched_lines_found:
                                for line in raw_query.splitlines():
                                    if rx.search(line):
                                        matched_lines_found.append({
                                            "line_number": line_no_offset if line_no_offset is not None else "",
                                            "matched_line": line.strip()
                                        })
                                        break

                            # 1) [기존 복원 - 파일3 용] 단건 모수 테이블 매칭 적재 가동
                            if matched_lines_found and not file3_match_success_map[(c_name, c_key)]:
                                file3_match_success_map[(c_name, c_key)] = True
                                first_f = matched_lines_found[0] # 최초 검출된 1건만 취함
                                l_num_3 = first_f["line_number"]
                                l_src_3 = first_f["matched_line"]
                                vsc_cmd_3 = "code -g %s:%s" % (src_file, l_num_3) if l_num_3 else "code -g %s" % src_file

                                row_m = dict(base_ref)
                                row_m["col_name"], row_m["col_key"] = c_name, c_key
                                row_m.update({
                                    "query_seq": q_idx, "match_type": "MATCHED",
                                    "line_number": l_num_3, "matched_line": l_src_3, 
                                    "vscode_open_cmd": vsc_cmd_3
                                })
                                match_buffer.append(row_m)

                            # 2) [다건 전수 유지 - 파일4 용] 매칭되는 행 수만큼 루프 돌려 전량 확장 적재
                            if matched_lines_found:
                                file4_match_success_map[(c_name, c_key)] = True
                                for item_f in matched_lines_found:
                                    l_num_4 = item_f["line_number"]
                                    l_src_4 = item_f["matched_line"]
                                    vsc_cmd_4 = "code -g %s:%s" % (src_file, l_num_4) if l_num_4 else "code -g %s" % src_file

                                    row_e = dict(base_ref)
                                    row_e["col_name"], row_e["col_key"] = c_name, c_key
                                    row_e.update({
                                        "enc_code": convert_key_to_code(c_key),
                                        "query_seq": q_idx, "match_type": "MATCHED",
                                        "line_number": l_num_4, "matched_line": l_src_4, 
                                        "vscode_open_cmd": vsc_cmd_4
                                    })
                                    enc_buffer.append(row_e)
                else:
                    # 칼럼 선언 없는 테이블 매칭 단독 로우 제어
                    file3_match_success_map[("", "")] = True
                    file4_match_success_map[("", "")] = True
                    vsc_cmd = "code -g %s:%s" % (src_file, line_no_offset) if line_no_offset else "code -g %s" % src_file
                    
                    row_m = dict(base_ref)
                    row_m.update({
                        "col_name": "", "col_key": "", "query_seq": q_idx, "match_type": "MATCHED",
                        "line_number": line_no_offset if line_no_offset is not None else "", "matched_line": "",
                        "vscode_open_cmd": vsc_cmd
                    })
                    match_buffer.append(row_m)

                    row_e = dict(base_ref)
                    row_e.update({
                        "col_name": "", "col_key": "", "enc_code": "", "query_seq": q_idx, "match_type": "MATCHED",
                        "line_number": line_no_offset if line_no_offset is not None else "", "matched_line": "",
                        "vscode_open_cmd": vsc_cmd
                    })
                    enc_buffer.append(row_e)

        # ── [파일3 미매칭 구제] 모수 행 형태 보존용 공란 적재 ──
        for (c_name, c_key), is_success in file3_match_success_map.items():
            if not is_success:
                row_m = dict(base_ref)
                row_m["col_name"], row_m["col_key"] = c_name, c_key
                row_m.update({"query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                match_buffer.append(row_m)

        # ── [파일4 미매칭 구제] 모수 행 형태 보존용 공란 적재 ──
        for (c_name, c_key), is_success in file4_match_success_map.items():
            if not is_success:
                row_e = dict(base_ref)
                row_e["col_name"], row_e["col_key"] = c_name, c_key
                row_e.update({"enc_code": convert_key_to_code(c_key), "query_seq": "", "match_type": "", "line_number": "", "matched_line": "", "vscode_open_cmd": ""})
                enc_buffer.append(row_e)

    print("[INFO] source_file 처리 완료:")
    print("  - 전체 ref_row 수  : %8d 건" % stat_total)
    print("  - 쿼리 추출 성공   : %8d 건" % stat_ok)
    print("  - source_file 없음 : %8d 건" % stat_skip)
    print("  - 파일 오픈 오류   : %8d 건" % stat_err)
    print("  - 쿼리 추출 없음   : %8d 건" % stat_no_query)
    print("  - 파일1(cols) 행수 : %8d 건" % len(cols_buffer))
    print("  - 파일2(query) 행수: %8d 건" % len(query_buffer))
    print("  - 파일3(match) 행수: %8d 건 (모수 기준 단건 롤백 완료)" % len(match_buffer))
    print("  - 파일4(enc) 행수  : %8d 건 (다건 전수 확장 유지)" % len(enc_buffer))
    print("-" * 70)

    if error_log:
        print("[INFO] 처리 오류 / 스킵 목록:")
        for src, msg in error_log:
            print("  - [%s]  %s" % (src or "(경로없음)", msg))
        print("-" * 70)

    save_csv(cols_buffer, csv_cols_path, COLS_FIELDNAMES, op_dtm)
    save_csv(query_buffer, csv_query_path, QUERY_FIELDNAMES, op_dtm)
    save_csv(match_buffer, csv_match_path, MATCH_FIELDNAMES, op_dtm)
    save_csv(enc_buffer, csv_enc_path, ENC_FIELDNAMES, op_dtm)
    print("[INFO] 파일1 저장 완료: %s  (%d 건)" % (csv_cols_path, len(cols_buffer)))
    print("[INFO] 파일2 저장 완료: %s  (%d 건)" % (csv_query_path, len(query_buffer)))
    print("[INFO] 파일3 저장 완료: %s  (%d 건)" % (csv_match_path, len(match_buffer)))
    print("[INFO] 파일4 저장 완료: %s  (%d 건)" % (csv_enc_path, len(enc_buffer)))
    print("-" * 70)

    cols_inserted, query_inserted, match_inserted, enc_inserted = 0, 0, 0, 0
    cols_err, query_err, match_err, enc_err = None, None, None, None

    if use_db:
        print("[INFO] DB 적재 시작 ...")
        cols_batch = [(run_id, r["db_name"], r["tbl_name"], r["operation"], to_int(r["no"]), r["source_file"], r["process_yn"], r["process_desc"], r["col_name"], r["col_key"], to_int(r["enc_col_cnt"]), to_int(r["ins_cnt"]), to_int(r["sel_cnt"]), op_dtm) for r in cols_buffer]
        cols_inserted, cols_err = db_load_table(mysql_conf, tbl_names["cols_fq"], _DDL_CREATE_COLS, _SQL_INSERT_COLS, cols_batch, "파일1-cols")

        query_batch = [(run_id, r["db_name"], r["tbl_name"], r["operation"], to_int(r["no"]), r["source_file"], r["process_yn"], r["process_desc"], to_int(r["query_seq"]), r["query_text"], to_int(r["enc_col_cnt"]), to_int(r["ins_cnt"]), to_int(r["sel_cnt"]), op_dtm) for r in query_buffer]
        query_inserted, query_err = db_load_table(mysql_conf, tbl_names["query_fq"], _DDL_CREATE_QUERY, _SQL_INSERT_QUERY, query_batch, "파일2-query")

        match_batch = [(run_id, r["db_name"], r["tbl_name"], r["operation"], to_int(r["no"]), r["source_file"], r["process_yn"], r["process_desc"], r["col_name"], r["col_key"], to_int(r["enc_col_cnt"]), to_int(r["ins_cnt"]), to_int(r["sel_cnt"]), to_int(r["query_seq"]), r["match_type"], to_int(r["line_number"]), r["matched_line"], r["vscode_open_cmd"], op_dtm) for r in match_buffer]
        match_inserted, match_err = db_load_table(mysql_conf, tbl_names["match_fq"], _DDL_CREATE_MATCH, _SQL_INSERT_MATCH, match_batch, "파일3-match")

        enc_batch = [(run_id, r["db_name"], r["tbl_name"], r["operation"], to_int(r["no"]), r["source_file"], r["process_yn"], r["process_desc"], r["col_name"], r["col_key"], r["enc_code"], to_int(r["enc_col_cnt"]), to_int(r["ins_cnt"]), to_int(r["sel_cnt"]), to_int(r["query_seq"]), r["match_type"], to_int(r["line_number"]), r["matched_line"], r["vscode_open_cmd"], op_dtm) for r in enc_buffer]
        enc_inserted, enc_err = db_load_table(mysql_conf, tbl_names["enc_fq"], _DDL_CREATE_ENC, _SQL_INSERT_ENC, enc_batch, "파일4-enc")
        print("-" * 70)

    print("=" * 70)
    print(" 처리 완료 요약")
    print("=" * 70)
    print("  처리일시             : %s" % op_dtm)
    print("  run_id               : %s" % run_id)
    print("  검색기준 테이블      : %s" % ref_table)
    print("  ref_row 조회 건수    : %d 행" % stat_total)
    print("  source_file 성공     : %d 건" % stat_ok)
    print("  source_file 없음     : %d 건" % stat_skip)
    print("  파일 오픈 오류       : %d 건" % stat_err)
    print("  쿼리 추출 없음       : %d 건" % stat_no_query)
    print("-" * 70)
    print("  [파일1] cols 파싱 결과")
    print("    저장 경로          : %s" % csv_cols_path)
    print("    레코드 수          : %d 건" % len(cols_buffer))
    print("  [파일2] query_text 추출 결과")
    print("    저장 경로          : %s" % csv_query_path)
    print("    레코드 수          : %d 건" % len(query_buffer))
    print("  [파일3] 정밀 매칭 분석 결과")
    print("    저장 경로          : %s" % csv_match_path)
    print("    레코드 수          : %d 건" % len(match_buffer))
    print("  [파일4] 코드 변환 매칭 결과")
    print("    저장 경로          : %s" % csv_enc_path)
    print("    레코드 수          : %d 건" % len(enc_buffer))
    print("-" * 70)
    if use_db:
        print("  [파일1] DB 테이블    : %s (적재: %d건)" % (tbl_names["cols_fq"], cols_inserted)) if not cols_err else print("  [파일1] DB 적재      : 실패 (%s)" % cols_err)
        print("  [파일2] DB 테이블    : %s (적재: %d건)" % (tbl_names["query_fq"], query_inserted)) if not query_err else print("  [파일2] DB 적재      : 실패 (%s)" % query_err)
        print("  [파일3] DB 테이블    : %s (적재: %d건)" % (tbl_names["match_fq"], match_inserted)) if not match_err else print("  [파일3] DB 적재      : 실패 (%s)" % match_err)
        print("  [파일4] DB 테이블    : %s (적재: %d건)" % (tbl_names["enc_fq"], enc_inserted)) if not enc_err else print("  [파일4] DB 적재      : 실패 (%s)" % enc_err)
    else:
        print("  DB 적재              : 생략 (--db 옵션 미지정)")
    print("=" * 70)
    print("[INFO] 모든 공정이 정상 처리 완료되었습니다.\n")


if __name__ == "__main__":
    main()