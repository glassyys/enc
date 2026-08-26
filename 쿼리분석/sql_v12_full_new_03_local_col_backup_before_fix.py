#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# sql_v12_full_new_03_local_col.py (2026-07-15 수정 완료)
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
#   - 2026-07-15 (10차 수정): --in 및 --col 동시 지정 시 처리 로직 순서 개편
#     * --in 파일의 칼럼 리스트 기준으로 하위 소스를 1차 검색하여 "결과 csv파일"에 들어갈 후보 데이터를 모두 수집(1차 추출)한 후,
#       최종 CSV 파일 생성 및 DB 테이블 적재 시점에 --col 에서 지정한 칼럼명이 결과 CSV 행 또는 매칭 라인에 포함된 경우만 최종 파일로 생성하고 DB에 등록.
#     * 화면 출력 로그 파일(*_print.txt) 또한 [내용] 행에 --col 지정 칼럼명이 들어있는 세트([매칭]+[내용]+선라인)만 최종 추출하여 저장하도록 수정.
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

# Truncated for brevity; this file is a backup copy of the current workspace state.
