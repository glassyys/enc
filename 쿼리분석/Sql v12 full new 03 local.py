#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# Sql v12 full new 03 local.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001_local (2026-06-12)
#   [신규] sql_v12_full_new_02.py 의 로컬 실행 버전
# v002_local (2026-06-29)
#   - 결과 테이블 명명규칙을 프로그램명이 아닌 p190872_ 접두사 형식으로 고정
#   - 검색기준 복사본 파일명에 p190872_ 접두사 고정 적용 및 날짜/시간(timestamp) 제거
#   - 추출한 쿼리 원본 정보 수집 기능 추가:
#     * 쿼리 원본 보관: 테이블 p190872_{last_dir}_{mode}_sql 및 out/p190872_{last_dir}_{mode}_sql_{timestamp}.csv 생성 및 적재
#   - MySQL 패킷 및 세션 안정성 보완: 커서 버퍼링(buffered=True) 및 executemany 500건 청크 분할 삽입 적용
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
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}

# ============================================================
# MySQL 드라이버 동적 로드 (mysql-connector-python 우선, pymysql 폴백)
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
            "MySQL 드라이버가 없습니다. "
            "pip install pymysql 또는 pip install mysql-connector-python 을 설치하세요."
        )

def _get_cursor(conn):
    if _MYSQL_DRIVER == "connector":
        return conn.cursor(buffered=True)
    return conn.cursor()

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
# 서버 MySQL 테이블 조회 → 검색 기준 쌍 목록 반환
# 조회 칼럼: db_name, tbl_name, column_name, tobe_enc_key, tobe_enc_rsn
# ============================================================
def load_search_pairs_from_db(mysql_conf: dict, ref_table: str) -> tuple:
    pairs = []
    seen  = set()
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

        # 테이블 존재 여부 확인
        cursor.execute("SHOW TABLES LIKE '%s'" % ref_table.split(".")[-1])
        if not cursor.fetchone():
            return [], "테이블이 존재하지 않습니다: %s" % ref_table

        # 칼럼 존재 여부 확인 후 동적 SELECT 구성
        cursor.execute("SHOW COLUMNS FROM `%s`" % ref_table)
        existing_cols = {row[0].lower() for row in cursor.fetchall()}

        select_cols = []
        for col in ("db_name", "tbl_name", "column_name", "tobe_enc_key", "tobe_enc_rsn"):
            if col in existing_cols:
                select_cols.append("`%s`" % col)
            else:
                select_cols.append("NULL AS `%s`" % col)

        sql = "SELECT %s FROM `%s`" % (", ".join(select_cols), ref_table)
        cursor.execute(sql)
        rows = cursor.fetchall()

        for row in rows:
            db_name  = (row[0] or "").strip()
            tbl      = (row[1] or "").strip()
            col      = (row[2] or "").strip()
            enc_key  = (row[3] or "").strip()
            enc_rsn  = (row[4] or "").strip()
            if tbl and col:
                key = (tbl.upper(), col.upper())
                if key not in seen:
                    seen.add(key)
                    pairs.append({
                        "db_name":      db_name,
                        "tbl_name":     tbl,
                        "column_name":  col,
                        "tobe_enc_key": enc_key,
                        "tobe_enc_rsn": enc_rsn,
                    })

        return pairs, None

    except Exception as e:
        return [], "DB 조회 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


# ============================================================
# 결과 적재용 DDL / INSERT SQL (매칭 결과 테이블)
# ============================================================
_DDL_DROP_COL_MATCH = "DROP TABLE IF EXISTS `{table}`;"

