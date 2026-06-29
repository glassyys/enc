#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_v12_full_new_04_local.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v004_local (2026-06-30)
#   - [--where] 옵션 추가 (old: asis_enc_yn='Y', new: asis_enc_yn='N')
#   - where 옵션 로직 기반 검색 기준 쪼개기 및 중복제거:
#     * tbl_name, column_name 조합으로 중복 제거하여 in/p190872_{last_dir}_search_input.csv 및
#       p190872_{last_dir}_search_input 테이블로 저장
#     * 중복제거 결과 및 최종 매칭 결과 출력물(CSV, DB) 모두에 where_opt(old/new/blank) 컬럼을 함께 남겨 추출
#   - 2단계 DB 연계 매칭 조회:
#     * 생성된 DB 쿼리 테이블(p190872_{last_dir}_{mode}_sql) 혹은 메모리 버퍼에서 query_text를 로드하여
#       중복제거된 (tbl_name, column_name) 쌍과 순환 매칭
#     * 최종적으로 매칭된 행만 out/p190872_{last_dir}_{mode}_col_match_{timestamp}.csv 파일 및
#       p190872_{last_dir}_{mode}_col_match 테이블에 저장 및 등록
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

# 검색기준테이블 원본 칼럼 목록
REF_TABLE_COLS = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 중복 제거된 검색기준 정보 보관용 스키마 칼럼 목록 (1단계 결과)
SEARCH_INPUT_FIELDNAMES = [
    "db_name", "tbl_name", "column_name", "tobe_enc_key", "tobe_enc_rsn", "where_opt", "op_dtm"
]

# 결과 CSV / DB 테이블 필드 순서 (2단계 매칭 최종 결과)
RESULT_FIELDNAMES = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols", "enc_col_cnt", "ins_cnt", "sel_cnt",
    "base_directory", "src_file_name", "dir_file",
    "crud_type", "sql_type", "match_type",
    "matched_col_name", "matched_col_key",
    "line_number", "matched_line",
    "where_opt",
    "op_dtm",
]

# ── 쿼리 원본 보관 CSV 필드 순서
SQL_FIELDNAMES = [
    "base_directory", "file_name", "dir_file",
    "query_seq", "start_line_no", "query_text", "op_dtm"
]

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
# cols 파싱: "col_01:k1,col_bb:k2" → [{"col_name":"col_01","col_key":"k1"}, ...]
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
# 서버 MySQL 검색기준테이블 조회 (where_opt 적용)
# ============================================================
def load_ref_rows_from_db(mysql_conf: dict, ref_table: str, where_opt: str = None) -> tuple:
    rows      = []
    conn      = None
    cursor    = None
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    fq_table  = make_fq(ref_schema, ref_tbl_only)

    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

        # 테이블 존재 여부 확인
        if ref_schema:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (ref_schema, ref_tbl_only)
            )
            row_chk = cursor.fetchone()
            exists  = (row_chk[0] > 0) if row_chk else False
        else:
            cursor.execute("SHOW TABLES LIKE %s", (ref_tbl_only,))
            row_chk = cursor.fetchone()
            exists  = True if row_chk else False
        if not exists:
            return [], ref_schema, "테이블이 존재하지 않습니다: %s" % ref_table

        # 실제 존재하는 칼럼 확인
        cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
        existing_cols = {row[0].lower() for row in cursor.fetchall()}

        # 동적 SELECT (없는 칼럼은 NULL AS col 로 처리)
        select_parts = []
        for col in REF_TABLE_COLS:
            if col in existing_cols:
                select_parts.append("`%s`" % col)
            else:
                select_parts.append("NULL AS `%s`" % col)
        
        # tobe_enc_key, tobe_enc_rsn, asis_enc_yn 가져오기
        for col in ("tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn"):
            if col not in REF_TABLE_COLS and col in existing_cols:
                select_parts.append("`%s`" % col)

        # where_opt 조건 필터
        where_conds = []
        if "tobe_enc_key" in existing_cols:
            where_conds.append("`tobe_enc_key` <> ''")
        
        if where_opt == "old" and "asis_enc_yn" in existing_cols:
            where_conds.append("`asis_enc_yn` = 'Y'")
        elif where_opt == "new" and "asis_enc_yn" in existing_cols:
            where_conds.append("`asis_enc_yn` = 'N'")

        where_clause = ""
        if where_conds:
            where_clause = "WHERE " + " AND ".join(where_conds)

        sql = "SELECT %s FROM %s %s ORDER BY tbl_name, no" % (
            ", ".join(select_parts), fq_table, where_clause
        )
        cursor.execute(sql)
        db_rows = cursor.fetchall()

        select_col_names = [p.replace("`", "") for p in select_parts]
        for db_row in db_rows:
            row_dict = {}
            for idx, col in enumerate(select_col_names):
                val = db_row[idx]
                col_key = col.split(" AS ")[-1].strip()
                row_dict[col_key] = str(val).strip() if val is not None else ""
            rows.append(row_dict)

        return rows, ref_schema, None

    except Exception as e:
        return [], ref_schema, "DB 조회 실패: %s" % str(e)
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


