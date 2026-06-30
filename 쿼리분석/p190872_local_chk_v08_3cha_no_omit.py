#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# p190872_local_chk_v08_3cha_no_omit.py
#
# [실행 형식]
# python p190872_local_chk_v08_3cha_no_omit.py <검색기준테이블> <검색기준소스테이블> [--where <old|new|all>] [--db] [--conf <설정파일>]
#
# [수정 사항 요약]
#   - 기존 v08_3cha의 화면 출력 스트림 형태 및 출력 보관 정책 완벽 유지
#   - 가공 필터(is_omit) 제거 상태로 주석 구간 외 column_name 무조건 추출 로직 유지
#   - 분석 진행 중 화면(콘솔)에 매칭 라인을 출력하는 부분은 최대 10건까지만 제한 표기 적용
#   - 화면 출력 제한과 관계없이 하위 모든 파일 소스 정보 추출 및 파일/DB 전체 적재 기능은 온전히 유지
#   - Python 2.7.5 하위 호환성 완벽 지원 (codecs.open 및 포매팅 규칙 준수)
# ===============================================================

import os
import re
import sys
import csv
import codecs
import argparse
import configparser
from datetime import datetime

# MySQL 패키지 호환성 동적 바인딩
try:
    import mysql.connector
    MYSQL_DRIVER = "connector"
except ImportError:
    try:
        import pymysql
        MYSQL_DRIVER = "pymysql"
    except ImportError:
        MYSQL_DRIVER = None

TARGET_EXTENSIONS = ('.sql', '.hql', '.uld', '.ld', '.sh')

def get_db_connection(conf):
    if MYSQL_DRIVER == "connector":
        return mysql.connector.connect(
            host=conf['host'], port=int(conf['port']),
            user=conf['user'], password=conf['password'],
            database=conf['database'], charset=conf.get('charset', 'utf8mb4')
        )
    elif MYSQL_DRIVER == "pymysql":
        return pymysql.connect(
            host=conf['host'], port=int(conf['port']),
            user=conf['user'], password=conf['password'],
            database=conf['database'], charset=conf.get('charset', 'utf8mb4'),
            autocommit=False
        )
    else:
        raise ImportError("MySQL 드라이버를 찾을 수 없습니다. pymysql 또는 mysql-connector-python을 설치하세요.")

def load_config(conf_path):
    if not os.path.exists(conf_path):
        return None, "설정 파일이 없습니다: %s" % conf_path
    cp = configparser.ConfigParser()
    try:
        cp.read(conf_path)
        conf = dict(cp['mysql'])
        if 'port' not in conf: conf['port'] = '3306'
        return conf, None
    except Exception as e:
        return None, "설정 분석 오류: %s" % str(e)

def parse_schema_table(fq_name):
    parts = fq_name.split('.')
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, fq_name

def make_fq(schema, table):
    if schema: return "%s.%s" % (schema, table)
    return table

def load_ref_columns(conf, ref_table, where_opt):
    schema, tbl = parse_schema_table(ref_table)
    conn = get_db_connection(conf)
    cursor = conn.cursor()
    
    # 패킷 꼬임 원천 방지용 스키마 카운트 사전 스캔 완료
    cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s", (tbl,))
    if cursor.fetchall()[0][0] == 0:
        cursor.close()
        conn.close()
        return None, "기준 마스터 테이블을 찾을 수 없습니다: %s" % ref_table

    col_sql = "SHOW COLUMNS FROM %s" % make_fq(schema, tbl)
    cursor.execute(col_sql)
    existing_cols = set([row[0].lower() for row in cursor.fetchall()])

    sel_fields = []
    for f in ["db_name", "tbl_name", "column_name", "tobe_enc_key", "tobe_enc_rsn", "asis_enc_yn"]:
        if f in existing_cols: sel_fields.append("`%s`" % f)
        else: sel_fields.append("NULL AS `%s`" % f)

    wh_cond = ["1=1"]
    if "tobe_enc_key" in existing_cols:
        wh_cond.append("`tobe_enc_key` IS NOT NULL AND `tobe_enc_key` <> ''")
    
    if where_opt == 'old' and "asis_enc_yn" in existing_cols:
        wh_cond.append("`asis_enc_yn` = 'Y'")
    elif where_opt == 'new' and "asis_enc_yn" in existing_cols:
        wh_cond.append("`asis_enc_yn` = 'N'")

    main_sql = "SELECT %s FROM %s WHERE %s" % (", ".join(sel_fields), make_fq(schema, tbl), " AND ".join(wh_cond))
    cursor.execute(main_sql)
    rows = cursor.fetchall()
    
    columns_list = []
    for r in rows:
        columns_list.append({
            "db_name": r[0] or "", "tbl_name": r[1] or "", "column_name": r[2] or "",
            "tobe_enc_key": r[3] or "", "tobe_enc_rsn": r[4] or "", "asis_enc_yn": r[5] or ""
        })
        
    cursor.close()
    conn.close()
    return columns_list, None

