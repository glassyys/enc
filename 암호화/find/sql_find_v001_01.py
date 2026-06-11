#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_find_v001_01.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001_01 (2026-06-10)
#   1) CSV파일 읽기 위치 변경: out 디렉토리 → in 디렉토리로 변경
#   2) 검색할 칼럼리스트를 파일 읽은 후 실행시 검색 단어 목록 번호와 함께 표시
#   3) CSV파일명 출력시 경로 포함 (스크립트 디렉토리 + 파일명)
#   4) DB 테이블 적재 전 결과를 별도 CSV 파일로 저장
#      - 파일명: {테이블명}.csv (DB 스키마 제외)
#      - 저장 위치: 스크립트 실행 디렉토리
#      - 저장 데이터: 매칭 결과 전체
#   5) 파일명 변경: sql_find_v001.py → sql_find_v001_01.py
#
# v001 (기존)
#   - out 디렉토리에서 CSV 파일 읽음
#   - 검색 단어 개수만 표시
#   - CSV 파일명만 출력
#   - DB 직접 적재
# 
# 실행예시:
#   python3 sql_find_v001_01.py <검색대상_디렉토리> <CSV파일명> <검색할_칼럼명> [--conf mysql.conf 경로]
#
# 예시:
#   python3 sql_find_v001_01.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB target_tables.csv target_table
#   python3 sql_find_v001_01.py /NAS/MIDP/DBMSVC/MIDP/TMT key_list_001.csv key_list key_list_001
#
# ■ 프로그램 설명
# ─────────────────────────────────────────────────────────────
# find 소스 (sql_find_v001_01.py)
# 1) 실행시 검색대상 디렉토리, CSV 파일명, 칼럼명을 파라미터로 전달
# 2) 소스하위 'in' 디렉토리에서 지정된 CSV 파일을 읽기 [v001_01 변경]
# 3) CSV 첫번째 행을 칼럼명으로 인식하고, 지정된 칼럼의 데이터를 단어 리스트로 메모리 저장
# 4) 실행시 지정된 디렉토리 하위의 모든 소스 파일 (.sql, .hql, .uld, .ld, .sh) 스캔
# 5) 저장된 단어 기준으로 소스 라인과 매칭하여 결과 수집
# 6) 매칭 결과를 임시 CSV 파일로 저장 (테이블명.csv) [v001_01 추가]
# 7) 매칭 결과를 MySQL 테이블에 등록 (동적 테이블명 생성)
# 8) 테이블명 규칙: {프로그램명}_{마지막디렉토리명}
# ===============================================================

import os
import sys
import csv
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 / 디렉토리 경로 설정
# [변경: OUT_DIR -> IN_DIR]
# ============================================================
PROGRAM_NAME    = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR      = os.path.dirname(os.path.abspath(sys.argv[0]))
IN_DIR          = os.path.join(SCRIPT_DIR, "in")  # [변경: out -> in]
MYSQL_CONF_FILE = "mysql.conf"

# 대상 확장자 규칙 (기존 소스 기준)
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}