# ============================================================
# DB 테이블명 정의 함수군
# ============================================================
def build_search_input_table_name(source_dir: str) -> str:
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return "p190872_%s_search_input" % last_dir

def build_sql_table_name(source_dir: str, mode: str) -> str:
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return "p190872_%s_%s_sql" % (last_dir, mode.lower())

def build_result_table(source_dir: str, ref_schema: str) -> tuple:
    last_dir   = os.path.basename(os.path.normpath(source_dir))
    table_only = "p190872_%s_simple_col_match" % last_dir
    fq         = make_fq(ref_schema, table_only)
    return ref_schema, table_only, fq


# ============================================================
# DB: DROP → CREATE → INSERT (1단계: 중복제거 검색 기준 적재)
# ============================================================
def db_insert_search_input_all(unique_pairs: list, mysql_conf: dict, source_dir: str, op_dtm: str) -> tuple:
    table_name = build_search_input_table_name(source_dir)
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)
        
        cursor.execute("DROP TABLE IF EXISTS `%s`" % table_name)
        conn.commit()
        
        cursor.execute(f"""
        CREATE TABLE `{table_name}` (
          `id`           BIGINT       NOT NULL AUTO_INCREMENT,
          `db_name`      VARCHAR(200) NULL,
          `tbl_name`     VARCHAR(500) NOT NULL,
          `column_name`  VARCHAR(500) NOT NULL,
          `tobe_enc_key` VARCHAR(200) NULL,
          `tobe_enc_rsn` VARCHAR(1000) NULL,
          `where_opt`    VARCHAR(10)  NULL,
          `op_dtm`       DATETIME     NOT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_tbl_col` (`tbl_name`(191), `column_name`(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='중복제거된 검색기준 테이블 정보';
        """)
        conn.commit()
        
        batch = []
        for p in unique_pairs:
            batch.append((
                p["db_name"],
                p["tbl_name"],
                p["column_name"],
                p["tobe_enc_key"],
                p["tobe_enc_rsn"],
                p["where_opt"],
                op_dtm
            ))
            
        if batch:
            chunk_size = 500
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i:i+chunk_size]
                cursor.executemany(
                    f"INSERT INTO `{table_name}` (db_name, tbl_name, column_name, tobe_enc_key, tobe_enc_rsn, where_opt, op_dtm) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    chunk
                )
                conn.commit()
                
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

        cursor.execute("DROP TABLE IF EXISTS `%s`" % table_name)
        conn.commit()

        cursor.execute(f"""
        CREATE TABLE `{table_name}` (
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
        """)
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
                cursor.executemany(
                    f"INSERT INTO `{table_name}` (run_id, base_directory, file_name, dir_file, query_seq, start_line_no, query_text, op_dtm) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    chunk
                )
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
# DB: 적재된 SQL 테이블 데이터 조회
# ============================================================
def load_queries_from_sql_table(mysql_conf: dict, sql_table: str) -> list:
    conn = None
    cursor = None
    results = []
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)
        sql = "SELECT base_directory, file_name, dir_file, query_seq, start_line_no, query_text FROM `%s` ORDER BY file_name, query_seq" % sql_table
        cursor.execute(sql)
        rows = cursor.fetchall()
        for r in rows:
            results.append({
                "base_directory": r[0],
                "file_name": r[1],
                "dir_file": r[2],
                "query_seq": r[3],
                "start_line_no": r[4],
                "query_text": r[5]
            })
    except Exception as e:
        print("[WARN] DB sql 테이블 조회 실패 (메모리 버퍼로 대체 진행): %s" % str(e))
    finally:
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass
    return results