def load_source_files(conf, src_table):
    schema, tbl = parse_schema_table(src_table)
    conn = get_db_connection(conf)
    cursor = conn.cursor()
    
    sql = "SELECT DISTINCT local_file FROM %s WHERE local_file IS NOT NULL AND local_file <> ''" % make_fq(schema, tbl)
    cursor.execute(sql)
    files = [r[0] for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return files

def preprocess_query(content):
    content = "\n".join(l for l in content.splitlines() if not l.lstrip().startswith('#'))
    content = "\n".join(l for l in content.splitlines() if not re.match(r"(?i)^\s*DBMS_OUTPUT", l))
    content = "\n".join(l for l in content.splitlines() if not (l.strip().startswith("/*") and l.strip().endswith("*/")))
    
    pat = re.compile(r"('(?:[^']|'')*')|(\"(?:[^\"]|\"\")*\")|(--[^\n]*$)|(/\*.*?\*/)", re.M | re.S)
    def repl(m):
        if m.group(1) or m.group(2): return m.group(0)
        return ""
    return pat.sub(repl, content)

def extract_queries_from_raw(file_path):
    if not os.path.exists(file_path): return [], 0, []
    try:
        with codecs.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception:
        return [], 0, []
        
    orig_lines = raw.splitlines()
    total_lines = len(orig_lines)
    clean_text = preprocess_query(raw)
    
    q_start_pat = re.compile(
        r"(?i)\b(CREATE\s+OR\s+REPLACE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|"
        r"CREATE\s+(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?(?:TABLE|VIEW)|CREATE\s+TABLE|CREATE\s+VIEW|"
        r"ALTER\s+TABLE|ALTER\s+VIEW|DROP\s+TABLE|DROP\s+VIEW|TRUNCATE\s+TABLE|REPLACE\s+VIEW|"
        r"MERGE\s+INTO|MERGE|UPSERT|INSERT|UPDATE|DELETE|SELECT|WITH|EXECUTE)\b"
    )
    
    queries = []
    pos = 0
    length = len(clean_text)
    last_idx = 0
    
    while pos < length:
        m = q_start_pat.search(clean_text, pos)
        if not m: break
        start = m.start()
        
        if m.group(1).upper().startswith("END"):
            l_start = clean_text.rfind("\n", 0, start) + 1
            l_end = clean_text.find("\n", start)
            if l_end == -1: l_end = length
            if re.match(r"(?i)^\s*END\s+IF\b", clean_text[l_start:l_end]):
                pos = l_end
                continue
                
        end = start
        depth = 0
        in_str = False
        q_char = None
        
        while end < length:
            ch = clean_text[end]
            if ch in ("'", '"'):
                if not in_str:
                    in_str = True
                    q_char = ch
                elif q_char == ch:
                    in_str = False
            elif not in_str:
                if ch == "(": depth += 1
                elif ch == ")": depth = max(depth - 1, 0)
                elif ch == ";" and depth == 0:
                    end += 1
                    break
            end += 1
            
        q_str = clean_text[start:end].strip()
        if q_str and ";" in q_str:
            st_line = 1
            first_q_line = q_str.splitlines()[0].strip()
            if first_q_line:
                for idx in range(last_idx, len(orig_lines)):
                    if first_q_line in orig_lines[idx]:
                        st_line = idx + 1
                        last_idx = idx
                        break
            queries.append((q_str, st_line))
        pos = end
        
    return queries, total_lines, orig_lines

def setup_result_table(conf, ref_table, out_table_name):
    schema, _ = parse_schema_table(ref_table)
    out_schema, out_tbl = parse_schema_table(out_table_name)
    if not out_schema: out_schema = schema
    
    fq_out = make_fq(out_schema, out_tbl)
    
    conn = get_db_connection(conf)
    cursor = conn.cursor()
    
    ddl = """
    CREATE TABLE IF NOT EXISTS %s (
        `id` BIGINT NOT NULL AUTO_INCREMENT,
        `mid` VARCHAR(100),
        `file_name` VARCHAR(500),
        `line_number` INT,
        `column_name` VARCHAR(250),
        `matched_line` TEXT,
        `tobe_enc_key` VARCHAR(250),
        `tobe_enc_rsn` TEXT,
        `vscode_open_cmd` TEXT,
        `op_dtm` DATETIME,
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """ % fq_out
    
    try:
        cursor.execute(ddl)
        conn.commit()
    except Exception as e:
        return None, None, "출력 적재용 테이블 생성 실패: %s" % str(e)
    finally:
        cursor.close()
        conn.close()
        
    cols = ["mid", "file_name", "line_number", "column_name", "matched_line", "tobe_enc_key", "tobe_enc_rsn", "vscode_open_cmd"]
    return cols, fq_out, None

def save_csv(data_buffer, file_path, fields, op_dtm):
    with codecs.open(file_path, "w", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(fields + ["op_dtm"])
        for r in data_buffer:
            row_data = [r.get(f, "") for f in fields] + [op_dtm]
            processed = []
            for item in row_data:
                if isinstance(item, unicode if sys.version_info[0] < 3 else str):
                    processed.append(item.encode('utf-8') if sys.version_info[0] < 3 else item)
                else:
                    processed.append(str(item))
            writer.writerow(processed)

def insert_results_to_db(conf, table_name, fields, data_buffer):
    if not data_buffer: return 0, None
    conn = get_db_connection(conf)
    cursor = conn.cursor()
    
    ins_fields = ["`%s`" % f for f in fields] + ["`op_dtm`"]
    placeholders = ", ".join(["%s"] * len(ins_fields))
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (table_name, ", ".join(ins_fields), placeholders)
    
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    batch = []
    for r in data_buffer:
        row = [r.get(f, None) for f in fields] + [op_dtm]
        batch.append(row)
        
    inserted = 0
    try:
        chunk_size = 500
        for idx in range(0, len(batch), chunk_size):
            chunk = batch[idx:idx+chunk_size]
            cursor.executemany(sql, chunk)
            conn.commit()
            inserted += len(chunk)
    except Exception as e:
        conn.rollback()
        return inserted, str(e)
    finally:
        cursor.close()
        conn.close()
    return inserted, None

def main():
    parser = argparse.ArgumentParser(description="컬럼 단순 무조건 추출용 확장 모듈 v08_no_omit (화면출력 10건 제한 버전)")
    parser.add_argument("ref_table", help="기준 정보 테이블 스키마")
    parser.add_argument("src_table", help="소스 대상 리스트 메타 스키마")
    parser.add_argument("--where", choices=["old", "new", "all"], default="all", help="마스터 데이터 조회 필터링 분기")
    parser.add_argument("--db", action="store_true", help="결과물 원격 마이그레이션 적재 유무 플래그")
    parser.add_argument("--conf", default="mysql.conf", help="원격 접속 구성 설정 자산 정보")
    args = parser.parse_args()

    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    if not os.path.exists(out_dir): os.makedirs(out_dir)

    # 대시보드 헤더 스트림 보존 출력
    print("=" * 80)
    print(" [p190872_local_chk_v08_3cha_no_omit 최적화 단순 매칭 스캔 가동] ")
    print("=" * 80)

    conf, err = load_config(args.conf)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    ref_columns, db_err = load_ref_columns(conf, args.ref_table, args.where)
    if db_err:
        print("[ERROR] 마스터 로드 오류: %s" % db_err)
        sys.exit(1)
    print("[INFO] 분석용 마스터 컬럼 자산 확보: %d 건" % len(ref_columns))

    source_paths = load_source_files(conf, args.src_table)
    print("[INFO] 탐색 대상 물리 소스 파일 개수: %d 건" % len(source_paths))
    print("-" * 80)

    compiled_patterns = {}
    for item in ref_columns:
        c_name = item['column_name'].upper()
        if c_name not in compiled_patterns:
            compiled_patterns[c_name] = re.compile(r"\b%s\b" % re.escape(item['column_name']), re.IGNORECASE)

    included_results = []
    excluded_results = []  
    mid_print_buffer = []  # 기존의 화면 출력 버퍼 구조 자산 완벽 유지

    console_print_count = 0  # 화면 출력 제한 제어용 카운터 변수

    for f_path in source_paths:
        if not f_path.lower().endswith(TARGET_EXTENSIONS): continue
        
        norm_path = os.path.normpath(f_path)
        path_tokens = norm_path.split(os.sep)
        mid = "UNKNOWN_MID"
        for t in reversed(path_tokens):
            if t.startswith("mid") or t.startswith("MID"):
                mid = t
                break
                
        queries, total_lines, orig_lines = extract_queries_from_raw(f_path)
        
        try:
            with codecs.open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_full_text = f.read()
            raw_full_lines = raw_full_text.splitlines()
        except Exception:
            raw_full_lines = []

        # 1차: 유효 내부 쿼리 블록 단위 검사 및 정보 추출 (백엔드 로직 100% 보존 유지)
        for q_text, st_line_no in queries:
            q_lines = q_text.splitlines()
            
            for item in ref_columns:
                col = item['column_name']
                col_up = col.upper()
                rx = compiled_patterns.get(col_up)
                if not rx: continue
                if not rx.search(q_text): continue
                
                for q_offset, q_line in enumerate(q_lines):
                    if not rx.search(q_line): continue
                    
                    real_line_no = st_line_no + q_offset if st_line_no else 1
                    vsc_cmd = "code -g %s:%d" % (f_path, real_line_no)
                    
                    # 수집 구조체 작성
                    res_row = {
                        "mid": mid, "file_name": f_path, "line_number": real_line_no,
                        "column_name": col, "matched_line": q_line.strip(),
                        "tobe_enc_key": item['tobe_enc_key'], "tobe_enc_rsn": item['tobe_enc_rsn'],
                        "vscode_open_cmd": vsc_cmd
                    }
                    included_results.append(res_row)

                    # [핵심제어] 화면(콘솔) 출력 구동은 정확히 10건까지만 수행하도록 제한
                    if console_print_count < 10:
                        log_line = "[MATCH] %s | 파일: %s (라인:%d) | 컬럼: %s -> 문장: %s" % (
                            mid, f_path, real_line_no, col, q_line.strip()
                        )
                        print(log_line)
                        mid_print_buffer.append(log_line)
                        console_print_count += 1
                    elif console_print_count == 10:
                        # 10건 초과 시점 최초 1회 안내 문구 출력
                        log_line = "[INFO] 화면 출력 상한선(10건)에 도달하여 이후 상세 출력은 화면에서 생략합니다. (파일/DB에는 정상 추출 적재 처리됨)"
                        print(log_line)
                        mid_print_buffer.append(log_line)
                        console_print_count += 1

        # 2차: 주석 격리 검사 추적 처리 (로직 구조 그대로 유지)
        for idx, orig_l in enumerate(raw_full_lines, 1):
            for item in ref_columns:
                col = item['column_name']
                rx = compiled_patterns.get(col.upper())
                if rx and rx.search(orig_l):
                    is_already_inc = any(r['file_name'] == f_path and r['line_number'] == idx and r['column_name'] == col for r in included_results)
                    if not is_already_inc:
                        excluded_results.append({
                            "mid": mid, "file_name": f_path, "line_number": idx,
                            "column_name": col, "exclude_reason": "COMMENT_SECTION_OR_OUT_OF_DML",
                            "matched_line": orig_l.strip(), "tobe_enc_key": item['tobe_enc_key']
                        })

    # 3차: 기존 종합 통계 요약 피드백 대시보드 스트림 보존 처리
    print("-" * 80)
    print("[INFO] 매칭 탐색 최종 프로세스 요약:")
    print("  - 가공 필터 해제 총 인클루드 건수 : %d 건" % len(included_results))
    print("  - 주석 및 예외 격리 세부 제외 건수 : %d 건" % len(excluded_results))
    print("-" * 80)

    _, ref_tbl_only = parse_schema_table(args.ref_table)
    out_table_base = "p190872_%s_v08_3cha_no_omit" % ref_tbl_only

    # 정식 전체 파일 적재 보존
    main_csv = os.path.join(out_dir, "%s.csv" % out_table_base)
    main_fields = ["mid", "file_name", "line_number", "column_name", "matched_line", "tobe_enc_key", "tobe_enc_rsn", "vscode_open_cmd"]
    save_csv(included_results, main_csv, main_fields, op_dtm)
    print("[INFO] 무조건 매칭 완료 정식 CSV 출력 완료: %s (%d 건)" % (main_csv, len(included_results)))

    # 주석 격리 제외 파일 전체 적재 보존
    exc_csv = os.path.join(out_dir, "%s_exclude.csv" % out_table_base)
    exc_fields = ["mid", "file_name", "line_number", "column_name", "exclude_reason", "matched_line", "tobe_enc_key"]
    save_csv(excluded_results, exc_csv, exc_fields, op_dtm)
    print("[INFO] 예외 격리 주석 데이터 파일 출력 완료: %s (%d 건)" % (exc_csv, len(excluded_results)))

    # 10건 화면 보관 덤프 로그 세이브 처리
    print_filename = "%s_print.txt" % out_table_base
    print_filepath = os.path.join(out_dir, print_filename)
    try:
        with codecs.open(print_filepath, "w", encoding="utf-8") as pf:
            pf.write("\n".join(mid_print_buffer) + "\n")
        print("[INFO] 화면 출력 복사본 파일 저장 완료: %s" % print_filepath)
    except Exception as e:
        print("[WARN] 화면 출력 파일 저장 에러: %s" % str(e))

    # 원격 타겟 DB 확장 마이그레이션 적재 (전체 수집건 데이터 무결 유지)
    if args.db:
        print("-" * 80)
        print("[INFO] 원격 데이터베이스 타겟 테이블 벌크 적재 작업을 시작합니다...")
        cols_main, fq_main, err_m = setup_result_table(conf, args.ref_table, out_table_base)
        if err_m:
            print("[ERROR] 적재 레이아웃 매핑 실패: %s" % err_m)
            sys.exit(1)
            
        ins_cnt, db_err = insert_results_to_db(conf, fq_main, cols_main, included_results)
        if db_err:
            print("[ERROR] 원격 마이그레이션 적재 중 에러 발생: %s" % db_err)
        else:
            print("[INFO] 수동 변경 격리 테이블 전용 적재 성공 완료: %d 행 -> %s" % (ins_cnt, fq_main))

    print("=" * 80)
    print(" [p190872_local_chk_v08_3cha_no_omit 모듈 가동 프로세스 완전 종료] ")
    print("=" * 80)

if __name__ == "__main__":
    main()