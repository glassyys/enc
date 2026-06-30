#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v08_3cha_no_omit.py
#
# [실행 형식]
# python p190872_local_chk_v08_3cha_no_omit.py <검색기준테이블> <검색기준소스테이블> [--where <old|new|all>] [--db] [--conf <설정파일>]
#
# [실행 예시]
# python p190872_local_chk_v08_3cha_no_omit.py my_db.my_ref_table my_db.my_src_table --where all --db --conf mysql.conf
#
# [수정 이력]
# ─────────────────────────────────────────────────────────────
# v08_3cha_no_omit (2026-06-30)
#   - p190872_local_chk_v08_3cha.py를 기반으로 무누락(no_omit) 버전 작성
#   - 주석 제외 탐색 구조 개선: 쿼리 단위 파싱 방식 대신 파일 전체 라인 순회 방식으로 변경하여
#     주석인 경우를 제외한 모든 영역(SQL 구문 외부, 리터럴 등 포함)에 대해 누락 없이 매칭 추출
#   - 제외 케이스 수집 및 기록: 원본 라인에 컬럼명이 존재하나 주석 마스킹 상태에서는 존재하지 않는 경우를
#     [제외]로 처리하여 화면 출력 및 별도 CSV 파일(_omit.csv) 생성
#   - 결과 테이블명 변경: 기존 <소스테이블명>_work 에서 <소스테이블명>_no_omit 로 변경
# ===============================================================

import os
import re
import sys
import csv
import argparse
import configparser
from datetime import datetime

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

def _get_cursor(conn):
    if _MYSQL_DRIVER == "connector":
        return conn.cursor(buffered=True)
    return conn.cursor()

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
            # env/mysql.conf 도 추가적으로 확인 (사용자 편의)
            env_fallback = os.path.join(script_dir, "env", "mysql.conf")
            if os.path.isfile(env_fallback):
                path = env_fallback
            else:
                return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path

    try:
        cp = configparser.ConfigParser()
        cp.read(path, encoding='utf-8')
        conf = dict(cp['mysql'])
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
    return None, full_table.strip()

def make_fq(schema, table):
    if schema:
        return "`%s`.`%s`" % (schema, table)
    return "`%s`" % table

# ============================================================
# DB 테이블 조회 로직
# ============================================================
def load_ref_rows_from_db(mysql_conf, ref_table, where_opt="all"):
    """
    검색기준테이블에서 조건에 따라 기준칼럼추출 정보를 가져옵니다.
    """
    rows     = []
    conn     = None
    cursor   = None
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    fq_table = make_fq(ref_schema, ref_tbl_only)

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
        else:
            cursor.execute("SHOW TABLES LIKE %s", (ref_tbl_only,))
        row_chk = cursor.fetchone()
        exists  = (row_chk[0] > 0) if row_chk else False
        if not exists:
            return [], ref_schema, ref_tbl_only, "테이블이 존재하지 않습니다: %s" % ref_table

        # 컬럼 목록 조회
        cursor.execute("SHOW COLUMNS FROM %s" % fq_table)
        columns_info = cursor.fetchall()
        existing_cols = {row[0].lower() for row in columns_info}
        select_cols = [row[0] for row in columns_info]
        select_parts = ["`%s`" % col for col in select_cols]

        # 2. 기준칼럼정보추출 조건 적용
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
    """
    검색기준소스테이블에서 local_file 및 id, mid를 중복없이 가져옵니다.
    """
    files = []
    conn = None
    cursor = None
    src_schema, src_tbl_only = split_schema_table(src_table)
    fq_table = make_fq(src_schema, src_tbl_only)

    try:
        conn = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)

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
# 소스 파싱 및 주석 제거
# ============================================================
def preprocess_only_comments(content):
    """
    주석만 마스킹 처리 (블록 주석 /* ... */, 한 줄 주석 -- 및 #)
    줄 수 유지를 위해 블록 주석 내부의 \n(줄바꿈)은 보존
    """
    # 1. 블록 주석 (/* ... */) 공백 치환 (줄바꿈 보존)
    def repl_block(m):
        text = m.group(0)
        return "".join('\n' if c == '\n' else ' ' for c in text)
    content = re.sub(r"/\*.*?\*/", repl_block, content, flags=re.DOTALL)

    # 2. 한 줄 주석 (--, #) 공백 치환
    def repl_line(m):
        text = m.group(0)
        return " " * len(text)
    content = re.sub(r"(?:--|#)[^\r\n]*", repl_line, content)

    return content