# ============================================================
# DB: DROP → CREATE → INSERT (최종 매칭 결과 적재)
# ============================================================
def db_insert_result_all(result_buffer: list, run_id: str, op_dtm: str,
                         mysql_conf: dict, source_dir: str,
                         ref_schema: str) -> tuple:
    _, _, fq_table = build_result_table(source_dir, ref_schema)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

        cursor.execute(_DDL_DROP_RESULT.format(table=fq_table))
        conn.commit()
        
        cursor.execute(f"""
        CREATE TABLE {fq_table} (
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
          `where_opt`        VARCHAR(10)   NULL                       COMMENT 'where 필터 옵션(old/new)',
          `op_dtm`           DATETIME      NOT NULL                   COMMENT '처리일시',
          PRIMARY KEY (`id`),
          KEY `idx_run_id`        (`run_id`),
          KEY `idx_tbl_name`      (`tbl_name`(191)),
          KEY `idx_src_file`      (`src_file_name`(191)),
          KEY `idx_matched_col`   (`matched_col_name`(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 테이블+칼럼 매칭 결과';
        """)
        conn.commit()

        batch = []
        for r in result_buffer:
            def to_int(v):
                try:
                    return int(v) if v not in (None, "") else None
                except Exception:
                    return None

            batch.append((
                run_id,
                r["db_name"],       r["tbl_name"],    r["operation"],
                to_int(r["no"]),    r["source_file"],
                r["process_yn"],    r["process_desc"], r["cols"],
                to_int(r["enc_col_cnt"]),
                to_int(r["ins_cnt"]),
                to_int(r["sel_cnt"]),
                r["base_directory"], r["src_file_name"], r["dir_file"],
                r["crud_type"],      r["sql_type"],       r["match_type"],
                r["matched_col_name"], r["matched_col_key"],
                r["line_number"],      r["matched_line"],
                r["where_opt"],
                op_dtm,
            ))

        if batch:
            chunk_size = 500
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i:i+chunk_size]
                cursor.executemany(_SQL_INSERT_RESULT.format(table=fq_table), chunk)
                conn.commit()

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