_DDL_CREATE_COL_MATCH = """
CREATE TABLE `{table}` (
  `id`              BIGINT        NOT NULL AUTO_INCREMENT    COMMENT '자동증가 PK',
  `run_id`          VARCHAR(30)   NOT NULL                   COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `base_directory`  VARCHAR(500)  NOT NULL                   COMMENT '소스파일 디렉토리 경로',
  `file_name`       VARCHAR(500)  NOT NULL                   COMMENT '파일명',
  `dir_file`        TEXT          NOT NULL                   COMMENT '소스파일 전체경로',
  `crud_type`       VARCHAR(1)    NULL                       COMMENT 'C/R/U/D',
  `sql_type`        VARCHAR(30)   NULL                       COMMENT 'INSERT/SELECT/UPDATE/...',
  `db_name`         VARCHAR(200)  NULL                       COMMENT '기준 테이블의 DB명',
  `tbl_name`        VARCHAR(500)  NOT NULL                   COMMENT '기준 테이블의 tbl_name 값',
  `column_name`     VARCHAR(500)  NOT NULL                   COMMENT '기준 테이블의 column_name 값',
  `matched_table`   VARCHAR(500)  NOT NULL                   COMMENT '매칭된 테이블명 (원본명)',
  `matched_column`  VARCHAR(500)  NOT NULL                   COMMENT '매칭된 칼럼명 (원본명)',
  `match_type`      VARCHAR(10)   NULL                       COMMENT 'SOURCE/TARGET (매칭된 위치)',
  `line_number`     INT           NULL                       COMMENT '소스파일 전체 기준 절대 행번호',
  `matched_line`    TEXT          NULL                       COMMENT '칼럼이 발견된 라인 내용',
  `tobe_enc_key`    VARCHAR(200)  NULL                       COMMENT '기준 테이블의 tobe_enc_key 값',
  `tobe_enc_rsn`    VARCHAR(500)  NULL                       COMMENT '기준 테이블의 tobe_enc_rsn 값',
  `op_dtm`          DATETIME      NOT NULL                   COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`        (`run_id`),
  KEY `idx_file`          (`file_name`(191)),
  KEY `idx_tbl_name`      (`tbl_name`(191)),
  KEY `idx_column_name`   (`column_name`(191)),
  KEY `idx_matched_table` (`matched_table`(191)),
  KEY `idx_enc_key`       (`tobe_enc_key`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='로컬 소스 테이블+칼럼 매칭 결과 (MySQL 테이블 기준 검색)';
"""

_SQL_INSERT_COL_MATCH = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file,
   crud_type, sql_type,
   db_name, tbl_name, column_name,
   matched_table, matched_column,
   match_type, line_number, matched_line,
   tobe_enc_key, tobe_enc_rsn,
   op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

COL_MATCH_FIELDNAMES = [
    "base_directory", "file_name", "dir_file",
    "crud_type", "sql_type",
    "db_name", "tbl_name", "column_name",
    "matched_table", "matched_column",
    "match_type", "line_number", "matched_line",
    "tobe_enc_key", "tobe_enc_rsn",
    "op_dtm",
]

# ============================================================
# 결과 적재용 DDL / INSERT SQL (추출 쿼리 원본 테이블)
# ============================================================
_DDL_DROP_SQL = "DROP TABLE IF EXISTS `{table}`;"

_DDL_CREATE_SQL = """
CREATE TABLE `{table}` (
  `id`              BIGINT        NOT NULL AUTO_INCREMENT    COMMENT '자동증가 PK',
  `run_id`          VARCHAR(30)   NOT NULL                   COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `base_directory`  VARCHAR(500)  NOT NULL                   COMMENT '소스파일 디렉토리 경로',
  `file_name`       VARCHAR(500)  NOT NULL                   COMMENT '파일명',
  `dir_file`        TEXT          NOT NULL                   COMMENT '소스파일 전체경로',
  `query_seq`       INT           NOT NULL                   COMMENT '쿼리 일련번호',
  `start_line_no`   INT           NULL                       COMMENT '쿼리 시작 라인번호',
  `query_text`      LONGTEXT      NULL                       COMMENT '쿼리 원본 내용',
  `op_dtm`          DATETIME      NOT NULL                   COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`        (`run_id`),
  KEY `idx_file`          (`file_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='로컬 소스 추출 쿼리 원본 보관';
"""

_SQL_INSERT_SQL = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file,
   query_seq, start_line_no, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s)