# ============================================================
# MySQL 드라이버 동적 로드  ※ sql_unload_v001.py 와 동일한 방식
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
# mysql.conf 로드  ※ sql_unload_v001.py 와 동일한 방식
# ============================================================
def load_mysql_conf(explicit_path=None) -> tuple:
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), MYSQL_CONF_FILE)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        fallback_path = os.path.join(SCRIPT_DIR, MYSQL_CONF_FILE)
        if os.path.isfile(fallback_path):
            path = fallback_path
        else:
            return None, f"mysql.conf 파일을 찾을 수 없습니다: {path}"

    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except Exception as e:
        return None, f"mysql.conf 읽기 오류: {e}"

    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."

    conf    = dict(cp["mysql"])
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, f"mysql.conf 필수 항목 누락: {', '.join(missing)}"
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
  `search_column`  VARCHAR(200)  NOT NULL  COMMENT '검색 기준 칼럼명',
  `matched_word`   VARCHAR(500)  NOT NULL  COMMENT '매치된 단어',
  `op_dtm`         DATETIME      NOT NULL  COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id` (`run_id`),
  KEY `idx_file`   (`file_name`(191)),
  KEY `idx_word`   (`matched_word`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 키워드 매칭 정보';
"""

_SQL_INSERT = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file,
   line_no, line_content, search_column, matched_word, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# ============================================================
# 라인에서 주석 제거 함수
# ============================================================
def remove_comments_from_line(line: str, file_ext: str) -> str:
    """
    파일 타입별로 주석을 제거합니다.
    - SQL 계열 (.sql, .hql, .uld, .ld): "--" 기준으로 주석 제거
    - Shell (.sh): "#" 기준으로 주석 제거
    """
    if not line:
        return line
    
    file_ext_lower = file_ext.lower()
    
    # SQL 계열 파일: "--" 주석 제거
    if file_ext_lower in {".sql", ".hql", ".uld", ".ld"}:
        comment_pos = line.find("--")
        if comment_pos != -1:
            line = line[:comment_pos]
    
    # Shell 파일: "#" 주석 제거 (문자열 내부의 "#"는 제외하기 위해 간단히 처리)
    elif file_ext_lower == ".sh":
        comment_pos = line.find("#")
        if comment_pos != -1:
            line = line[:comment_pos]
    
    return line.strip()

# ============================================================
# 동적 테이블명 생성 함수 (기존 규칙 기준)
# ============================================================
def build_dynamic_table_name(source_dir: str) -> str:
    last_dir = os.path.basename(os.path.normpath(source_dir))
    return f"{PROGRAM_NAME}_{last_dir}"

# ============================================================
# CSV 파일로 결과 저장 함수 [추가: 2026-06-10]
# ============================================================
def save_results_to_csv(rows_buffer: list, table_name: str, script_dir: str) -> str:
    """
    DB 적재 전 검색 결과를 CSV 파일로 저장
    파일명: {테이블명}.csv (스키마 제외)
    """
    csv_output_path = os.path.join(script_dir, f"{table_name}.csv")
    
    try:
        with open(csv_output_path, "w", encoding="utf-8", newline="") as f:
            if not rows_buffer:
                # 빈 버퍼일 경우 헤더만 저장
                writer = csv.DictWriter(f, fieldnames=[
                    "base_directory", "file_name", "dir_file",
                    "line_no", "line_content", "search_column", "matched_word"
                ])
                writer.writeheader()
            else:
                # 결과 데이터 저장
                fieldnames = rows_buffer[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows_buffer)
        
        return csv_output_path
    except Exception as e:
        raise Exception(f"CSV 파일 저장 실패 ({csv_output_path}): {e}")

# ============================================================
# DB 적재 (CREATE IF NOT EXISTS → BATCH INSERT)
# ============================================================
def db_insert_matches(rows_buffer: list, run_id: str, op_dtm: str,
                      mysql_conf: dict, source_dir: str) -> int:
    table_name = build_dynamic_table_name(source_dir)
    conn   = None
    cursor = None
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        # 기존 테이블 DROP
        cursor.execute(_DDL_DROP.format(table=table_name))
        conn.commit()

        # 새로운 테이블 CREATE
        cursor.execute(_DDL_CREATE.format(table=table_name))
        conn.commit()

        batch = [
            (
                run_id,
                r["base_directory"], r["file_name"], r["dir_file"],
                r["line_no"],        r["line_content"],
                r["search_column"],  r["matched_word"],
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
def parse_args() -> tuple:
    args = sys.argv[1:]
    search_dir   = None
    csv_filename = None
    column_name  = None
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
            elif column_name is None:
                column_name = args[i]
            i += 1

    if search_dir is None or csv_filename is None or column_name is None:
        print(f"사용법: python3 {PROGRAM_NAME}.py <검색대상_디렉토리> <CSV파일명> <검색할_칼럼명> [--conf mysql.conf 경로]")
        sys.exit(1)

    search_dir = os.path.abspath(search_dir)
    if not os.path.isdir(search_dir):
        print(f"[오류] 유효한 검색 디렉토리가 아닙니다: {search_dir}")
        sys.exit(1)

    return search_dir, csv_filename, column_name, conf_path

# ============================================================
# MAIN
# ============================================================
def main():
    search_dir, csv_filename, column_name, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # DB 드라이버 검사
    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다. pymysql 또는 mysql-connector-python을 설치하십시오.")
        sys.exit(1)

    # DB 설정 파일 로드
    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print(f"[ERROR] {err}")
        sys.exit(1)

    table_name = build_dynamic_table_name(search_dir)

    print("=" * 60)
    print(" [소스 키워드 탐색 시작]")
    print("=" * 60)
    print(f"  검색 대상 디렉토리 : {search_dir}")
    print(f"  CSV 파일경로       : {os.path.join(IN_DIR, csv_filename)}")  # [변경: 경로포함 출력]
    print(f"  검색 기준 칼럼명   : {column_name}")
    print(f"  적재할 DB 테이블   : {mysql_conf.get('database', '')}.{table_name}")
    print(f"  처리일시 (op_dtm)  : {op_dtm}")
    print("-" * 60)

    # 1. in 디렉토리 하위 특정 .csv 파일을 읽어 단어 리스트 추출 [변경: out -> in]
    if not os.path.isdir(IN_DIR):
        print(f"[ERROR] 'in' 디렉토리가 존재하지 않습니다: {IN_DIR}")  # [변경: out -> in]
        print("        먼저 소스하위 in 디렉토리에 CSV 파일들을 배치하십시오.")  # [변경]
        sys.exit(1)

    csv_path = os.path.join(IN_DIR, csv_filename)  # [변경: OUT_DIR -> IN_DIR]
    if not os.path.isfile(csv_path):
        print(f"[ERROR] 지정한 CSV 파일이 존재하지 않습니다: {csv_path}")
        sys.exit(1)

    print("[INFO] CSV 단어 리스트 추출 중...")

    search_words = set()
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            count_in_file = 0
            for row in reader:
                val = row.get(column_name)
                if val:
                    val_clean = val.strip()
                    if val_clean:
                        search_words.add(val_clean)
                        count_in_file += 1
        print(f"  - {csv_path}: '{column_name}' 컬럼에서 {count_in_file:,}개 단어 추출 완료")  # [변경: 경로포함]
    except Exception as e:
        print(f"  - [WARN] {csv_filename} 파일 읽기 실패: {e}")

    if not search_words:
        print(f"[ERROR] CSV 파일 내에서 '{column_name}' 컬럼 값을 찾지 못했거나 값이 모두 비어 있습니다.")
        sys.exit(1)

    print(f"[INFO] 메모리에 저장된 검색 단어 개수: {len(search_words):,} 개")
    # [추가: 검색 단어 목록 표시]
    print("[INFO] 검색할 칼럼리스트:")
    for idx, word in enumerate(sorted(search_words), 1):
        print(f"       {idx:3d}. {word}")
    print("-" * 60)

    # 2. 지정된 디렉토리 하위 소스 파일 탐색 및 매칭
    print("[INFO] 소스 파일 스캔 및 매칭 시작...")
    match_buffer         = []
    total_files_scanned  = 0
    total_lines_scanned  = 0
    total_lines_skipped  = 0  # 주석 라인 스킵 카운트

    lower_words_map = {w.lower(): w for w in search_words}

    for root, _, files in os.walk(search_dir):
        for file in sorted(files):
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue

            full_path = os.path.join(root, file)
            base_dir  = os.path.abspath(root)
            total_files_scanned += 1
            
            # 파일 확장자 추출
            _, file_ext = os.path.splitext(file)

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, raw_line in enumerate(f, 1):
                        total_lines_scanned += 1
                        line_content = raw_line.strip()
                        if not line_content:
                            continue

                        # 주석 제거
                        line_without_comments = remove_comments_from_line(line_content, file_ext)
                        
                        # 주석 제거 후 라인이 비어있으면 스킵
                        if not line_without_comments:
                            total_lines_skipped += 1
                            continue

                        lower_line = line_without_comments.lower()
                        for lower_word, orig_word in lower_words_map.items():
                            if lower_word in lower_line:
                                match_buffer.append({
                                    "base_directory": base_dir,
                                    "file_name":      file,
                                    "dir_file":       full_path,
                                    "line_no":        line_no,
                                    "line_content":   line_without_comments,  # 주석 제거된 라인 저장
                                    "search_column":  column_name,
                                    "matched_word":   orig_word,
                                })
            except Exception as e:
                print(f"  - [WARN] 소스 파일 읽기 실패: {full_path} ({e})")

    print("[INFO] 소스 탐색 완료:")
    print(f"  - 스캔한 파일 개수  : {total_files_scanned:,} 개")
    print(f"  - 스캔한 총 라인 수 : {total_lines_scanned:,} 줄")
    print(f"  - 스킵된 주석 라인  : {total_lines_skipped:,} 줄")
    print(f"  - 매칭 발견 건수    : {len(match_buffer):,} 건")
    print("-" * 60)

    # [추가: DB 등록 전 결과를 CSV로 저장]
    if match_buffer:
        print("[INFO] 임시 결과를 CSV 파일로 저장 중...")
        try:
            csv_output_path = save_results_to_csv(match_buffer, table_name, SCRIPT_DIR)
            print(f"  - CSV 파일 저장 완료: {csv_output_path}")
            print(f"  - 저장된 레코드 수  : {len(match_buffer):,} 건")
        except Exception as e:
            print(f"  - [WARN] CSV 저장 실패: {e}")
    print("-" * 60)

    # 3. DB 적재 진행
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
        print(f"  DB 오류 내용       : {e}")
        sys.exit(1)

    print("=" * 60)
    print(" 소스 키워드 탐색 성공 완료")
    print("=" * 60)
    print(f"  적재 테이블        : {mysql_conf.get('database', '')}.{table_name}")
    print(f"  성공 적재 건수     : {inserted_cnt:,} 건")
    print(f"  run_id (실행 ID)   : {run_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