# ============================================================
# CSV 저장 (1단계: 중복제거 검색 기준)
# ============================================================
def save_search_input_csv(unique_pairs: list, source_dir: str, op_dtm: str) -> str:
    os.makedirs(IN_DIR, exist_ok=True)
    last_dir = os.path.basename(os.path.normpath(source_dir))
    csv_file = "p190872_%s_search_input.csv" % last_dir
    csv_path = os.path.join(IN_DIR, csv_file)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SEARCH_INPUT_FIELDNAMES)
        writer.writeheader()
        for p in unique_pairs:
            row = dict(p)
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
# CSV 저장 (최종 매칭 결과)
# ============================================================
def save_result_csv(result_buffer: list, source_dir: str, op_dtm: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir = os.path.basename(os.path.normpath(source_dir))
    csv_file = "p190872_%s_simple_col_match.csv" % last_dir
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
# 정규식 / 상수
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
    if u in ("CREATE", "INSERT", "MERGE", "REPLACE", "UPSERT", "EXECUTE"): return "C"
    elif u == "SELECT":   return "R"
    elif u in ("UPDATE", "ALTER"): return "U"
    elif u in ("DELETE", "DROP", "TRUNCATE"): return "D"
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
        if sql[i] == "(":   depth += 1
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
            result.append(sql[i:]); break
        sel_pos = i + m.start()
        result.append(sql[i:sel_pos])
        result.append("SELECT ")
        j = sel_pos + len("SELECT")
        depth = 0; found_from = False
        while j < length:
            ch = sql[j]
            if ch == "(":   depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0: break
            elif depth == 0:
                if re.match(r"\bFROM\b", sql_up[j:], re.IGNORECASE):
                    result.append("__COLS__ "); i = j; found_from = True; break
                if ch == ";":
                    result.append(sql[j:j+1]); i = j + 1; found_from = True; break
            j += 1
        if not found_from:
            result.append(sql[j:]); break
    return "".join(result)

def strip_update_set(sql: str) -> str:
    result = []
    i      = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r"\bSET\b", sql_up[i:])
        if not m:
            result.append(sql[i:]); break
        set_pos = i + m.start()
        result.append(sql[i:set_pos])
        result.append("SET ")
        j = set_pos + len("SET"); depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":   depth += 1
            elif ch == ")":
                if depth == 0: break
                depth -= 1
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bWHEN\b", up)
                        or re.match(r"\bON\b", up) or re.match(r"\bFROM\b", up)
                        or ch == ";"): break
            j += 1
        result.append("__SET__ "); i = j
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
        "FROM","JOIN","USING","WITH","ON","AS","SELECT","WHERE","HAVING","SET",
        "INSERT","UPDATE","DELETE","MERGE","CREATE","TABLE","VIEW","INTO",
        "WHEN","THEN","ELSE","AND","OR","NOT","EXISTS","IN","ANY","ALL","CASE"
    }
    while i < length:
        m = re.search(r"(\b\w+)\s*\(", sql_up[i:])
        if not m:
            result.append(sql[i:]); break
        fn_start    = i + m.start()
        fn_name     = m.group(1).upper()
        paren_start = i + m.end() - 1
        if fn_name in SKIP:
            result.append(sql[i:paren_start + 1]); i = paren_start + 1; continue
        if fn_start > 0 and sql[fn_start - 1] in (".", "}", "$"):
            result.append(sql[i:paren_start + 1]); i = paren_start + 1; continue
        result.append(sql[i:fn_start + len(m.group(1))])
        inner, end_pos = extract_paren_content(sql, paren_start)
        result.append("(__FUNC_ARGS__)"); i = end_pos + 1
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
        while pos < length and query[pos] in " \t\n\r": pos += 1
        if pos >= length: break
        alias_m = re.match(r"(\w+)", query[pos:])
        if not alias_m: break
        alias    = alias_m.group(1)
        alias_up = alias.upper()
        if alias_up in DML_KW: break
        pos += alias_m.end()
        while pos < length and query[pos] in " \t\n\r": pos += 1
        if pos >= length: break
        if not re.match(r"\bAS\b", q_up[pos:], re.IGNORECASE): break
        pos += 2
        while pos < length and query[pos] in " \t\n\r": pos += 1
        if pos >= length or query[pos] != "(": break
        inner, end_pos = extract_paren_content(query, pos)
        pos = end_pos + 1
        cte_map[alias_up] = extract_sources_recursive(inner)
        while pos < length and query[pos] in " \t\n\r": pos += 1
        if pos >= length: break
        if query[pos] == ",": pos += 1; continue
        break
    return cte_map


