#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_find_v002.py
#
# 실행예시:
#   python3 sql_find_v001.py <검색대상_디렉토리> <CSV파일명> <칼럼명1> <칼럼명2> [--conf mysql.conf 경로]
#   python3 sql_find_v002.py /NAS/MIDP/DBMSVC/MIDP/TMT key1_test.csv enc_rsn_desc key [--conf mysql.conf 경로]
#
# 설명:
# 2. find소스(sql_find_v001.py)
# 1) 실행시 검색할디렉토리와 csv파일명 칼럼명 파라미터로 설정
# 2) 소스하위디렉토리 out 내부의 .csv 파일을 읽기
# 3) 첫번재 행을 칼럼명으로 인식해서 실행시 지정된 칼럼명을 지정하면 첫번째 이후 행의 단어리스트를 메모리저장후
# 4) 실행시 디렉토리하위 소스 내용 읽는다
# 5) 3)번에서 저장한 단어 기준으로 라인의 정보와 소스와 디렉토리 정보를 테이블에 등록
# 6) 테이블명은 기존소스 규칙대로 지정
# - CSV 파일에서 '칼럼명1'과 '칼럼명2'의 값을 추출하여 매핑합니다.
# - '칼럼명1'의 값을 기준으로 소스 코드에서 해당 단어가 완전 일치(exact match)하는 라인을 찾습니다.
# - DB 테이블 적재 시, 매치된 단어('칼럼명1' 값)와 함께 추가 정보인 '칼럼명2'의 값을 새로운 칼럼으로 등록합니다.
# ===============================================================

import os
import sys
import csv
import codecs
import re
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 / 디렉토리 경로 설정
# ============================================================
PROGRAM_NAME    = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR      = os.path.dirname(os.path.abspath(sys.argv[0]))
OUT_DIR         = os.path.join(SCRIPT_DIR, "out")
MYSQL_CONF_FILE = "mysql.conf"

# 대상 확장자 규칙
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}

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
            "MySQL 드라이버가 없습니다. "
            "pip install pymysql 또는 pip install mysql-connector-python 을 설치하세요."
        )

# ============================================================
# mysql.conf 로드
# ============================================================
def load_mysql_conf(explicit_path=None):
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), MYSQL_CONF_FILE)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        fallback_path = os.path.join(SCRIPT_DIR, MYSQL_CONF_FILE)
        if os.path.isfile(fallback_path):
            path = fallback_path
        else:
            return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path

    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)

    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."

    conf = dict(cp.items("mysql"))
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
    return conf, None

# ============================================================
# DDL / INSERT SQL 정의
# ============================================================
_DDL_DROP = """
DROP TABLE IF EXISTS `{table}`;
"""

_DDL_CREATE = """
CREATE TABLE `{table}` (
  `id`             BIGINT        NOT NULL AUTO_INCREMENT,
  `run_id`         VARCHAR(30)   NOT NULL  COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `base_directory` VARCHAR(500)  NOT NULL  COMMENT '소스파일 디렉토리 경로',
  `file_name`      VARCHAR(500)  NOT NULL  COMMENT '파일명',
  `dir_file`       TEXT          NOT NULL  COMMENT '소스파일 전체경로',
  `line_no`        INT           NOT NULL  COMMENT '라인 번호',
  `line_content`   TEXT          NULL      COMMENT '라인 내용',
  `search_column1` VARCHAR(200)  NOT NULL  COMMENT '검색 기준 칼럼명1',
  `search_column2` VARCHAR(200)  NOT NULL  COMMENT '추가 등록 칼럼명2',
  `matched_word1`  VARCHAR(500)  NOT NULL  COMMENT '매치된 단어(칼럼1)',
  `matched_word2`  VARCHAR(500)  NULL      COMMENT '매치된 단어(칼럼2)',
  `op_dtm`         DATETIME      NOT NULL  COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id` (`run_id`),
  KEY `idx_file`   (`file_name`(191)),
  KEY `idx_word`   (`matched_word1`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 키워드 매칭 정보';
"""

_SQL_INSERT = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file,
   line_no, line_content, search_column1, search_column2, matched_word1, matched_word2, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# ============================================================
# 라인에서 주석 제거 함수
# ============================================================
def remove_comments_from_line(line, file_ext):
    if not line:
        return line
    
    file_ext_lower = file_ext.lower()
    
    if file_ext_lower in {".sql", ".hql", ".uld", ".ld"}:
        comment_pos = line.find("--")
        if comment_pos != -1:
            line = line[:comment_pos]
    elif file_ext_lower == ".sh":
        comment_pos = line.find("#")
        if comment_pos != -1:
            line = line[:comment_pos]
    
    return line.strip()