"""

SQL_FIELDNAMES = [
    "base_directory", "file_name", "dir_file",
    "query_seq", "start_line_no", "query_text", "op_dtm"
]

# ============================================================
# 동적 테이블명 생성
# ============================================================
def build_col_match_table_name(source_dir: str, mode: str) -> str:
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return "p190872_%s_%s_col_match" % (last_dir, mode.lower())

def build_sql_table_name(source_dir: str, mode: str) -> str:
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return "p190872_%s_%s_sql" % (last_dir, mode.lower())


# ============================================================
# DB: DROP → CREATE → INSERT (매칭 결과 적재)
# ============================================================
def db_insert_col_match_all(col_match_buffer: list, run_id: str, op_dtm: str,
                             mysql_conf: dict, source_dir: str, mode: str) -> tuple:
    table_name = build_col_match_table_name(source_dir, mode)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

        cursor.execute(_DDL_DROP_COL_MATCH.format(table=table_name))
        conn.commit()

        cursor.execute(_DDL_CREATE_COL_MATCH.format(table=table_name))
        conn.commit()

        batch = []
        for r in col_match_buffer:
            batch.append((
                run_id,
                r["base_directory"],  r["file_name"],    r["dir_file"],
                r["crud_type"],       r["sql_type"],
                r["db_name"],
                r["tbl_name"],        r["column_name"],
                r["matched_table"],   r["matched_column"],
                r["match_type"],
                r["line_number"],
                r["matched_line"],
                r["tobe_enc_key"],    r["tobe_enc_rsn"],
                op_dtm,
            ))
            
        if batch:
            chunk_size = 500
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i:i+chunk_size]
                cursor.executemany(_SQL_INSERT_COL_MATCH.format(table=table_name), chunk)
                conn.commit()

        inserted = len(batch)
        return inserted, None

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


# ============================================================
# DB: DROP → CREATE → INSERT (추출 쿼리 원본 적재)
# ============================================================
def db_insert_sql_all(sql_buffer: list, run_id: str, op_dtm: str,
                      mysql_conf: dict, source_dir: str, mode: str) -> tuple:
    table_name = build_sql_table_name(source_dir, mode)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

        cursor.execute(_DDL_DROP_SQL.format(table=table_name))
        conn.commit()

        cursor.execute(_DDL_CREATE_SQL.format(table=table_name))
        conn.commit()

        batch = []
        for r in sql_buffer:
            batch.append((
                run_id,
                r["base_directory"],  r["file_name"],    r["dir_file"],
                r["query_seq"],
                r["start_line_no"],
                r["query_text"],
                op_dtm,
            ))
            
        if batch:
            chunk_size = 500
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i:i+chunk_size]
                cursor.executemany(_SQL_INSERT_SQL.format(table=table_name), chunk)
                conn.commit()

        inserted = len(batch)
        return inserted, None

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


# ============================================================
# CSV 저장 (매칭 결과)
# ============================================================
def save_col_match_csv(col_match_buffer: list, source_dir: str,
                       op_dtm: str, mode: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir  = os.path.basename(os.path.normpath(source_dir))
    timestamp = op_dtm.replace("-", "").replace(" ", "_").replace(":", "")
    csv_file  = "p190872_%s_%s_col_match_%s.csv" % (
        last_dir, mode.lower(), timestamp
    )
    csv_path  = os.path.join(OUT_DIR, csv_file)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COL_MATCH_FIELDNAMES)
        writer.writeheader()
        for r in col_match_buffer:
            row = dict(r)
            row["op_dtm"] = op_dtm
            writer.writerow(row)

    return csv_path


# ============================================================
# CSV 저장 (추출 쿼리 원본)
# ============================================================
def save_sql_csv(sql_buffer: list, source_dir: str,
                  op_dtm: str, mode: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir  = os.path.basename(os.path.normpath(source_dir))
    timestamp = op_dtm.replace("-", "").replace(" ", "_").replace(":", "")
    csv_file  = "p190872_%s_%s_sql_%s.csv" % (
        last_dir, mode.lower(), timestamp
    )
    csv_path  = os.path.join(OUT_DIR, csv_file)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SQL_FIELDNAMES)
        writer.writeheader()
        for r in sql_buffer:
            row = dict(r)
            row["op_dtm"] = op_dtm
            writer.writerow(row)

    return csv_path


# ============================================================
# 정규식 / 상수 (sql_v12_full_new_02.py 참조)
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
END_IF_PATTERN   = re.compile(r"^\s*END\s+IF\b",  re.IGNORECASE)
INNER_DML_RE     = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|REPLACE|ALTER)\b",
    re.IGNORECASE
)


# ============================================================
# 전처리 (주석 제거, 문자열 리터럴 유지)
# ============================================================
def preprocess(content: str) -> str:
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


# ============================================================
# EXECUTE IMMEDIATE 내부 SQL 추출
# ============================================================
def extract_execute_immediate(content: str) -> list:
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


# ============================================================
# 소스 파일에서 쿼리 추출
# 반환: (queries_with_offset, total_lines, orig_lines)
#   queries_with_offset: list of (query_str, raw_query_str, start_line_no)
#   start_line_no: 파일 전체 기준 쿼리 시작 1-based 라인번호
# ============================================================
def extract_queries_from_file(file_path: str) -> tuple:
    queries_with_offset = []
    total_lines         = 0
    orig_lines          = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        orig_lines  = raw.splitlines()
        total_lines = len(orig_lines)
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

                queries_with_offset.append((query, query, start_line_no))
            pos = end

        # EXECUTE IMMEDIATE 쿼리 (라인번호 특정 불가 → None)
        for ei_q in ei_queries:
            queries_with_offset.append((ei_q, ei_q, None))

    except Exception:
        pass
    return queries_with_offset, total_lines, orig_lines


# ============================================================
# SQL TYPE / CRUD TYPE 감지
# ============================================================
def detect_real_sql_type(query: str) -> str:
    q     = query.strip().upper()
    words = q.split()
    first = words[0] if words else "UNKNOWN"

    if first in ("DECLARE", "BEGIN"):
        m = INNER_DML_RE.search(query)
        return m.group(1).upper() if m else "UNKNOWN"
    if first == "WITH":
        if re.search(r"\bINSERT\b", q): return "INSERT"
        if re.search(r"\bUPDATE\b", q): return "UPDATE"
        if re.search(r"\bDELETE\b", q): return "DELETE"
        if re.search(r"\bMERGE\b",  q): return "MERGE"
        return "SELECT"
    if first == "CREATE": return "CREATE"
    if first == "DROP":   return "DROP"
    if first == "SELECT": return "SELECT"
    return first


def classify_crud_type(sql_type: str) -> str:
    u = sql_type.upper()
    if u in ("CREATE", "INSERT", "MERGE", "REPLACE", "UPSERT", "EXECUTE"):
        return "C"
    elif u == "SELECT":
        return "R"
    elif u in ("UPDATE", "ALTER"):
        return "U"
    elif u in ("DELETE", "DROP", "TRUNCATE"):
        return "D"
    return "R"


# ============================================================
# 테이블명 정제
# ============================================================
def clean_table(name: str):
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


# ============================================================
# 파싱 헬퍼
# ============================================================
def strip_inline_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def remove_string_literals(sql: str) -> str:
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r'"[^"]*"', '""', sql)
    return sql


def extract_paren_content(sql: str, start: int) -> tuple:
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


def strip_select_columns(sql: str) -> str:
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


def strip_update_set(sql: str) -> str:
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


def strip_insert_col_list(sql: str) -> str:
    pattern = re.compile(
        r"(INSERT\s+(?:OVERWRITE\s+)?(?:TABLE\s+)?[\w${}.\-]+)"
        r"(\s*\([^)]*\))"
        r"(\s*(?:WITH|SELECT|VALUES)\b)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(r"\1 __INSERT_COLS__\3", sql)


def strip_function_args(sql: str) -> str:
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


# ============================================================
# CTE 분석
# ============================================================
def extract_cte_map(query: str) -> dict:
    cte_map = {}
    query   = strip_inline_comments(query)
    if "WITH" not in query.upper():
        return cte_map
    with_m = re.search(r"\bWITH\b", query, re.IGNORECASE)
    if not with_m:
        return cte_map

    pos    = with_m.end()
    length = len(query)
    q_up   = query.upper()
    DML_KW = {"SELECT","INSERT","UPDATE","DELETE","MERGE"}

    while pos < length:
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        alias_m = re.match(r"(\w+)", query[pos:])
        if not alias_m:
            break
        alias    = alias_m.group(1)
        alias_up = alias.upper()
        if alias_up in DML_KW:
            break
        pos += alias_m.end()
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        if not re.match(r"\bAS\b", q_up[pos:], re.IGNORECASE):
            break
        pos += 2
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length or query[pos] != "(":
            break
        inner, end_pos = extract_paren_content(query, pos)
        pos = end_pos + 1
        cte_map[alias_up] = extract_sources_recursive(inner)
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        if query[pos] == ",":
            pos += 1
            continue
        break
    return cte_map


# ============================================================
# SET 절 서브쿼리 소스 추출
# ============================================================
def _extract_sources_from_set_subqueries(sql: str) -> set:
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
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bWHEN\b", up)
                        or re.match(r"\bON\b", up) or re.match(r"\bFROM\b", up)
                        or ch == ";"):
                    break
            j += 1
    return sources


# ============================================================
# 소스 테이블 추출 (재귀)
# ============================================================
def extract_sources_recursive(query: str) -> set:
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


# ============================================================
# 타겟 테이블 추출
# ============================================================
def extract_target_tables(query: str) -> set:
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
# TEMP REGSISTRY 수집
# ============================================================
def build_temp_registry(source_dir: str) -> set:
    temp_set = set()
    for root, _, files in os.walk(source_dir):
        for file in files:
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue
            full_path = os.path.join(root, file)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                for m in TEMP_CREATE_PAT.finditer(preprocess(raw)):
                    name = clean_table(m.group(1))
                    if name:
                        temp_set.add(name.upper())
            except Exception:
                pass
    return temp_set


# ============================================================
# 테이블+칼럼 매칭 로직
# ============================================================
def build_col_match_rows(
    query_text: str,
    sources: set,
    targets: set,
    crud_type: str,
    sql_type: str,
    base_directory: str,
    file_name: str,
    dir_file: str,
    search_pairs: list,
    compiled_col_patterns: dict,
    query_start_line_no,
    orig_lines: list = None,
) -> list:
    results = []
    seen    = set()

    src_upper = {s.upper() for s in sources if s}
    tgt_upper = {t.upper() for t in targets if t}

    query_lines = query_text.splitlines()

    for pair in search_pairs:
        tbl     = pair["tbl_name"]
        col     = pair["column_name"]
        db_name = pair.get("db_name", "")
        enc_k   = pair.get("tobe_enc_key", "")
        enc_rsn = pair.get("tobe_enc_rsn", "")
        tbl_up  = tbl.upper()
        col_up  = col.upper()

        # 테이블 일치 확인 (target 우선, 없으면 source)
        match_type = None
        if tbl_up in tgt_upper:
            match_type = "TARGET"
        elif tbl_up in src_upper:
            match_type = "SOURCE"

        if match_type is None:
            continue

        # 칼럼 완전일치(\b단어\b) 확인
        rx = compiled_col_patterns.get(col_up)
        if rx is None:
            try:
                rx = re.compile(r"\b%s\b" % re.escape(col), re.IGNORECASE)
                compiled_col_patterns[col_up] = rx
            except Exception:
                continue

        if not rx.search(query_text):
            continue

        # 중복 제거
        dedup_key = (tbl_up, col_up, match_type)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # 파일 전체 기준 절대 행번호 산출
        matched_line    = ""
        line_number     = None

        if query_start_line_no is not None and orig_lines:
            start_idx = query_start_line_no - 1
            for idx in range(start_idx, len(orig_lines)):
                if rx.search(orig_lines[idx]):
                    line_number  = idx + 1
                    matched_line = orig_lines[idx].strip()
                    break
        else:
            # fallback: 쿼리 내 상대 위치
            for line in query_lines:
                if rx.search(line):
                    matched_line = line.strip()
                    break

        results.append({
            "base_directory": base_directory,
            "file_name":      file_name,
            "dir_file":       dir_file,
            "crud_type":      crud_type,
            "sql_type":       sql_type,
            "db_name":        db_name,
            "tbl_name":       tbl,
            "column_name":    col,
            "matched_table":  tbl,
            "matched_column": col,
            "match_type":     match_type,
            "line_number":    line_number,
            "matched_line":   matched_line,
            "tobe_enc_key":   enc_k,
            "tobe_enc_rsn":   enc_rsn,
        })

    return results


# ============================================================
# 인수 파싱
# ============================================================
def parse_args() -> tuple:
    args      = sys.argv[1:]
    src_dir   = None
    ref_table = None
    mode      = "SIMPLE"
    use_db    = False
    conf_path = None

    i = 0
    while i < len(args):
        if args[i] == "--mode":
            if i + 1 < len(args):
                mode = args[i + 1].upper()
                if mode not in ("SIMPLE", "DETAIL"):
                    print("[오류] --mode 값은 SIMPLE 또는 DETAIL 이어야 합니다.")
                    sys.exit(1)
                i += 2
            else:
                print("[오류] --mode 다음에 SIMPLE 또는 DETAIL 을 지정하세요.")
                sys.exit(1)
        elif args[i] == "--db":
            use_db = True
            i += 1
        elif args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]
                i += 2
            else:
                print("[오류] --conf 다음에 mysql.conf 파일 경로를 지정하세요.")
                sys.exit(1)
        else:
            if src_dir is None:
                src_dir = args[i]
            elif ref_table is None:
                ref_table = args[i]
            i += 1

    if src_dir is None or ref_table is None:
        print("사용법: python3 %s.py <검색대상_디렉토리> <검색기준테이블> "
              "[--mode SIMPLE|DETAIL] [--db] [--conf mysql.conf 경로]" % PROGRAM_NAME)
        print("")
        print("예시:")
        print("  python3 %s.py D:\\source enc_target_columns --mode SIMPLE" % PROGRAM_NAME)
        print("  python3 %s.py D:\\source enc_target_columns --mode SIMPLE --db" % PROGRAM_NAME)
        print("  python3 %s.py /NAS/MIDP/SRC enc_target_columns --mode DETAIL --db "
              "--conf /home/user/mysql.conf" % PROGRAM_NAME)
        sys.exit(1)

    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        print("[오류] 유효한 디렉토리가 아닙니다: %s" % src_dir)
        sys.exit(1)

    return src_dir, ref_table, mode, use_db, conf_path


# ============================================================
# MAIN
# ============================================================
def main():
    src_dir, ref_table, mode, use_db, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [로컬 소스 테이블+칼럼 매칭 탐색 시작]")
    print("=" * 70)
    print("  검색 대상 디렉토리 : %s" % src_dir)
    print("  검색 기준 테이블   : %s" % ref_table)
    print("  실행 모드          : %s" % mode)
    print("  처리일시 (op_dtm)  : %s" % op_dtm)
    print("  실행 ID (run_id)   : %s" % run_id)
    print("  DB 적재 여부       : %s" % ("YES (--db)" if use_db else "NO  (파일만 생성)"))
    print("-" * 70)

    # ── DB 드라이버 / mysql.conf 확인 ───────────────────────────────
    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다.")
        print("        pip install pymysql  또는  pip install mysql-connector-python")
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

    # ── 서버 MySQL 테이블 조회 → 검색 기준 쌍 로드 ──────────────────
    print("[INFO] 서버 MySQL 테이블 조회 중: %s.%s ..."
          % (mysql_conf.get("database"), ref_table))
    search_pairs, db_err = load_search_pairs_from_db(mysql_conf, ref_table)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not search_pairs:
        print("[ERROR] 조회된 (tbl_name, column_name) 쌍이 없습니다.")
        sys.exit(1)

    print("[INFO] 조회 완료: %d 쌍  (tbl_name + column_name 기준 중복 제거)" % len(search_pairs))
    
    # 2026-06-29: 화면 출력 기준 목록 주석 처리 완료
    # print("[INFO] 검색 기준 목록:")
    # for idx, pair in enumerate(search_pairs, 1):
    #     print("       %3d. tbl=%-40s col=%-30s enc_key=%s" % (
    #         idx,
    #         pair["tbl_name"],
    #         pair["column_name"],
    #         pair.get("tobe_enc_key", ""),
    #     ))
    # print("-" * 70)

    # in/ 디렉토리에 검색 기준 복사본 저장 (p190872 접두사 적용 및 프로그램명 & 날짜/시간 제거)
    os.makedirs(IN_DIR, exist_ok=True)
    last_dir   = os.path.basename(os.path.normpath(src_dir))
    in_csv_name = "p190872_%s_search_input.csv" % last_dir
    in_csv_path = os.path.join(IN_DIR, in_csv_name)
    try:
        with open(in_csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=["db_name", "tbl_name", "column_name",
                               "tobe_enc_key", "tobe_enc_rsn"]
            )
            writer.writeheader()
            writer.writerows(search_pairs)
        print("[INFO] 검색 기준 복사본 저장: %s" % in_csv_path)
    except Exception as e:
        print("[WARN] in/ 디렉토리 저장 실패 (계속 진행): %s" % str(e))
    print("-" * 70)

    # ── 칼럼 정규표현식 사전 컴파일 ─────────────────────────────────
    compiled_col_patterns = {}
    for pair in search_pairs:
        col_up = pair["column_name"].upper()
        if col_up not in compiled_col_patterns:
            try:
                compiled_col_patterns[col_up] = re.compile(
                    r"\b%s\b" % re.escape(pair["column_name"]), re.IGNORECASE
                )
            except Exception:
                pass

    # ── TEMP 테이블 레지스트리 수집 ──────────────────────────────────
    print("[INFO] TEMP 테이블 레지스트리 수집 중 ...")
    temp_registry = build_temp_registry(src_dir)
    print("[INFO] TEMP 테이블 수집 완료: %d 개" % len(temp_registry))
    print("-" * 70)

    # ── 소스 파일 탐색 및 매칭 ───────────────────────────────────────
    print("[INFO] 소스 파일 탐색 및 쿼리 매칭 시작 ...")

    col_match_buffer  = []
    sql_buffer        = []   # 파싱된 쿼리 원본 보관용 버퍼
    total_files       = 0
    total_queries     = 0
    total_file_lines  = 0
    file_match_counts = {}   # 파일별 매칭 건수 (요약용)

    for root, _, files in os.walk(src_dir):
        for file in sorted(files):
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue
            total_files   += 1
            full_path      = os.path.join(root, file)
            base_directory = os.path.abspath(root)

            queries_with_offset, file_lines, orig_lines = extract_queries_from_file(full_path)
            total_file_lines += file_lines
            total_queries    += len(queries_with_offset)

            file_match_cnt = 0
            query_seq      = 0
            for query, raw_query, query_start_line_no in queries_with_offset:
                query_seq += 1
                sql_type  = detect_real_sql_type(query)
                crud_type = classify_crud_type(sql_type)
                sources   = extract_sources_recursive(query)
                targets   = extract_target_tables(query)

                # 파싱된 모든 쿼리 정보를 sql_buffer에 기록
                sql_buffer.append({
                    "base_directory": base_directory,
                    "file_name":      file,
                    "dir_file":       full_path,
                    "query_seq":      query_seq,
                    "start_line_no":  query_start_line_no if query_start_line_no is not None else 1,
                    "query_text":     raw_query,
                    "op_dtm":         op_dtm
                })

                cm_rows = build_col_match_rows(
                    query_text            = raw_query,
                    sources               = sources,
                    targets               = targets,
                    crud_type             = crud_type,
                    sql_type              = sql_type,
                    base_directory        = base_directory,
                    file_name             = file,
                    dir_file              = full_path,
                    search_pairs          = search_pairs,
                    compiled_col_patterns = compiled_col_patterns,
                    query_start_line_no   = query_start_line_no,
                    orig_lines            = orig_lines,
                )
                if cm_rows:
                    col_match_buffer.extend(cm_rows)
                    file_match_cnt += len(cm_rows)

            if file_match_cnt > 0:
                file_match_counts[full_path] = file_match_cnt

    print("[INFO] 소스 탐색 완료:")
    print("  - 스캔한 파일 수   : %8d 개  (확장자: %s)" % (
        total_files, ", ".join(sorted(TARGET_EXTENSIONS))))
    print("  - 추출한 쿼리 수   : %8d 건" % total_queries)
    print("  - 총 파일 라인 수  : %8d 줄" % total_file_lines)
    print("  - 매칭 결과 건수   : %8d 건" % len(col_match_buffer))
    print("  - 추출 수집 쿼리 수: %8d 건" % len(sql_buffer))
    print("-" * 70)

    # ── 결과 CSV 저장 ────────────────────────────────────────────────
    if col_match_buffer:
        print("[INFO] 매칭 결과 CSV 파일 저장 중 (%s) ..." % OUT_DIR)
        try:
            csv_output_path = save_col_match_csv(col_match_buffer, src_dir, op_dtm, mode)
            print("[INFO] CSV 파일 저장 완료: %s" % csv_output_path)
            print("  - 저장 레코드 수   : %d 건" % len(col_match_buffer))
        except Exception as e:
            print("[ERROR] CSV 저장 실패: %s" % str(e))
            sys.exit(1)
    else:
        print("[WARN] 매칭 결과가 없으나, 프로세스 계속 진행 및 쿼리 원본을 저장합니다.")
        csv_output_path = "N/A"
    print("-" * 70)

    # ── 쿼리 원본 CSV 저장 ────────────────────────────────────────────
    if sql_buffer:
        print("[INFO] 쿼리 원본 CSV 파일 저장 중 (%s) ..." % OUT_DIR)
        try:
            sql_output_path = save_sql_csv(sql_buffer, src_dir, op_dtm, mode)
            print("[INFO] CSV 파일 저장 완료: %s" % sql_output_path)
            print("  - 저장 레코드 수   : %d 건" % len(sql_buffer))
        except Exception as e:
            print("[ERROR] 쿼리 원본 CSV 저장 실패: %s" % str(e))
            sys.exit(1)
    else:
        sql_output_path = "N/A"
    print("-" * 70)

    # ── 매칭 파일 목록 출력 ──────────────────────────────────────────
    if file_match_counts:
        print("[INFO] 매칭된 소스 파일 목록:")
        for fpath, cnt in sorted(file_match_counts.items()):
            print("  - %-60s  (%d 건)" % (fpath, cnt))
        print("-" * 70)

    # ── DB 적재 (--db 옵션) ──────────────────────────────────────────
    db_inserted = 0
    db_err_msg  = None
    db_table    = build_col_match_table_name(src_dir, mode)

    db_sql_inserted = 0
    db_sql_err_msg  = None
    db_sql_table    = build_sql_table_name(src_dir, mode)

    if use_db:
        print("[INFO] MySQL 매칭 결과 테이블 적재 시작: %s.%s ..."
              % (mysql_conf.get("database"), db_table))
        if col_match_buffer:
            db_inserted, db_err_msg = db_insert_col_match_all(
                col_match_buffer, run_id, op_dtm, mysql_conf, src_dir, mode
            )
            if db_err_msg:
                print("[ERROR] DB 적재 실패: %s" % db_err_msg)
            else:
                print("[INFO] DB 적재 완료: %d 건" % db_inserted)
        else:
            print("[WARN] 적재할 매칭 결과 데이터가 없습니다.")
        print("-" * 70)

        print("[INFO] MySQL 쿼리 원본 테이블 적재 시작: %s.%s ..."
              % (mysql_conf.get("database"), db_sql_table))
        if sql_buffer:
            db_sql_inserted, db_sql_err_msg = db_insert_sql_all(
                sql_buffer, run_id, op_dtm, mysql_conf, src_dir, mode
            )
            if db_sql_err_msg:
                print("[ERROR] DB 쿼리 원본 적재 실패: %s" % db_sql_err_msg)
            else:
                print("[INFO] DB 쿼리 원본 적재 완료: %d 건" % db_sql_inserted)
        else:
            print("[WARN] 적재할 쿼리 데이터가 없습니다.")
        print("-" * 70)
    else:
        print("[INFO] --db 옵션이 지정되지 않아 DB 적재는 생략되었습니다.")

    # ── 최종 결과 요약 ───────────────────────────────────────────────
    print("=" * 70)
    print(" 로컬 소스 테이블+칼럼 매칭 탐색 성공 완료")
    print("=" * 70)
    print("  실행 모드            : %s" % mode)
    print("  처리일시             : %s" % op_dtm)
    print("  run_id (실행 ID)     : %s" % run_id)
    print("  검색 기준 테이블     : %s.%s" % (mysql_conf.get("database"), ref_table))
    print("  검색 기준 쌍 수      : %d 건" % len(search_pairs))
    print("  스캔 파일 수         : %d 개" % total_files)
    print("  추출 쿼리 수         : %d 건" % total_queries)
    print("  총 파일 라인 수      : %d 줄" % total_file_lines)
    print("  매칭 결과 건수       : %d 건" % len(col_match_buffer))
    print("  추출 수집 쿼리 수    : %d 건" % len(sql_buffer))
    print("  저장 매칭 CSV 파일   : %s" % csv_output_path)
    print("  저장 쿼리 CSV 파일   : %s" % sql_output_path)
    print("-" * 70)
    if use_db:
        if db_err_msg:
            print("  DB 매칭 적재         : 실패")
            print("  DB 매칭 오류 내용    : %s" % db_err_msg)
        else:
            print("  DB 매칭 적재         : 성공")
            print("  DB 매칭 테이블       : %s.%s" % (mysql_conf.get("database"), db_table))
            print("  DB 매칭 적재 건수    : %d 건" % db_inserted)
        
        if db_sql_err_msg:
            print("  DB 쿼리 적재         : 실패")
            print("  DB 쿼리 오류 내용    : %s" % db_sql_err_msg)
        else:
            print("  DB 쿼리 적재         : 성공")
            print("  DB 쿼리 테이블       : %s.%s" % (mysql_conf.get("database"), db_sql_table))
            print("  DB 쿼리 적재 건수    : %d 건" % db_sql_inserted)
    else:
        print("  DB 적재              : 생략 (--db 옵션 미지정)")
    print("=" * 70)
    print("[INFO] 모든 처리가 완료되었습니다.\n")


if __name__ == "__main__":
    main()