# ============================================================
# 소스 테이블 추출 (재귀)
# ============================================================
def _extract_sources_from_set_subqueries(sql: str) -> set:
    sources = set()
    sql_up  = sql.upper()
    length  = len(sql)
    for set_m in re.finditer(r"\bSET\b", sql_up):
        j = set_m.end(); depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
                if depth == 1:
                    inner, end_pos = extract_paren_content(sql, j)
                    inner_up = inner.upper()
                    if re.search(r"\bSELECT\b", inner_up) and re.search(r"\bFROM\b", inner_up):
                        sources.update(extract_sources_recursive(inner))
                    j = end_pos + 1; depth = 0; continue
                else: j += 1; continue
            elif ch == ")": depth = max(depth - 1, 0)
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bFROM\b", up)
                        or re.match(r"\bWHEN\b", up) or ch == ";"): break
            j += 1
    return sources

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
        "INNER","LEFT","RIGHT","FULL","CROSS","JOIN","FROM","USING"
    }
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
                token    = tok_m.group(1)
                token_up = token.upper().rstrip(",;")
                if token_up in CLAUSE_END: break
                tbl = clean_table(token)
                if tbl: sources.add(tbl)
                j += tok_m.end()
                alias_m = re.match(r"[\s]+([^\s,;()\n]+)", q[j:])
                if alias_m:
                    alias_word = alias_m.group(1).upper()
                    if alias_word not in CLAUSE_END and not alias_word.startswith(","): j += alias_m.end()
            while j < length and q[j] in " \t\n\r": j += 1
            if j < length and q[j] == ",": j += 1
            else: break
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
            if not raw or raw.upper() in POST_KW: continue
            tbl = clean_table(raw)
            if tbl: targets.add(tbl)
    return targets


# ============================================================
# TEMP 레지스트리 수집
# ============================================================
def build_temp_registry(source_dir: str) -> set:
    temp_set = set()
    for root, _, files in os.walk(source_dir):
        for file in files:
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)): continue
            full_path = os.path.join(root, file)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                for m in TEMP_CREATE_PAT.finditer(preprocess(raw)):
                    name = clean_table(m.group(1))
                    if name: temp_set.add(name.upper())
            except Exception: pass
    return temp_set


# ============================================================
# 결과 적재 DDL / INSERT SQL
# ============================================================
_DDL_DROP_RESULT = "DROP TABLE IF EXISTS {table};"

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (run_id,
   db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt,
   base_directory, src_file_name, dir_file,
   crud_type, sql_type, match_type,
   matched_col_name, matched_col_key,
   line_number, matched_line,
   where_opt,
   op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# ============================================================
# 인수 파싱
# ============================================================
def parse_args() -> tuple:
    args      = sys.argv[1:]
    src_dir   = None
    ref_table = None
    use_db    = False
    conf_path = None
    where_opt = None

    i = 0
    while i < len(args):
        if args[i] == "--db":
            use_db = True
            i += 1
        elif args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]
                i += 2
            else:
                print("[오류] --conf 다음에 mysql.conf 파일 경로를 지정하세요.")
                sys.exit(1)
        elif args[i] == "--where":
            if i + 1 < len(args):
                where_opt = args[i + 1].lower()
                if where_opt not in ("old", "new"):
                    print("[오류] --where 값은 old 또는 new 여야 합니다.")
                    sys.exit(1)
                i += 2
            else:
                print("[오류] --where 다음에 old 또는 new 를 지정하세요.")
                sys.exit(1)
        else:
            if src_dir is None:
                src_dir = args[i]
            elif ref_table is None:
                ref_table = args[i]
            i += 1

    if src_dir is None or ref_table is None:
        print("사용법: python3 %s.py <분석대상_디렉토리> <스키마.검색기준테이블> "
              "[--db] [--conf mysql.conf 경로] [--where old|new]" % PROGRAM_NAME)
        sys.exit(1)

    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        print("[오류] 유효한 디렉토리가 아닙니다: %s" % src_dir)
        sys.exit(1)

    return src_dir, ref_table, use_db, conf_path, where_opt


