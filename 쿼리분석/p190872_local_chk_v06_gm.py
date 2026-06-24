#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v06_gm.py(20260624)
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
#                  --db 옵션 지정 시 DB 테이블(p190872_{기준테이블}_{MID})에 자동 적재
#
# [실행 형식]
# # python p190872_local_chk_v06_gm.py <검색기준테이블> <검색디렉토리> [--mid <MID목록>] [--db] [--conf <설정파일>] [--where <old|new>] [--chk <default|encdec_no>]
#
# [실행 예시]
# # 1. 기본 실행 예시 (MID 전체 검색, DB 미적재):
# # python p190872_local_chk_v06_gm.py my_db.my_ref_table D:\chksrc\sources
#
# # 2. 특정 MID(subdirectories) 검색 및 DB 적재:
# # python p190872_local_chk_v06_gm.py my_db.my_ref_table D:\chksrc\sources --mid aaa,bbb,ccc --db --conf D:\chksrc\mysql.conf
#
# # 3. 신규 암호화 조건 검색 및 default 함수 매칭 필터 적용:
# # python p190872_local_chk_v06_gm.py my_db.my_ref_table D:\chksrc\sources --mid aaa,bbb --where new --chk default --db
#
# [수정 이력]
# ─────────────────────────────────────────────────────────────
# v05_gm (2026-06-16)
#   - 최초 작성 및 LIKE 검색방식에서 정규식 완전일치 방식으로 수정
# v06_gm (2026-06-24)
#   - 실행 구조 개편: positional arguments 및 --mid, --db, --conf, --where, --chk 옵션 추가
#   - 검색기준테이블 레이아웃 변경 적용 및 column_name 기준 중복 조회 제거
#   - 소스 디렉토리 MID별 개별/전체 탐색 지원 및 결과 파일/테이블 분리 생성
#   - 매칭 행 필터링 강화: 주석 제거 및 순수 칼럼 참조 제외 (omit/include 룰 적용)
#   - --chk 옵션 및 포함예시 이외행(순수 칼럼 참조)에 따른 제외행 파일(exclude.txt) 생성 기능 추가
#   - 화면 출력 내용의 텍스트 파일(print.txt) 생성 및 출력 메시지 보완
#   - 동일 파일 내 중복 라인 매칭 방지(seen_matches) 탑재
# ===============================================================

import os
import re
import sys
import csv
import argparse
import configparser
from datetime import datetime

# ============================================================
# 검색기준테이블 고정 칼럼 목록
# ============================================================
REF_TABLE_COLS = [
    "db_name", "tbl_name", "column_name", "type_name", "integer_idx",
    "mig_dec", "tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn"
]