# ============================================================
# 동적 테이블명 생성 함수
# ============================================================
def build_dynamic_table_name(source_dir):
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return "%s_%s" % (PROGRAM_NAME, last_dir)

# ============================================================
# DB 적재 (CREATE IF NOT EXISTS → BATCH INSERT)
# ============================================================
def db_insert_matches(rows_buffer, run_id, op_dtm, mysql_conf, source_dir):
    table_name = build_dynamic_table_name(source_dir)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        cursor.execute(_DDL_DROP.format(table=table_name))
        conn.commit()

        cursor.execute(_DDL_CREATE.format(table=table_name))
        conn.commit()

        batch = [
            (
                run_id,
                r["base_directory"], r["file_name"], r["dir_file"],
                r["line_no"],        r["line_content"],
                r["search_column1"], r["search_column2"],
                r["matched_word1"],  r["matched_word2"],
                op_dtm,
            )
            for r in rows_buffer
        ]

        if batch:
            cursor.executemany(_SQL_INSERT.format(table=table_name), batch)
            conn.commit()

        return len(batch)

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        sys.stderr.write("[ERROR] DB 적재 실패: %s\n" % str(e))
        raise e
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# ============================================================
# 인수 파싱
# ============================================================
def parse_args():
    args = sys.argv[1:]
    search_dir   = None
    csv_filename = None
    column_name1 = None
    column_name2 = None
    conf_path    = None

    i = 0
    while i < len(args):
        if args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]
                i += 2
            else:
                print("[오류] --conf 다음에는 mysql.conf 파일의 경로를 입력해 주십시오.")
                sys.exit(1)
        else:
            if search_dir is None:
                search_dir = args[i]
            elif csv_filename is None:
                csv_filename = args[i]
            elif column_name1 is None:
                column_name1 = args[i]
            elif column_name2 is None:
                column_name2 = args[i]
            i += 1

    if search_dir is None or csv_filename is None or column_name1 is None or column_name2 is None:
        print("사용법: python %s.py <검색대상_디렉토리> <CSV파일명> <칼럼명1> <칼럼명2> [--conf mysql.conf 경로]" % PROGRAM_NAME)
        sys.exit(1)

    search_dir = os.path.abspath(search_dir)
    if not os.path.isdir(search_dir):
        print("[오류] 유효한 검색 디렉토리가 아닙니다: %s" % search_dir)
        sys.exit(1)

    return search_dir, csv_filename, column_name1, column_name2, conf_path