# ============================================================
# MAIN
# ============================================================
def main():
    src_dir, ref_table, use_db, conf_path, where_opt = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode   = "SIMPLE"

    print("=" * 70)
    print(" [로컬 소스 tbl_name + cols 칼럼 매칭 탐색 시작]")
    print("=" * 70)
    print("  분석 대상 디렉토리 : %s" % src_dir)
    print("  검색 기준 테이블   : %s" % ref_table)
    print("  where 필터 옵션    : %s" % (where_opt if where_opt else "(기본 적용: tobe_enc_key 필수)"))
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

    # ── 검색기준테이블 조회 (where_opt 적용) ──────────────────────────
    print("[INFO] 검색기준테이블 조회 중: %s ..." % ref_table)
    ref_rows, ref_schema, db_err = load_ref_rows_from_db(mysql_conf, ref_table, where_opt)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[ERROR] 검색기준테이블에서 조회된 데이터가 없습니다.")
        sys.exit(1)

    # ── 1단계: 검색 기준 정보 쪼개기 및 중복 제거 ──
    print("[INFO] 검색 기준 정보 분할 및 중복제거 진행 중 ...")
    seen_pairs = set()
    unique_pairs = []
    
    for r in ref_rows:
        db_name  = r.get("db_name", "")
        tbl_name = r.get("tbl_name", "")
        cols_str = r.get("cols", "")
        tobe_enc_key = r.get("tobe_enc_key", "")
        tobe_enc_rsn = r.get("tobe_enc_rsn", "")
        
        col_items = parse_cols(cols_str)
        for item in col_items:
            col_name = item["col_name"]
            col_key  = item["col_key"] if item["col_key"] else tobe_enc_key
            
            pair_key = (tbl_name.upper(), col_name.upper())
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                unique_pairs.append({
                    "db_name":      db_name,
                    "tbl_name":     tbl_name,
                    "column_name":  col_name,
                    "tobe_enc_key": col_key,
                    "tobe_enc_rsn": tobe_enc_rsn,
                    "where_opt":    where_opt or ""
                })

    print("[INFO] 1단계 가공 완료: 고유 (tbl_name, column_name) 쌍 %d 건 추출" % len(unique_pairs))
    
    # ── 1단계 결과 저장 (p190872_{last_dir}_search_input) ──
    search_input_csv_path = save_search_input_csv(unique_pairs, src_dir, op_dtm)
    print("[INFO] 1단계 CSV 파일 저장 완료: %s" % search_input_csv_path)
    
    db_search_input_inserted = 0
    if use_db:
        db_search_input_inserted, db_search_err = db_insert_search_input_all(
            unique_pairs, mysql_conf, src_dir, op_dtm
        )
        if db_search_err:
            print("[ERROR] 1단계 DB 테이블 적재 실패: %s" % db_search_err)
        else:
            print("[INFO] 1단계 DB 테이블 적재 완료: %d 건" % db_search_input_inserted)
    print("-" * 70)

    # ── TEMP 레지스트리 수집 ─────────────────────────────────────────
    print("[INFO] TEMP 테이블 레지스트리 수집 중 ...")
    temp_registry = build_temp_registry(src_dir)
    print("[INFO] TEMP 테이블 수집 완료: %d 개" % len(temp_registry))
    print("-" * 70)

    # ── 소스 파일 탐색 및 쿼리 원본 추출 ─────────────────────────────────
    print("[INFO] 소스 파일 탐색 및 쿼리 원본 수집 시작 ...")
    sql_buffer       = []
    total_files      = 0
    total_queries    = 0
    total_file_lines = 0

    for root, _, files in os.walk(src_dir):
        for file in sorted(files):
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue
            total_files   += 1
            full_path      = os.path.join(root, file)
            base_directory = os.path.abspath(root)

            queries_with_offset, file_lines, _ = extract_queries_from_file(full_path)
            total_file_lines += file_lines
            total_queries    += len(queries_with_offset)

            query_seq = 0
            for query, raw_query, query_start_line_no in queries_with_offset:
                query_seq += 1
                sql_buffer.append({
                    "base_directory": base_directory,
                    "file_name":      file,
                    "dir_file":       full_path,
                    "query_seq":      query_seq,
                    "start_line_no":  query_start_line_no if query_start_line_no is not None else 1,
                    "query_text":     raw_query,
                })

    print("[INFO] 쿼리 원본 추출 완료: 파일 %d 개 / 쿼리 %d 건" % (total_files, len(sql_buffer)))
    
    # ── 쿼리 원본 CSV 저장 ──
    sql_output_path = save_sql_csv(sql_buffer, src_dir, op_dtm, mode)
    print("[INFO] 쿼리 원본 CSV 파일 저장 완료: %s" % sql_output_path)
    
    db_sql_inserted = 0
    db_sql_table = build_sql_table_name(src_dir, mode)
    if use_db:
        db_sql_inserted, db_sql_err = db_insert_sql_all(
            sql_buffer, run_id, op_dtm, mysql_conf, src_dir, mode
        )
        if db_sql_err:
            print("[ERROR] DB 쿼리 원본 적재 실패: %s" % db_sql_err)
        else:
            print("[INFO] DB 쿼리 원본 적재 완료: %d 건" % db_sql_inserted)
    print("-" * 70)

    # ── 2단계: 1에서 저장한 검색 정보를 이용하여 매칭자료 조회 ────────────────
    print("[INFO] 2단계: DB 적재 쿼리 정보로부터 테이블+칼럼 매칭 조회 시작 ...")
    
    queries_to_match = []
    if use_db and db_sql_inserted > 0:
        queries_to_match = load_queries_from_sql_table(mysql_conf, db_sql_table)
    
    if not queries_to_match:
        queries_to_match = sql_buffer

    col_match_buffer = []
    compiled_col_patterns = {}
    file_match_counts = {}

    for q_row in queries_to_match:
        q_text    = q_row["query_text"]
        start_ln  = q_row["start_line_no"]
        file_name = q_row["file_name"]
        dir_file  = q_row["dir_file"]
        base_dir  = q_row["base_directory"]

        sql_type  = detect_real_sql_type(q_text)
        crud_type = classify_crud_type(sql_type)
        sources   = extract_sources_recursive(q_text)
        targets   = extract_target_tables(q_text)

        src_upper = {str(s).strip().upper() for s in sources if s}
        tgt_upper = {str(t).strip().upper() for t in targets if t}
        query_text_upper = q_text.upper()

        q_match_cnt = 0
        for pair in unique_pairs:
            tbl = pair["tbl_name"]
            col = pair["column_name"]
            db_name = pair["db_name"]
            enc_key = pair["tobe_enc_key"]
            enc_rsn = pair["tobe_enc_rsn"]

            tbl_up = str(tbl).strip().upper()
            col_up = str(col).strip().upper()

            # 테이블 매칭 판정
            match_type = None
            if tbl_up in tgt_upper:
                match_type = "TARGET"
            elif tbl_up in src_upper:
                match_type = "SOURCE"

            if match_type is None:
                continue

            # 칼럼 매칭 판정 (정규식 또는 문자열 검사)
            rx = compiled_col_patterns.get(col_up)
            if rx is None:
                try:
                    rx = re.compile(r"\b%s\b" % re.escape(col.strip()), re.IGNORECASE)
                    compiled_col_patterns[col_up] = rx
                except Exception:
                    pass

            col_in_query = False
            if rx and rx.search(q_text):
                col_in_query = True
            elif col_up in query_text_upper:
                col_in_query = True

            if not col_in_query:
                continue

            # 매칭 위치 (라인번호 및 matched_line) 추적
            line_number  = start_ln
            matched_line = ""
            for line_idx, line in enumerate(q_text.splitlines()):
                if (rx and rx.search(line)) or (col_up in line.upper()):
                    matched_line = line.strip()
                    if start_ln is not None:
                        line_number = start_ln + line_idx
                    break

            # 매칭 데이터 적재 버퍼 추가
            col_match_buffer.append({
                # 검색기준 원본 필드 대응 (구조 정합성 확보)
                "db_name":      db_name,
                "tbl_name":     tbl,
                "operation":    "",
                "no":           "",
                "source_file":  "",
                "process_yn":   "",
                "process_desc": "",
                "cols":         "",
                "enc_col_cnt":  "",
                "ins_cnt":      "",
                "sel_cnt":      "",
                # 매칭 상세 결과 필드
                "base_directory":   base_dir,
                "src_file_name":    file_name,
                "dir_file":         dir_file,
                "crud_type":        crud_type,
                "sql_type":         sql_type,
                "match_type":       match_type,
                "matched_col_name": col,
                "matched_col_key":  enc_key,
                "line_number":      line_number,
                "matched_line":     matched_line,
                "where_opt":        where_opt or "",
            })
            q_match_cnt += 1
            
        if q_match_cnt > 0:
            file_match_counts[dir_file] = file_match_counts.get(dir_file, 0) + q_match_cnt

    print("[INFO] 매칭 자료 순환 탐색 완료: 매칭 레코드 %d 건 추출" % len(col_match_buffer))
    print("-" * 70)

    # ── 매칭 결과 CSV 저장 (out/p190872_{last_dir}_simple_col_match.csv) ──
    result_csv_path = save_result_csv(col_match_buffer, src_dir, op_dtm)
    print("[INFO] 매칭 결과 CSV 파일 저장 완료: %s" % result_csv_path)
    print("-" * 70)

    # ── 매칭 결과 DB 적재 ──
    db_result_inserted = 0
    db_result_err = None
    _, _, fq_result_table = build_result_table(src_dir, ref_schema)
    if use_db:
        print("[INFO] MySQL 매칭 결과 테이블 적재 시작: %s ..." % fq_result_table)
        db_result_inserted, db_result_err = db_insert_result_all(
            col_match_buffer, run_id, op_dtm, mysql_conf, src_dir, ref_schema
        )
        if db_result_err:
            print("[ERROR] DB 결과 적재 실패: %s" % db_result_err)
        else:
            print("[INFO] DB 결과 적재 완료: %d 건" % db_result_inserted)
        print("-" * 70)

    # ── 매칭 파일 목록 출력 ──────────────────────────────────────────
    if file_match_counts:
        print("[INFO] 매칭된 소스 파일 목록:")
        for fpath, cnt in sorted(file_match_counts.items()):
            print("  - %-60s  (%d 건)" % (fpath, cnt))
        print("-" * 70)

    # ── 최종 결과 요약 ───────────────────────────────────────────────
    print("=" * 70)
    print(" 로컬 소스 tbl_name + cols 칼럼 매칭 탐색 성공 완료")
    print("=" * 70)
    print("  처리일시             : %s" % op_dtm)
    print("  run_id (실행 ID)     : %s" % run_id)
    print("  검색 기준 테이블     : %s" % ref_table)
    print("  고유 매칭 칼럼 쌍    : %d 개" % len(unique_pairs))
    print("  스캔 파일 수         : %d 개" % total_files)
    print("  추출 쿼리 수         : %d 건" % total_queries)
    print("  최종 매칭 결과 건수  : %d 건" % len(col_match_buffer))
    print("  저장 입력 CSV 파일   : %s" % search_input_csv_path)
    print("  저장 쿼리 CSV 파일   : %s" % sql_output_path)
    print("  저장 결과 CSV 파일   : %s" % result_csv_path)
    print("-" * 70)
    if use_db:
        print("  DB 입력 적재 테이블  : %s" % build_search_input_table_name(src_dir))
        print("  DB 입력 적재 건수    : %d 건" % db_search_input_inserted)
        print("  DB 쿼리 적재 테이블  : %s" % db_sql_table)
        print("  DB 쿼리 적재 건수    : %d 건" % db_sql_inserted)
        if db_result_err:
            print("  DB 결과 적재         : 실패 (%s)" % db_result_err)
        else:
            print("  DB 결과 적재 테이블  : %s" % fq_result_table)
            print("  DB 결과 적재 건수    : %d 건" % db_result_inserted)
    else:
        print("  DB 적재              : 생략 (--db 옵션 미지정)")
    print("=" * 70)
    print("[INFO] 모든 처리가 완료되었습니다.\n")


if __name__ == "__main__":
    main()