# 결과 파일 / 테이블 최종 필드 레이아웃
CSV_FIELDNAMES = [
    "run_id", "db_name", "tbl_name", "column_name", "type_name", "integer_idx",
    "mig_dec", "tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn",
    "source_file", "line_number", "matched_line", "vscode_open_cmd",
    "query_text", "op_dtm"
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
# 주석 및 칼럼 필터링 유틸리티
# ============================================================
def strip_comments(line: str) -> str:
    # 1) -- 주석 제거
    line = re.sub(r'--.*$', '', line)
    # 2) # 주석 제거
    line = re.sub(r'#.*$', '', line)
    # 3) single-line block comment /* ... */ 제거
    line = re.sub(r'/\*.*?\*/', '', line)
    return line.strip()

def is_pure_column(clean_line: str, col_name: str) -> bool:
    # 콤마 및 외곽 공백 제거
    s = clean_line.strip().strip(',').strip()
    
    # 1) 단순 칼럼 단독 참조 (예: col1, a.col1)
    pat_col = r'^(?:[a-zA-Z0-9_]+\.)?%s$' % re.escape(col_name)
    if re.match(pat_col, s, re.IGNORECASE):
        return True
        
    # 2) 별칭 부여 (예: col1 as col_alias, c.col_1 as c.col_2)
    # as 기준 칼럼명이 다른 경우 생량하지 않고 포함함(즉, False 반환). 같을 경우만 생략함(True 반환).
    pat_col_alias = r'^(?:[a-zA-Z0-9_]+\.)?%s\s+(?:as\s+)?(?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)$' % re.escape(col_name)
    m = re.match(pat_col_alias, s, re.IGNORECASE)
    if m:
        alias_name = m.group(1)
        if alias_name.lower() == col_name.lower():
            return True
        else:
            return False
        
    # 3) 단순 대입/비교식 (예: a.col1 = b.col22)
    pat_comp1 = r'^(?:[a-zA-Z0-9_]+\.)?%s\s*=\s*(?:[a-zA-Z0-9_]+\.)?[a-zA-Z0-9_]+$' % re.escape(col_name)
    pat_comp2 = r'^(?:[a-zA-Z0-9_]+\.)?[a-zA-Z0-9_]+\s*=\s*(?:[a-zA-Z0-9_]+\.)?%s$' % re.escape(col_name)
    
    if re.match(pat_comp1, s, re.IGNORECASE) or re.match(pat_comp2, s, re.IGNORECASE):
        return True
        
    return False

# ============================================================
# 소스 디렉토리 탐색 및 바이너리 제외
# ============================================================
def is_binary_file(filepath: str) -> bool:
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                return True
    except Exception:
        return True
    return False

def get_source_files(search_dir: str, mids: list = None) -> dict:
    result = {}
    search_dir = os.path.abspath(search_dir)
    
    if not mids:
        default_mid = os.path.basename(os.path.normpath(search_dir))
        files = []
        if os.path.isdir(search_dir):
            for root, _, filenames in os.walk(search_dir):
                for f in filenames:
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
                        filepath = os.path.join(root, f)
                        if not is_binary_file(filepath):
                            files.append(filepath)
            else:
                print("[WARN] 디렉토리가 존재하지 않습니다: %s" % mid_dir)
            result[mid] = files
    return result

# ============================================================
# DB 테이블 DDL 및 적재 모듈
# ============================================================
_DDL_DROP   = "DROP TABLE IF EXISTS {table};"

_DDL_CREATE_RESULT = """
CREATE TABLE {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `run_id`           VARCHAR(30)   NOT NULL                 COMMENT '실행 ID(YYYYMMDD_HHMMSS)',
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
  KEY `idx_tbl_name`  (`tbl_name`(191)),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 정밀 매칭 분석 결과';
"""

_SQL_INSERT_RESULT = """
INSERT INTO {table}
  (run_id, db_name, tbl_name, column_name, type_name, integer_idx,
   mig_dec, tobe_enc_key, tobe_enc_rsn, asis_enc_yn,
   source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

def build_output_table_name(ref_schema: str, ref_tbl_only: str, mid: str) -> str:
    tbl_name = "p190872_%s_%s" % (ref_tbl_only, mid)
    if ref_schema:
        return "`%s`.`%s`" % (ref_schema, tbl_name)
    return "`%s`" % tbl_name

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
    try:
        if v is None or str(v).strip() == "" or str(v).strip().lower() == "none":
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None

# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Query Analyzer Script (v06_gm)")
    parser.add_argument("ref_table", help="검색기준테이블")
    parser.add_argument("search_dir", help="검색디렉토리")
    parser.add_argument("--mid", help="검색디렉토리 하위 MID값 (쉼표 구분)", default=None)
    parser.add_argument("--db", action="store_true", help="DB 적재 활성화")
    parser.add_argument("--conf", help="mysql.conf 파일 경로", default=None)
    parser.add_argument("--where", choices=["old", "new"], help="검색기준테이블 조회 필터", default=None)
    parser.add_argument("--chk", choices=["default", "encdec_no"], help="암호화/복호화 포함 및 제외 필터", default=None)

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

    # 4차수정요청: column_name 기준 중복제거
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
        seen_matches = set() # (filepath, l_num, col_lower) 중복 매칭 방지

        # 집계용 변수 초기화
        total_files_scanned = len(files)
        files_with_matches = set()
        match_line_count = 0
        exclude_line_count = 0

        for filepath in files:
            queries, open_err, orig_lines, raw_content = open_and_extract_queries(filepath)
            if open_err:
                continue
            
            # If no queries were parsed, fall back to analyzing the raw file lines as a single block
            if not queries and raw_content.strip():
                queries = [{"query_text": raw_content, "start_line_no": 1}]

            for q_idx, q_item in enumerate(queries, 1):
                raw_query = q_item["query_text"]
                query_text_upper = raw_query.upper()
                line_no_offset = q_item["start_line_no"]
                query_lines = raw_query.splitlines()

                for col_lower, rx in compiled_col_patterns.items():
                    if rx.search(query_text_upper):
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
                                # 4차수정요청: 포함예시 이외행(순수 칼럼 참조 등)을 제외 텍스트로 축적
                                exclude_str = "[제외] %s %s (테이블: %s)" % (vscode_cmd, orig_col_name, assoc_tables_str)
                                content_str = "[내용] %s" % l_val.strip()
                                mid_exclude_buffer.append(exclude_str)
                                mid_exclude_buffer.append(content_str)
                                mid_exclude_buffer.append("-" * 80)
                                continue

                            # Apply --chk filters
                            is_included = True
                            if args.chk:
                                has_encdec = "default.encrypt" in l_val.lower() or "default.decrypt" in l_val.lower()
                                if args.chk == "default":
                                    is_included = has_encdec
                                elif args.chk == "encdec_no":
                                    is_included = not has_encdec

                            # Generate matching rows
                            if is_included:
                                files_with_matches.add(filepath)
                                match_line_count += 1
                                for ref_row in col_to_rows[col_lower]:
                                    result_row = dict(ref_row)
                                    result_row.update({
                                        "run_id": run_id,
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
                                
                                # print(match_str)
                                # print(content_str)
                                # print("-" * 80)
                                
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

        # Define paths
        csv_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s.csv" % (ref_tbl_only, out_suffix)))
        print_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_print.txt" % (ref_tbl_only, out_suffix)))
        ex_txt_path = os.path.abspath(os.path.join(out_dir, "p190872_%s_%s_exclude.txt" % (ref_tbl_only, out_suffix)))

        # Output file generation per MID if results are present
        if included_results:
            save_csv(included_results, csv_path, CSV_FIELDNAMES, op_dtm)
            print("[INFO] 파일 저장 완료: %s  (%d 건)" % (csv_path, len(included_results)))

            if args.db:
                fq_out_table = build_output_table_name(ref_schema, ref_tbl_only, out_suffix)
                batch = [
                    (
                        run_id,
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
                        op_dtm
                    )
                    for r in included_results
                ]
                db_load_table(mysql_conf, fq_out_table, _DDL_CREATE_RESULT, _SQL_INSERT_RESULT, batch, "결과데이터")
        else:
            print("[INFO] '%s' MID에 대해 추출된 매칭 결과 행이 없습니다. (파일/테이블 미생성)" % mid)

        # Exclude file generation per MID if excluded results are present
        if len(mid_exclude_buffer) > 3:
            with open(ex_txt_path, "w", encoding="utf-8") as ef:
                ef.write("\n".join(mid_exclude_buffer) + "\n")
            print("[INFO] 제외행 내용 파일 생성 완료: %s" % ex_txt_path)

        # ─────────────────────────────────────────────────────────────
        # MID별 실행 결과 상세 요약 화면 출력 및 저장 (7차 수정요청)
        # ─────────────────────────────────────────────────────────────
        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append(" [분석 완료 요약 - MID: %s]" % mid)
        summary_lines.append("=" * 80)
        summary_lines.append("  - 검색 대상 기준 테이블   : %s" % args.ref_table)
        summary_lines.append("  - 검색 대상 소스 파일 수   : %d 개" % total_files_scanned)
        summary_lines.append("  - 매칭 발생 소스 파일 수   : %d 개" % len(files_with_matches))
        summary_lines.append("  - 매칭 건수 (포함)          : %d 건" % match_line_count)
        summary_lines.append("  - 매칭 건수 (제외)          : %d 건" % exclude_line_count)
        summary_lines.append("-" * 80)
        summary_lines.append("  1. 생성 파일 정보")
        if included_results:
            summary_lines.append("     - 결과 CSV 파일   : %s (%d 건)" % (csv_path, len(included_results)))
            summary_lines.append("     - 화면 출력 파일  : %s (%d 건)" % (print_path, match_line_count))
        else:
            summary_lines.append("     - 결과 CSV 파일   : (생성 없음)")
            summary_lines.append("     - 화면 출력 파일  : (생성 없음)")
            
        if len(mid_exclude_buffer) > 3:
            summary_lines.append("     - 제외 로그 파일  : %s (%d 건)" % (ex_txt_path, exclude_line_count))
        else:
            summary_lines.append("     - 제외 로그 파일  : (생성 없음)")
            
        summary_lines.append("  2. DB 적재 정보")
        if args.db and included_results:
            fq_out_table = build_output_table_name(ref_schema, ref_tbl_only, out_suffix)
            summary_lines.append("     - 결과 DB 테이블  : %s (%d 건)" % (fq_out_table, len(included_results)))
        else:
            summary_lines.append("     - 결과 DB 테이블  : (적재 없음)")
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