def open_source_file(source_file_path):
    """
    소스 파일을 열어 라인별 목록과 원본 텍스트를 리턴합니다.
    """
    try:
        with open(source_file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        orig_lines = content.splitlines()
        return None, orig_lines, content
    except Exception as e:
        return str(e), [], ""

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
# 결과 테이블 동적 구성 및 DDL
# ============================================================
def setup_result_table(mysql_conf, ref_table, out_table_name):
    """
    요청하신 3차 레이아웃에 맞추어 결과 테이블을 자동 생성합니다.
    """
    ref_schema, ref_tbl_only = split_schema_table(ref_table)
    out_schema = ref_schema if ref_schema else mysql_conf.get("database")
    fq_out_table = make_fq(out_schema, out_table_name)
    
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)
        
        cursor.execute("DROP TABLE IF EXISTS %s" % fq_out_table)
        
        ddl = f"""
        CREATE TABLE {fq_out_table} (
          `id_auto`            BIGINT        NOT NULL AUTO_INCREMENT,
          `id`                 VARCHAR(200)  NULL COMMENT '검색기준소스테이블 ID',
          `mid`                VARCHAR(200)  NULL COMMENT '검색기준소스테이블 MID',
          `source_file`        VARCHAR(500)  NULL COMMENT '검색기준소스테이블 SOURCE_FILE',
          `column_name`        VARCHAR(500)  NULL,
          `tobe_enc_key`       VARCHAR(200)  NULL,
          `conv_tobe_enc_key`   VARCHAR(200)  NULL COMMENT 'Converted tobe_enc_key (e.g. e1)',
          `line_number`        INT           NULL COMMENT '소스전체기준 라인',
          `vscode_open_cmd`    VARCHAR(1000) NULL COMMENT 'vscode 이동 실행 명령어',
          `matched_line`       TEXT          NULL COMMENT '매칭된 행 내용',
          `run_id`             VARCHAR(30)   NULL,
          `op_dtm`             DATETIME      NULL,
          PRIMARY KEY (`id_auto`),
          KEY `idx_run_id` (`run_id`),
          KEY `idx_col_name` (`column_name`(191))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='3차 암호화 대상 검출 결과 (무누락)';
        """
        
        cursor.execute(ddl)
        conn.commit()
        
        col_names = [
            "id", "mid", "source_file", "column_name", "tobe_enc_key", "conv_tobe_enc_key",
            "line_number", "vscode_open_cmd", "matched_line", "run_id", "op_dtm"
        ]
        return col_names, fq_out_table, None
    except Exception as e:
        return [], "", "결과 테이블 생성 실패: %s" % str(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def insert_results_to_db(mysql_conf, fq_out_table, col_names, results):
    if not results:
        return 0, None
    
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = _get_cursor(conn)
        
        cols_str = ", ".join(["`%s`" % col for col in col_names])
        placeholders = ", ".join(["%s"] * len(col_names))
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (fq_out_table, cols_str, placeholders)
        
        batch = []
        for r in results:
            row_data = []
            for col in col_names:
                row_data.append(r.get(col, None))
            batch.append(row_data)
            
        # max_allowed_packet 및 패킷 꼬임 에러 방지를 위해 500건 단위 청크 분할 executemany 실행
        chunk_size = 500
        for i in range(0, len(batch), chunk_size):
            chunk = batch[i:i + chunk_size]
            cursor.executemany(sql, chunk)
            conn.commit()
            
        return len(batch), None
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return 0, "DB 적재 실패: %s" % str(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# ============================================================
# CSV 저장 모듈
# ============================================================
def save_csv(rows, filepath, fieldnames, op_dtm):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
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
    parser = argparse.ArgumentParser(description="3차 암호화 대상 검출 프로그램 - 무누락 버전 (v08_3cha_no_omit)")
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
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 80)
    print(" [3차 암호화 대상 검출 분석 시작 (무누락 버전)]")
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

    # column_name 중복 제거하여 검색 속도 향상 및 중복 결과 방지
    unique_ref_rows = []
    seen_cols = set()
    col_to_row = {}
    for r in ref_rows:
        col_name = r.get("column_name", "").strip()
        if not col_name:
            continue
        c_lower = col_name.lower()
        if c_lower not in seen_cols:
            seen_cols.add(c_lower)
            col_to_row[c_lower] = r
            unique_ref_rows.append(r)
    print("[INFO] 중복 제거 후 검색기준 칼럼 수: %d 개" % len(unique_ref_rows))

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

    # 4. 소스 파일 매칭 탐색 루프 (라인 단위 전체 매칭)
    included_results = []
    omit_results = []
    seen_matches = set()
    seen_omits = set()
    total_files = len(files_info)
    matched_file_count = 0
    total_matches = 0
    total_omits = 0
    mid_print_buffer = []
    screen_detail_print_count = 0

    print("[INFO] 소스 파일 매칭 검색을 시작합니다...")
    for idx, f_info in enumerate(files_info, 1):
        filepath = f_info["local_file"]
        filepath_abs = os.path.abspath(filepath)
        if not os.path.isfile(filepath_abs):
            print("[%d/%d] [WARN] 파일이 존재하지 않습니다 (Skip): %s" % (idx, total_files, filepath))
            continue

        open_err, orig_lines, raw_content = open_source_file(filepath_abs)
        if open_err:
            print("[%d/%d] [WARN] 파일 오픈 실패 (Skip): %s, 에러: %s" % (idx, total_files, filepath, open_err))
            continue

        # 파일 오픈 성공 후 분석 시작할 때 local_file 경로 및 ID 출력
        file_start_msg = "[진행] ID: %s, local_file: %s" % (f_info["id"], filepath)
        print(file_start_msg)
        mid_print_buffer.append(file_start_msg)

        # 주석 마스킹 처리된 내용 생성
        clean_content = preprocess_only_comments(raw_content)
        clean_lines = clean_content.splitlines()

        # 1차 필터링: 해당 파일에 실제로 존재하는 컬럼명 패턴들만 선별 (성능 병목 해결)
        active_patterns = {}
        raw_content_upper = raw_content.upper()
        for col_lower, rx in compiled_col_patterns.items():
            if rx.search(raw_content_upper):
                active_patterns[col_lower] = rx

        file_matched = False
        num_lines = min(len(orig_lines), len(clean_lines))
        
        if active_patterns:
            for l_idx in range(num_lines):
                orig_line = orig_lines[l_idx]
                clean_line = clean_lines[l_idx]
                l_num = l_idx + 1

                for col_lower, rx in active_patterns.items():
                    if rx.search(orig_line):
                        # 원본에 매칭되는 경우
                        if rx.search(clean_line):
                            # 주석이 제거된 라인에도 매칭되는 경우 -> 매칭 성공
                            match_key = (filepath_abs, l_num, col_lower)
                            if match_key in seen_matches:
                                continue
                            seen_matches.add(match_key)

                            orig_col_name = col_to_row[col_lower]["column_name"]
                            vscode_cmd = "code -g %s:%s" % (filepath_abs, l_num)
                            file_matched = True
                            total_matches += 1

                            # 결과 데이터 생성
                            ref_row = col_to_row[col_lower]
                            tobe_enc_key = ref_row.get("tobe_enc_key", "")
                            conv_key = convert_key_to_code(tobe_enc_key)

                            result_row = {
                                "id": f_info["id"],
                                "mid": f_info["mid"],
                                "source_file": f_info.get("source_file", ""),
                                "column_name": orig_col_name,
                                "tobe_enc_key": tobe_enc_key,
                                "conv_tobe_enc_key": conv_key,
                                "line_number": l_num,
                                "vscode_open_cmd": vscode_cmd,
                                "matched_line": orig_line.strip(),
                                "run_id": run_id,
                                "op_dtm": op_dtm
                            }
                            included_results.append(result_row)

                            match_str = "[매칭] %s %s" % (vscode_cmd, orig_col_name)
                            content_str = "[내용] %s" % orig_line.strip()

                            if screen_detail_print_count < 10:
                                print(match_str)
                                print(content_str)
                                print("-" * 80)
                                screen_detail_print_count += 1
                            elif screen_detail_print_count == 10:
                                print("[INFO] 상위 10개 검출 결과만 화면에 출력되었습니다. 전체 결과는 파일 및 DB를 확인하세요.")
                                screen_detail_print_count += 1

                            mid_print_buffer.append(match_str)
                            mid_print_buffer.append(content_str)
                            mid_print_buffer.append("-" * 80)
                        else:
                            # 원본에는 있으나 주석 마스킹 후에는 존재하지 않는 경우 -> 제외 건
                            omit_key = (filepath_abs, l_num, col_lower)
                            if omit_key in seen_omits:
                                continue
                            seen_omits.add(omit_key)

                            orig_col_name = col_to_row[col_lower]["column_name"]
                            vscode_cmd = "code -g %s:%s" % (filepath_abs, l_num)
                            total_omits += 1

                            ref_row = col_to_row[col_lower]
                            tobe_enc_key = ref_row.get("tobe_enc_key", "")
                            conv_key = convert_key_to_code(tobe_enc_key)

                            omit_row = {
                                "id": f_info["id"],
                                "mid": f_info["mid"],
                                "source_file": f_info.get("source_file", ""),
                                "column_name": orig_col_name,
                                "tobe_enc_key": tobe_enc_key,
                                "conv_tobe_enc_key": conv_key,
                                "line_number": l_num,
                                "vscode_open_cmd": vscode_cmd,
                                "matched_line": orig_line.strip(),
                                "run_id": run_id,
                                "op_dtm": op_dtm
                            }
                            omit_results.append(omit_row)

                            omit_str = "[제외] %s %s" % (vscode_cmd, orig_col_name)
                            omit_content_str = "[내용] %s" % orig_line.strip()

                            if screen_detail_print_count < 10:
                                print(omit_str)
                                print(omit_content_str)
                                print("-" * 80)
                                screen_detail_print_count += 1
                            elif screen_detail_print_count == 10:
                                print("[INFO] 상위 10개 검출 결과만 화면에 출력되었습니다. 전체 결과는 파일 및 DB를 확인하세요.")
                                screen_detail_print_count += 1

                            mid_print_buffer.append(omit_str)
                            mid_print_buffer.append(omit_content_str)
                            mid_print_buffer.append("-" * 80)

        if file_matched:
            matched_file_count += 1
        else:
            # 매칭되는 자료가 없더라도 id값 기준 1개의 기본 행 생성
            default_line_no = 1
            vscode_cmd = "code -g %s:%s" % (filepath_abs, default_line_no)
            result_row = {
                "id": f_info["id"],
                "mid": f_info["mid"],
                "source_file": f_info.get("source_file", ""),
                "column_name": "",
                "tobe_enc_key": "",
                "conv_tobe_enc_key": "",
                "line_number": default_line_no,
                "vscode_open_cmd": vscode_cmd,
                "matched_line": "",
                "run_id": run_id,
                "op_dtm": op_dtm
            }
            included_results.append(result_row)

    print("-" * 80)
    print("[INFO] 매칭 탐색 종료")
    print("  - 전체 조사 파일 수: %d 개" % total_files)
    print("  - 매칭 발견 파일 수: %d 개" % matched_file_count)
    print("  - 추출된 매칭 건수: %d 건" % total_matches)
    print("  - 제외된 주석 건수: %d 건" % total_omits)
    print("-" * 80)

    # 5. 결과 테이블 설정 및 DB 생성
    _, src_tbl_only = split_schema_table(args.src_table)
    out_table_name = "%s_no_omit" % src_tbl_only
    print("[INFO] 결과 테이블 자동 구성 중: %s ..." % out_table_name)
    col_names, fq_out_table, setup_err = setup_result_table(mysql_conf, args.ref_table, out_table_name)
    if setup_err:
        print("[ERROR] %s" % setup_err)
        sys.exit(1)
    print("[INFO] 결과 테이블 레이아웃 구성 완료.")

    # 6. CSV 파일 저장
    csv_filename = "%s.csv" % out_table_name
    csv_filepath = os.path.join(out_dir, csv_filename)
    print("[INFO] CSV 저장 처리 중: %s" % csv_filepath)
    save_csv(included_results, csv_filepath, col_names, op_dtm)
    print("[INFO] CSV 파일 저장 완료.")

    # 6.3 제외 CSV 파일 저장
    omit_csv_filename = "%s_omit.csv" % out_table_name
    omit_csv_filepath = os.path.join(out_dir, omit_csv_filename)
    print("[INFO] 제외 CSV 저장 처리 중: %s" % omit_csv_filepath)
    save_csv(omit_results, omit_csv_filepath, col_names, op_dtm)
    print("[INFO] 제외 CSV 파일 저장 완료.")

    # 6.5 화면 출력 내용 파일로 생성
    print_filename = "%s_print.txt" % out_table_name
    print_filepath = os.path.join(out_dir, print_filename)
    try:
        with open(print_filepath, "w", encoding="utf-8") as pf:
            pf.write("\n".join(mid_print_buffer) + "\n")
        print("[INFO] 화면 출력 내용 파일 저장 완료: %s" % print_filepath)
    except Exception as e:
        print("[WARN] 화면 출력 파일 저장 에러: %s" % str(e))

    # 7. DB 테이블 적재
    if args.db:
        print("[INFO] DB 적재를 진행합니다: %s" % fq_out_table)
        loaded_count, db_load_err = insert_results_to_db(mysql_conf, fq_out_table, col_names, included_results)
        if db_load_err:
            print("[ERROR] %s" % db_load_err)
            sys.exit(1)
        print("[INFO] DB 적재 완료: %d 행 적재됨" % loaded_count)
    else:
        print("[INFO] --db 옵션이 지정되지 않아 DB 적재는 생략되었습니다.")

    print("=" * 80)
    print(" [작업이 정상적으로 종료되었습니다]")
    print("=" * 80)

if __name__ == "__main__":
    main()