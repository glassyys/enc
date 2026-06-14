#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_v12_full_new_03_local.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001_local_02 (2026-06-12)
#   [수정1] CASE1/CASE2 매칭 동작 확인 및 주석 보강
#           - CASE1: INSERT INTO tbl01 → tbl01이 TARGET → col_01 매칭
#           - CASE2: FROM tbl01 → tbl01이 SOURCE → col_bb 매칭
#           - 두 케이스 모두 정상 동작 확인
#   [수정2] 검색기준 cols 목록 화면 출력 추가
#           - tbl_name, cols, 파싱된 칼럼명 목록을 출력
#   [수정3] 검색기준테이블 행 유지 (매칭 없는 행도 결과에 포함)
#           - ref_row 기준으로 소스 매칭이 전혀 없는 경우에도
#             매칭 관련 칼럼을 NULL/'' 로 채워 결과 행 생성
#   [수정4] cols 분리값만큼 각각 추출 (매칭 없는 칼럼도 NULL행 포함)
#           - col_item 별로 소스 매칭이 없으면 line_number=NULL,
#             matched_line='' 로 결과 행 생성 (칼럼 순환 보장)
#   [수정5] 매칭 결과가 없어도 CSV/DB 저장 계속 진행
#           - 전체 결과 없을 때 sys.exit(0) 제거,
#             ref_row 기반 NULL행이 항상 존재하므로 저장 로직 통과
#
# v001_local (2026-06-12)
#   [신규] sql_v12_full_new_02_local.py 의 확장 버전
#   - 검색 기준 테이블 레이아웃 변경
#     기존: tbl_name + column_name (1:1 쌍)
#     변경: tbl_name + cols ("col_01:k1,col_bb:k2" 형식의 복합 칼럼 문자열)
#   - cols 파싱 로직 추가
#     "col_01:k1,col_bb:k2" → [("col_01","k1"), ("col_bb","k2")]
#     ","로 분리 → 각 항목에서 ":" 앞부분이 칼럼명, ":" 뒷부분이 키값
#   - 매칭 조건 변경
#     기존: tbl_name 일치 + column_name \b완전일치
#     변경: tbl_name 일치 + cols 에서 파싱된 각 칼럼명 \b완전일치 (순환 처리)
#   - 결과 레이아웃에 검색기준테이블의 전체 칼럼값 포함
#     (db_name, tbl_name, operation, no, source_file, process_yn,
#      process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt)
#     + line_number (소스파일 전체 기준 절대 행번호)
#     + matched_line (매칭된 라인 내용)
#   - [--mode] 파라미터 제거 (DB 조회가 필수이므로 항상 실행)
#   - [--db] 옵션: 결과 파일 생성 + MySQL 테이블 적재
#   - 결과 테이블: 검색기준테이블과 동일한 스키마에 생성
#   - 파일명/테이블명: 일자_시간 제외
#
# ■ 참조 소스 목록
# ─────────────────────────────────────────────────────────────
# sql_find_v001_01.py
#   - in/ 디렉토리 기반 CSV 읽기 및 단어 리스트 추출 로직 참조
#   - 소스 파일 탐색 및 라인 단위 매칭 로직 참조
#   - DB 적재 (DROP→CREATE→INSERT) 방식 참조
#
# sql_find_v001_01_local.py
#   - CSV 절대경로로 직접 지정하는 로컬 실행 방식 참조
#   - out/ 디렉토리에 결과 CSV 저장 방식 참조
#
# sql_v12_full_new_02.py
#   - 소스 파일 파싱(쿼리 추출, CTE, 소스/타겟 테이블 추출) 전체 로직 참조
#   - 파일 전체 기준 절대 행번호 산출 방식 참조
#   - MySQL DDL/INSERT 방식 (DROP→CREATE→INSERT) 참조
#   - preprocess(): 주석 제거 후 쿼리 추출 로직 참조
#
# ■ 프로그램 설명
# ─────────────────────────────────────────────────────────────
# 1) 실행 시 파라미터: 분석대상_디렉토리, 스키마.검색기준테이블, [--db], [--conf]
# 2) 서버 MySQL 에서 <검색기준테이블> 전체 데이터 조회
#    - 스키마 포함 전체 테이블명(`schema`.`table`)으로 직접 처리
#    - 조회 칼럼: db_name, tbl_name, operation, no, source_file,
#                 process_yn, process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt
# 3) 조회된 각 행의 tbl_name 과 cols 를 검색 기준으로 메모리에 저장
#    - cols 파싱: "col_01:k1,col_bb:k2" → [("col_01","k1"), ("col_bb","k2")]
#    - ","로 분리 후 각 항목의 ":" 앞부분을 칼럼명으로 사용
# 4) 분석대상_디렉토리 하위 소스 파일 (.sql, .hql, .uld, .ld, .sh) 전체 탐색
# 5) 각 소스 파일에서 쿼리 단위로 추출 (주석 제거 포함)
# 6) 매칭 조건 (AND 조건):
#    조건1) 쿼리의 소스 또는 타겟 테이블 중 tbl_name 과 일치하는 항목 존재
#    조건2) cols 에서 파싱된 각 칼럼명이 해당 쿼리 텍스트에 \b완전일치로 포함
#           → 각 칼럼명별로 순환 처리, 매칭된 라인 및 절대 행번호 각각 추출
# 7) 매칭 결과에 검색기준테이블의 원본 행 전체 칼럼값 포함하여 CSV 생성
# 8) [--db] 옵션 지정 시 검색기준테이블과 동일 스키마에 결과 테이블 적재
#
# ■ 실행 형식
# ─────────────────────────────────────────────────────────────
# python3 sql_v12_full_new_03_local.py \
#     <분석대상_디렉토리> <스키마.검색기준테이블> \
#     [--db] [--conf mysql.conf 경로]
#
# ■ 실제 실행 예시
# ─────────────────────────────────────────────────────────────
# [예시1] 파일만 생성 / DB 미등록 (Windows)
# python3 sql_v12_full_new_03_local.py \
#     D:\NAS\MIDP\DBMSVC\MIDP\SID \
#     midp_db.enc_col_target \
#     --conf D:\chksrc\mysql.conf
#
# [예시2] 파일 생성 + DB 등록 (Windows)
# python3 sql_v12_full_new_03_local.py \
#     D:\NAS\MIDP\DBMSVC\MIDP\SID \
#     midp_db.enc_col_target \
#     --db \
#     --conf D:\chksrc\mysql.conf
#
# [예시3] 파일 생성 + DB 등록 (Linux)
# python3 /home/p190872/chksrc/sql_v12_full_new_03_local.py \
#     /NAS/MIDP/DBMSVC/MIDP/SID \
#     midp_db.enc_col_target \
#     --db \
#     --conf /home/p190872/chksrc/mysql.conf
#
# [예시4] TMT 디렉토리 대상 / DB 등록 (Linux)
# python3 /home/p190872/chksrc/sql_v12_full_new_03_local.py \
#     /NAS/MIDP/DBMSVC/MIDP/TMT \
#     midp_db.enc_col_target \
#     --db \
#     --conf /home/p190872/chksrc/mysql.conf
#
# [예시5] mysql.conf 자동탐색 (스크립트 디렉토리 또는 실행 경로)
# python3 sql_v12_full_new_03_local.py \
#     /NAS/MIDP/DBMSVC/MIDP/SID \
#     midp_db.enc_col_target
#
# ■ 파라미터
# ─────────────────────────────────────────────────────────────
# 분석대상_디렉토리    : 소스파일(.sql/.hql/.uld/.ld/.sh) 탐색 루트
# 스키마.검색기준테이블: MySQL 테이블명 (스키마 필수 포함: schema.tablename)
#                        조회 칼럼(고정 11항목):
#                          db_name, tbl_name, operation, no, source_file,
#                          process_yn, process_desc, cols,
#                          enc_col_cnt, ins_cnt, sel_cnt
# --db                 : 결과 파일 생성 + MySQL DB 등록 (mysql.conf 필요)
# --conf 경로          : mysql.conf 파일 경로 지정 (미지정 시 자동탐색)
#
# ■ cols 파싱 규칙
# ─────────────────────────────────────────────────────────────
# cols 값 예시: "col_01:k1,col_bb:k2"
# ","로 분리   → ["col_01:k1", "col_bb:k2"]
# ":"로 분리   → 앞부분: 칼럼명, 뒷부분: 키값
# 칼럼명 목록  → ["col_01", "col_bb"]
# 각 칼럼명에 대해 소스 쿼리 내 \b칼럼명\b 완전일치 검색 수행
#
# ■ [mysql.conf 파일 예시]
# ─────────────────────────────────────────────────────────────
# [mysql]
# host     = 192.168.1.100
# port     = 3306
# user     = midp_user
# password = secret
# database = midp_db
# charset  = utf8mb4
#
# ■ 검색기준테이블 레이아웃 (MySQL)
# ─────────────────────────────────────────────────────────────
# CREATE TABLE midp_db.enc_col_target (
#   id           BIGINT       NOT NULL AUTO_INCREMENT,
#   db_name      VARCHAR(200) NULL     COMMENT 'DB명',
#   tbl_name     VARCHAR(500) NOT NULL COMMENT '테이블명',
#   operation    VARCHAR(50)  NULL     COMMENT '오퍼레이션 (INSERT/SELECT 등)',
#   no           INT          NULL     COMMENT '순번',
#   source_file  VARCHAR(500) NULL     COMMENT '소스파일 경로',
#   process_yn   VARCHAR(1)   NULL     COMMENT '처리여부 (Y/N)',
#   process_desc VARCHAR(500) NULL     COMMENT '처리설명',
#   cols         VARCHAR(2000)NULL     COMMENT '칼럼목록 (col_01:k1,col_bb:k2 형식)',
#   enc_col_cnt  INT          NULL     COMMENT '암호화 칼럼 수',
#   ins_cnt      INT          NULL     COMMENT 'INSERT 건수',
#   sel_cnt      INT          NULL     COMMENT 'SELECT 건수',
#   PRIMARY KEY (id)
# );
#
# ■ 출력 파일 레이아웃
# ─────────────────────────────────────────────────────────────
# out/{프로그램명}_{마지막디렉토리}_col_match.csv
# 칼럼 순서:
#   [검색기준테이블 원본 칼럼]
#   db_name, tbl_name, operation, no, source_file,
#   process_yn, process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt
#   [매칭 결과 추가 칼럼]
#   base_directory, src_file_name, dir_file,
#   crud_type, sql_type, match_type,
#   matched_col_name, matched_col_key,
#   line_number, matched_line, op_dtm
#
# ■ 결과 적재 테이블명 (--db 옵션)
# ─────────────────────────────────────────────────────────────
# {검색기준테이블_스키마}.{프로그램명}_{마지막디렉토리}_col_match
# 예: midp_db.sql_v12_full_new_03_local_SID_col_match
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