# ============================================================
# MAIN
# ============================================================
def main():
    search_dir, csv_filename, column_name1, column_name2, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다. pymysql 또는 mysql-connector-python을 설치하십시오.")
        sys.exit(1)

    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    table_name = build_dynamic_table_name(search_dir)

    print("=" * 60)
    print(" [소스 키워드 탐색 시작]")
    print("=" * 60)
    print("  검색 대상 디렉토리 : %s" % search_dir)
    print("  CSV 파일명         : %s" % csv_filename)
    print("  검색 기준 칼럼명1  : %s" % column_name1)
    print("  추가 등록 칼럼명2  : %s" % column_name2)
    print("  적재할 DB 테이블   : %s.%s" % (mysql_conf.get('database', ''), table_name))
    print("  처리일시 (op_dtm)  : %s" % op_dtm)
    print("-" * 60)

    if not os.path.isdir(OUT_DIR):
        print("[ERROR] 'out' 디렉토리가 존재하지 않습니다: %s" % OUT_DIR)
        print("        먼저 CSV 파일들을 생성하십시오.")
        sys.exit(1)

    csv_path = os.path.join(OUT_DIR, csv_filename)
    if not os.path.isfile(csv_path):
        print("[ERROR] 지정한 CSV 파일이 존재하지 않습니다: %s" % csv_path)
        sys.exit(1)

    print("[INFO] CSV 단어 리스트 추출 중...")

    search_map = {}
    try:
        with codecs.open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines and lines[0].startswith(u'\ufeff'):
                lines[0] = lines[0][1:]
            
            # Python 2.7 / 3.x CSV DictReader 호환성 처리
            if sys.version_info[0] < 3:
                import StringIO
                byte_content = "".join([l.encode('utf-8') if isinstance(l, unicode) else l for l in lines])
                f_csv = StringIO.StringIO(byte_content)
            else:
                import io
                str_content = "".join(lines)
                f_csv = io.StringIO(str_content)
                
            reader = csv.DictReader(f_csv)
            count_in_file = 0
            
            for row in reader:
                val1 = None
                val2 = None
                
                for k, v in row.items():
                    k_str = k.decode('utf-8') if isinstance(k, bytes) else k
                    v_str = v.decode('utf-8') if isinstance(v, bytes) else v
                    
                    if k_str == column_name1:
                        val1 = v_str
                    elif k_str == column_name2:
                        val2 = v_str

                if val1:
                    val1_clean = val1.strip()
                    if val1_clean:
                        val2_clean = val2.strip() if val2 else ""
                        search_map[val1_clean] = val2_clean
                        count_in_file += 1
                        
        print("  - %s: '%s' 컬럼에서 %d개 단어 추출 완료" % (csv_filename, column_name1, count_in_file))
    except Exception as e:
        print("  - [WARN] %s 파일 읽기 실패: %s" % (csv_filename, str(e)))

    if not search_map:
        print("[ERROR] CSV 파일 내에서 '%s' 컬럼 값을 찾지 못했거나 값이 모두 비어 있습니다." % column_name1)
        sys.exit(1)

    print("[INFO] 메모리에 저장된 검색 단어 개수: %d 개" % len(search_map))
    print("-" * 60)

    print("[INFO] 소스 파일 스캔 및 매칭 시작...")
    match_buffer         = []
    total_files_scanned  = 0
    total_lines_scanned  = 0
    total_lines_skipped  = 0

    # 단어별 정규표현식 미리 컴파일 (완전 일치 \b단어\b)
    compiled_patterns = {}
    for w in search_map.keys():
        escaped_word = re.escape(w.lower())
        pattern = r'\b%s\b' % escaped_word
        try:
            compiled_patterns[w] = re.compile(pattern)
        except Exception:
            pass

    for root, _, files in os.walk(search_dir):
        for file_name in sorted(files):
            file_lower = file_name.lower()
            if not any(file_lower.endswith(ext) for ext in TARGET_EXTENSIONS):
                continue

            full_path = os.path.join(root, file_name)
            base_dir  = os.path.abspath(root)
            total_files_scanned += 1
            
            _, file_ext = os.path.splitext(file_name)

            try:
                with codecs.open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, raw_line in enumerate(f, 1):
                        total_lines_scanned += 1
                        line_content = raw_line.strip()
                        if not line_content:
                            continue

                        line_without_comments = remove_comments_from_line(line_content, file_ext)
                        if not line_without_comments:
                            total_lines_skipped += 1
                            continue

                        lower_line = line_without_comments.lower()
                        for orig_word, rx in compiled_patterns.items():
                            if rx.search(lower_line):
                                col2_val = search_map[orig_word]
                                match_buffer.append({
                                    "base_directory": base_dir,
                                    "file_name":      file_name,
                                    "dir_file":       full_path,
                                    "line_no":        line_no,
                                    "line_content":   line_without_comments,
                                    "search_column1": column_name1,
                                    "search_column2": column_name2,
                                    "matched_word1":  orig_word,
                                    "matched_word2":  col2_val,
                                })
            except Exception as e:
                print("  - [WARN] 소스 파일 읽기 실패: %s (%s)" % (full_path, str(e)))

    print("[INFO] 소스 탐색 완료:")
    print("  - 스캔한 파일 개수  : %d 개" % total_files_scanned)
    print("  - 스캔한 총 라인 수 : %d 줄" % total_lines_scanned)
    print("  - 스킵된 주석 라인  : %d 줄" % total_lines_skipped)
    print("  - 매칭 발견 건수    : %d 건" % len(match_buffer))
    print("-" * 60)

    if not match_buffer:
        print("[WARN] 소스 내에 매칭된 단어가 없어 DB 저장을 생략합니다.")
        sys.exit(0)

    print("[INFO] MySQL 테이블에 매칭 데이터 적재 시작...")

    try:
        inserted_cnt = db_insert_matches(match_buffer, run_id, op_dtm, mysql_conf, search_dir)
    except Exception as e:
        print("=" * 60)
        print(" 소스 키워드 탐색 적재 실패")
        print("=" * 60)
        print("  DB 오류 내용       : %s" % str(e))
        sys.exit(1)

    print("=" * 60)
    print(" 소스 키워드 탐색 성공 완료")
    print("=" * 60)
    print("  적재 테이블        : %s.%s" % (mysql_conf.get('database', ''), table_name))
    print("  성공 적재 건수     : %d 건" % inserted_cnt)
    print("  run_id (실행 ID)   : %s" % run_id)
    print("=" * 60)

if __name__ == "__main__":
    main()