# 검색기준테이블 고정 칼럼 목록 (없는 칼럼은 NULL 로 대체)
REF_TABLE_COLS = [
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols",
    "enc_col_cnt", "ins_cnt", "sel_cnt",
]

# 결과 CSV / DB 테이블 필드 순서
RESULT_FIELDNAMES = [
    # 검색기준테이블 원본 칼럼
    "db_name", "tbl_name", "operation", "no", "source_file",
    "process_yn", "process_desc", "cols", "enc_col_cnt", "ins_cnt", "sel_cnt",
    # 매칭 결과 추가 칼럼
    "base_directory", "src_file_name", "dir_file",
    "crud_type", "sql_type", "match_type",
    "matched_col_name", "matched_col_key",
    "line_number", "matched_line",
    "op_dtm",
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
    """
    'schema.table' → (schema, table)
    스키마 미포함   → ("", table)
    """
    parts = full_table.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", parts[0].strip()


def make_fq(schema: str, table: str) -> str:
    """fully-qualified 테이블명 생성: `schema`.`table` 또는 `table`"""
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table


# ============================================================
# cols 파싱: "col_01:k1,col_bb:k2" → [{"col_name":"col_01","col_key":"k1"}, ...]
# ============================================================
def parse_cols(cols_str: str) -> list:
    """
    cols 필드 파싱.
    입력 예: "col_01:k1,col_bb:k2"
    반환 예: [{"col_name": "col_01", "col_key": "k1"},
              {"col_name": "col_bb", "col_key": "k2"}]
    - ":" 이 없는 항목은 col_key="" 로 처리
    - 공백 무시
    """
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
# 서버 MySQL 검색기준테이블 조회
# 반환: (list of dict, ref_schema, error_msg)
# ============================================================
def load_ref_rows_from_db(mysql_conf: dict, ref_table: str) -> tuple:
    """
    ref_table(스키마.테이블) 의 전체 데이터 조회.
    없는 칼럼은 None(NULL) 으로 대체하여 반환.
    반환: (rows: list of dict, ref_schema: str, error_msg: str|None)
    """
    rows      = []
    conn      = None
    cursor    = None
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    fq_table  = make_fq(ref_schema, ref_tbl_only)

    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
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

        sql = "SELECT %s FROM %s ORDER BY tbl_name, no" % (
            ", ".join(select_parts), fq_table
        )
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
        if cursor:
            try: cursor.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


# ============================================================
# 결과 적재 DDL / INSERT
# ============================================================
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='소스 tbl_name+cols 칼럼 매칭 결과 (검색기준테이블 전체 칼럼 포함)';
"""

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (run_id,
   db_name, tbl_name, operation, no, source_file,
   process_yn, process_desc, cols, enc_col_cnt, ins_cnt, sel_cnt,
   base_directory, src_file_name, dir_file,
   crud_type, sql_type, match_type,
   matched_col_name, matched_col_key,
   line_number, matched_line,
   op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# ============================================================
# 동적 결과 테이블명 생성
# 형식: {ref_schema}.{PROGRAM_NAME}_{마지막디렉토리}_col_match
# ============================================================
def build_result_table(source_dir: str, ref_schema: str) -> tuple:
    """
    반환: (schema, table_only, fq_name)
    """
    last_dir   = os.path.basename(os.path.normpath(source_dir))
    table_only = "%s_%s_col_match" % (PROGRAM_NAME, last_dir)
    fq         = make_fq(ref_schema, table_only)
    return ref_schema, table_only, fq


# ============================================================
# DB: DROP → CREATE → INSERT (결과 적재)
# ============================================================
def db_insert_result_all(result_buffer: list, run_id: str, op_dtm: str,
                         mysql_conf: dict, source_dir: str,
                         ref_schema: str) -> tuple:
    _, _, fq_table = build_result_table(source_dir, ref_schema)
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
            # no, enc_col_cnt, ins_cnt, sel_cnt: 정수 변환 (빈 문자열→None)
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
                op_dtm,
            ))

        if batch:
            cursor.executemany(_SQL_INSERT_RESULT.format(table=fq_table), batch)
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
# 결과 CSV 저장
# out/{PROGRAM_NAME}_{마지막디렉토리}_col_match.csv
# ============================================================
def save_result_csv(result_buffer: list, source_dir: str, op_dtm: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir = os.path.basename(os.path.normpath(source_dir))
    csv_file = "%s_%s_col_match.csv" % (PROGRAM_NAME, last_dir)
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
# 소스 파싱용 정규식 / 상수
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
# 전처리: 주석 제거 (문자열 리터럴 유지)
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
# 핵심 매칭 로직
#
# ■ 매칭 동작 확인 (CASE1 / CASE2)
# ─────────────────────────────────────────────────────────────
# 검색기준: tbl_name="tbl01", cols="col_01:k1,col_bb:k2"
#
# CASE1) INSERT INTO tbl01 ... SELECT max(col_01) as col_01 FROM tbl02;
#   → tbl01 이 TARGET(INSERT INTO tbl01) → match_type="TARGET"
#   → col_01 이 쿼리에 존재 → line_number=해당행, matched_line="max(col_01) as col_01"
#   → col_bb 는 쿼리에 없음 → line_number=NULL, matched_line='' 로 행 생성
#
# CASE2) INSERT OVERWRITE tbl99 ... SELECT nvl(col_bb) as col_bb FROM tbl01;
#   → tbl01 이 SOURCE(FROM tbl01) → match_type="SOURCE"
#   → col_01 은 쿼리에 없음 → line_number=NULL, matched_line='' 로 행 생성
#   → col_bb 가 쿼리에 존재 → line_number=해당행, matched_line="nvl(col_bb) as col_bb"
#
# ■ 처리 원칙
# ─────────────────────────────────────────────────────────────
# 1) ref_row 마다 tbl_name 이 쿼리의 소스/타겟 테이블에 있는지 확인
#    - 없으면 → 이 쿼리에 대해 ref_row 는 스킵 (다른 쿼리에서 매칭될 수 있음)
#    - 있으면 → cols 분리 칼럼 각각에 대해 아래 처리 수행
# 2) cols 파싱 칼럼 순환 (cols 분리값 개수만큼 결과 행 생성)
#    - 칼럼이 쿼리에 있으면 → line_number/matched_line 채워 행 생성
#    - 칼럼이 쿼리에 없으면 → line_number=NULL, matched_line='' 로 행 생성
# 3) cols 가 비어있으면 → 칼럼 관련 항목 공란으로 행 1건 생성
# ============================================================
def build_match_rows(
    query_text: str,
    sources: set,
    targets: set,
    crud_type: str,
    sql_type: str,
    base_directory: str,
    src_file_name: str,
    dir_file: str,
    ref_rows: list,
    compiled_col_patterns: dict,
    query_start_line_no,
    orig_lines: list = None,
    ref_matched_flags: list = None,   # ref_row 별 매칭 여부 플래그 (인덱스 공유)
) -> list:
    results   = []
    
    # 1. 소스/타겟 테이블 목록을 대문자로 통일하여 가공 (대소문자 구분 없는 비교 보장)
    src_upper = {str(s).strip().upper() for s in sources if s}
    tgt_upper = {str(t).strip().upper() for t in targets if t}
    
    # 쿼리 텍스트 전체를 대문자로 변환한 본문 (대소문자 구분 없는 고속 1차 string 매칭용)
    query_text_upper = query_text.upper()

    for ref_idx, ref_row in enumerate(ref_rows):
        tbl_name = ref_row.get("tbl_name", "")
        cols_str = ref_row.get("cols", "")
        if not tbl_name:
            continue

        # 검색 기준 테이블명도 대문자로 변환
        tbl_up = str(tbl_name).strip().upper()

        # 조건1: 테이블 존재 확인 (TARGET 우선, 없으면 SOURCE) - 대소문자 무관하게 매칭
        match_type = None
        if tbl_up in tgt_upper:
            match_type = "TARGET"
        elif tbl_up in src_upper:
            match_type = "SOURCE"

        # tbl_name 이 이 쿼리에 없으면 이 쿼리는 스킵
        if match_type is None:
            continue

        # tbl_name 매칭 성공 → ref_row 매칭 플래그 ON
        if ref_matched_flags is not None:
            ref_matched_flags[ref_idx] = True

        # cols 파싱
        col_items = parse_cols(cols_str)

        if not col_items:
            # cols 비어있음 → 칼럼 관련 항목 공란으로 행 1건 생성
            results.append(_make_result_row(
                ref_row, base_directory, src_file_name, dir_file,
                crud_type, sql_type, match_type,
                matched_col_name="", matched_col_key="",
                line_number=None, matched_line="",
            ))
            continue

        # 조건2: cols 분리값 개수만큼 순환 → 대소문자 구분 없이 query_text 포함 여부 판단
        for col_item in col_items:
            col_name = col_item["col_name"]
            col_key  = col_item["col_key"]
            col_up   = col_name.strip().upper()

            # 정규식 캐싱 및 컴파일
            rx = compiled_col_patterns.get(col_up)
            if rx is None:
                try:
                    rx = re.compile(r"\b%s\b" % re.escape(col_name.strip()), re.IGNORECASE)
                    compiled_col_patterns[col_up] = rx
                except Exception:
                    pass

            # [핵심 보완] 정규식 완전일치(\b)로 검색하거나, 
            # 변수명 처리 등으로 인해 단어 경계 인식이 안 될 경우를 대비해 
            # 대소문자 구분 없는 단순 문자열 포함(in) 조건도 상호 보완적으로 체크합니다.
            col_in_query = False
            if rx and rx.search(query_text):
                col_in_query = True
            elif col_up in query_text_upper:
                col_in_query = True

            if col_in_query:
                # 파일 전체 기준 절대 행번호 산출
                line_number  = None
                matched_line = ""
                if query_start_line_no is not None and orig_lines:
                    start_idx = query_start_line_no - 1
                    for idx in range(start_idx, len(orig_lines)):
                        orig_line_upper = orig_lines[idx].upper()
                        # 행 단위에서도 정규식 패턴 혹은 단순 대소문자 포함 여부 체크
                        if (rx and rx.search(orig_lines[idx])) or (col_up in orig_line_upper):
                            line_number  = idx + 1
                            matched_line = orig_lines[idx].strip()
                            break
                
                # 대피책(Fallback): 쿼리 안에서 줄 바꿈 기준으로 매칭행 추적
                if not matched_line:
                    for line in query_text.splitlines():
                        if (rx and rx.search(line)) or (col_up in line.upper()):
                            matched_line = line.strip()
                            break
            else:
                # 칼럼이 이 쿼리에 없음 → NULL행으로 기록 (cols 순환 보장)
                line_number  = None
                matched_line = ""

            results.append(_make_result_row(
                ref_row, base_directory, src_file_name, dir_file,
                crud_type, sql_type, match_type,
                matched_col_name=col_name, matched_col_key=col_key,
                line_number=line_number, matched_line=matched_line,
            ))

    return results


def _make_result_row(ref_row: dict, base_directory: str, src_file_name: str,
                     dir_file: str, crud_type: str, sql_type: str,
                     match_type: str, matched_col_name: str, matched_col_key: str,
                     line_number, matched_line: str) -> dict:
    """결과 행 dict 생성 헬퍼"""
    row = {}
    # 검색기준테이블 원본 칼럼값 복사
    for col in REF_TABLE_COLS:
        row[col] = ref_row.get(col, "")
    # 매칭 결과 칼럼값
    row["base_directory"]   = base_directory
    row["src_file_name"]    = src_file_name
    row["dir_file"]         = dir_file
    row["crud_type"]        = crud_type
    row["sql_type"]         = sql_type
    row["match_type"]       = match_type
    row["matched_col_name"] = matched_col_name
    row["matched_col_key"]  = matched_col_key
    row["line_number"]      = line_number
    row["matched_line"]     = matched_line
    return row


# ============================================================
# 인수 파싱
# ============================================================
def parse_args() -> tuple:
    args      = sys.argv[1:]
    src_dir   = None
    ref_table = None
    use_db    = False
    conf_path = None

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
        else:
            if src_dir is None:
                src_dir = args[i]
            elif ref_table is None:
                ref_table = args[i]
            i += 1

    if src_dir is None or ref_table is None:
        print("사용법: python3 %s.py <분석대상_디렉토리> <스키마.검색기준테이블> "
              "[--db] [--conf mysql.conf 경로]" % PROGRAM_NAME)
        print("")
        print("예시:")
        print("  python3 %s.py D:\\source midp_db.enc_col_target" % PROGRAM_NAME)
        print("  python3 %s.py D:\\source midp_db.enc_col_target --db "
              "--conf D:\\chksrc\\mysql.conf" % PROGRAM_NAME)
        print("  python3 %s.py /NAS/MIDP/SRC midp_db.enc_col_target --db "
              "--conf /home/p190872/chksrc/mysql.conf" % PROGRAM_NAME)
        sys.exit(1)

    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        print("[오류] 유효한 디렉토리가 아닙니다: %s" % src_dir)
        sys.exit(1)

    return src_dir, ref_table, use_db, conf_path


# ============================================================
# MAIN
# ============================================================
def main():
    src_dir, ref_table, use_db, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [로컬 소스 tbl_name + cols 칼럼 매칭 탐색 시작]")
    print("=" * 70)
    print("  분석 대상 디렉토리 : %s" % src_dir)
    print("  검색 기준 테이블   : %s" % ref_table)
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

    # ── 검색기준테이블 조회 ──────────────────────────────────────────
    print("[INFO] 검색기준테이블 조회 중: %s ..." % ref_table)
    ref_rows, ref_schema, db_err = load_ref_rows_from_db(mysql_conf, ref_table)
    if db_err:
        print("[ERROR] %s" % db_err)
        sys.exit(1)
    if not ref_rows:
        print("[ERROR] 검색기준테이블에서 조회된 데이터가 없습니다.")
        sys.exit(1)

    # tbl_name 고유 건수 및 cols 파싱 건수 집계
    unique_tbls     = len({r["tbl_name"] for r in ref_rows if r["tbl_name"]})
    total_col_items = sum(len(parse_cols(r.get("cols", ""))) for r in ref_rows)
    print("[INFO] 조회 완료: 전체 %d 행  / 고유 tbl_name %d 개  / cols 파싱 칼럼 합계 %d 개" % (
        len(ref_rows), unique_tbls, total_col_items
    ))

    # ── cols 목록 화면 출력 (요건3) ─────────────────────────────────
    print("[INFO] 검색 기준 cols 목록:")
    print("  %-5s  %-40s  %-50s  %s" % ("No", "tbl_name", "cols", "파싱된 칼럼명 목록"))
    print("  " + "-" * 120)
    for i, ref_row in enumerate(ref_rows, 1):
        tbl  = ref_row.get("tbl_name", "")
        cols = ref_row.get("cols", "")
        parsed = parse_cols(cols)
        col_names = ", ".join(c["col_name"] for c in parsed) if parsed else "(없음)"
        print("  %-5d  %-40s  %-50s  [%s]" % (i, tbl, cols, col_names))
    print("-" * 70)

    # in/ 디렉토리에 검색 기준 복사본 저장
    os.makedirs(IN_DIR, exist_ok=True)
    last_dir    = os.path.basename(os.path.normpath(src_dir))
    in_csv_name = "%s_%s_search_input.csv" % (PROGRAM_NAME, last_dir)
    in_csv_path = os.path.join(IN_DIR, in_csv_name)
    try:
        with open(in_csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=REF_TABLE_COLS)
            writer.writeheader()
            writer.writerows(ref_rows)
        print("[INFO] 검색 기준 복사본 저장: %s" % in_csv_path)
    except Exception as e:
        print("[WARN] in/ 저장 실패 (계속 진행): %s" % str(e))
    print("-" * 70)

    # ── 칼럼 정규식 사전 컴파일 ──────────────────────────────────────
    compiled_col_patterns = {}
    for ref_row in ref_rows:
        for col_item in parse_cols(ref_row.get("cols", "")):
            col_up = col_item["col_name"].upper()
            if col_up not in compiled_col_patterns:
                try:
                    compiled_col_patterns[col_up] = re.compile(
                        r"\b%s\b" % re.escape(col_item["col_name"]), re.IGNORECASE
                    )
                except Exception:
                    pass

    # ── TEMP 레지스트리 수집 ─────────────────────────────────────────
    print("[INFO] TEMP 테이블 레지스트리 수집 중 ...")
    temp_registry = build_temp_registry(src_dir)
    print("[INFO] TEMP 테이블 수집 완료: %d 개" % len(temp_registry))
    print("-" * 70)

    # ── 소스 파일 탐색 및 매칭 ───────────────────────────────────────
    print("[INFO] 소스 파일 탐색 및 쿼리 매칭 시작 ...")

    # ref_row 별 매칭 여부 추적 (인덱스 기반)
    # - 소스 전체에서 한 번이라도 매칭된 ref_row 는 True
    # - 한 번도 매칭되지 않은 ref_row 는 마지막에 NULL행으로 결과에 추가
    ref_matched_flags = [False] * len(ref_rows)

    result_buffer    = []
    total_files      = 0
    total_queries    = 0
    total_file_lines = 0
    file_match_counts = {}

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
            for query, raw_query, query_start_line_no in queries_with_offset:
                sql_type  = detect_real_sql_type(query)
                crud_type = classify_crud_type(sql_type)
                sources   = extract_sources_recursive(query)
                targets   = extract_target_tables(query)

                match_rows = build_match_rows(
                    query_text            = raw_query,
                    sources               = sources,
                    targets               = targets,
                    crud_type             = crud_type,
                    sql_type              = sql_type,
                    base_directory        = base_directory,
                    src_file_name         = file,
                    dir_file              = full_path,
                    ref_rows              = ref_rows,
                    compiled_col_patterns = compiled_col_patterns,
                    query_start_line_no   = query_start_line_no,
                    orig_lines            = orig_lines,
                    ref_matched_flags     = ref_matched_flags,
                )
                if match_rows:
                    result_buffer.extend(match_rows)
                    file_match_cnt += len(match_rows)

            if file_match_cnt > 0:
                file_match_counts[full_path] = file_match_cnt

    # ── 소스에서 한 번도 매칭되지 않은 ref_row → NULL행으로 결과에 추가 ──
    null_row_cnt = 0
    for idx, ref_row in enumerate(ref_rows):
        if not ref_matched_flags[idx]:
            col_items = parse_cols(ref_row.get("cols", ""))
            if col_items:
                # cols 분리값 개수만큼 NULL행 생성 (행 유지)
                for col_item in col_items:
                    result_buffer.append(_make_result_row(
                        ref_row,
                        base_directory="", src_file_name="", dir_file="",
                        crud_type="", sql_type="", match_type="",
                        matched_col_name=col_item["col_name"],
                        matched_col_key=col_item["col_key"],
                        line_number=None, matched_line="",
                    ))
                    null_row_cnt += 1
            else:
                # cols 없음 → 1건만 생성
                result_buffer.append(_make_result_row(
                    ref_row,
                    base_directory="", src_file_name="", dir_file="",
                    crud_type="", sql_type="", match_type="",
                    matched_col_name="", matched_col_key="",
                    line_number=None, matched_line="",
                ))
                null_row_cnt += 1

    print("[INFO] 소스 탐색 완료:")
    print("  - 스캔한 파일 수   : %8d 개  (확장자: %s)" % (
        total_files, ", ".join(sorted(TARGET_EXTENSIONS))))
    print("  - 추출한 쿼리 수   : %8d 건" % total_queries)
    print("  - 총 파일 라인 수  : %8d 줄" % total_file_lines)
    print("  - 소스 매칭 건수   : %8d 건  (line_number 있는 행 포함)" % (len(result_buffer) - null_row_cnt))
    print("  - 미매칭 NULL 행수 : %8d 건  (검색기준테이블 행 유지)" % null_row_cnt)
    print("  - 결과 합계 건수   : %8d 건" % len(result_buffer))
    print("-" * 70)

    # ── 매칭 파일 목록 출력 ──────────────────────────────────────────
    if file_match_counts:
        print("[INFO] 매칭된 소스 파일 목록:")
        for fpath, cnt in sorted(file_match_counts.items()):
            print("  - %-60s  (%d 건)" % (fpath, cnt))
        print("-" * 70)

    # ── 결과 CSV 저장 ────────────────────────────────────────────────
    print("[INFO] 결과 CSV 파일 저장 중 (%s) ..." % OUT_DIR)
    csv_output_path = ""
    try:
        csv_output_path = save_result_csv(result_buffer, src_dir, op_dtm)
        print("[INFO] CSV 파일 저장 완료: %s" % csv_output_path)
        print("  - 저장 레코드 수   : %d 건" % len(result_buffer))
    except Exception as e:
        print("[ERROR] CSV 저장 실패: %s" % str(e))
        sys.exit(1)
    print("-" * 70)

    # ── DB 적재 (--db 옵션) ──────────────────────────────────────────
    db_inserted = 0
    db_err_msg  = None
    _, _, fq_result_table = build_result_table(src_dir, ref_schema)

    if use_db:
        print("[INFO] MySQL 테이블 적재 시작: %s ..." % fq_result_table)
        db_inserted, db_err_msg = db_insert_result_all(
            result_buffer, run_id, op_dtm, mysql_conf, src_dir, ref_schema
        )
        if db_err_msg:
            print("[ERROR] DB 적재 실패: %s" % db_err_msg)
        else:
            print("[INFO] DB 적재 완료: %d 건" % db_inserted)
        print("-" * 70)

    # ── 최종 결과 요약 ───────────────────────────────────────────────
    print("=" * 70)
    print(" 로컬 소스 tbl_name + cols 칼럼 매칭 탐색 성공 완료")
    print("=" * 70)
    print("  처리일시             : %s" % op_dtm)
    print("  run_id (실행 ID)     : %s" % run_id)
    print("  검색 기준 테이블     : %s" % ref_table)
    print("  검색 기준 행 수      : %d 행" % len(ref_rows))
    print("  고유 tbl_name 수     : %d 개" % unique_tbls)
    print("  스캔 파일 수         : %d 개" % total_files)
    print("  추출 쿼리 수         : %d 건" % total_queries)
    print("  총 파일 라인 수      : %d 줄" % total_file_lines)
    print("  매칭 결과 건수       : %d 건" % len(result_buffer))
    print("  저장 CSV 파일        : %s" % csv_output_path)
    print("-" * 70)
    if use_db:
        if db_err_msg:
            print("  DB 적재              : 실패")
            print("  DB 오류 내용         : %s" % db_err_msg)
        else:
            print("  DB 적재              : 성공")
            print("  DB 결과 테이블       : %s" % fq_result_table)
            print("  DB 적재 건수         : %d 건" % db_inserted)
    else:
        print("  DB 적재              : 생략 (--db 옵션 미지정)")
    print("=" * 70)
    print("[INFO] 모든 처리가 완료되었습니다.\n")


if __name__ == "__main__":
    main()