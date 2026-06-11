#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_check_encrypt_v001.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001 (2026-06-11)
#   1) CSV 파일(tbl_name, column_name, tobe_enc_key, tobe_end_rsn)을 읽음
#   2) 검색 대상 디렉토리 하위의 .sql, .hql, .uld, .ld, .sh 파일 스캔
#   3) 각 파일의 query_text에서:
#      - source_table / target_table 과 tbl_name 비교 (일치 검사)
#      - query_text에서 column_name 단어 포함 여부 검사
#   4) 매칭 결과를 CSV로 저장 (라인번호 포함)
#   5) MySQL DB에 적재 (--db 옵션 사용 시)
#   6) 결과 파일: {CSV파일명}_encrypt_chk_{timestamp}.csv
#
# ■ 프로그램 설명
# ─────────────────────────────────────────────────────────────
# 암호화 대상 테이블/컬럼 정보와 실제 소스 코드를 비교하여
# 일치하는 테이블/컬럼 사용 라인을 추출합니다.
#
# ■ 실행예시
# ─────────────────────────────────────────────────────────────
# python3 sql_check_encrypt_v001.py <검색대상_디렉토리> <CSV파일_절대경로> [--db] [--conf 경로]
#
# 기본 실행 (CSV만 생성):
#   python3 sql_check_encrypt_v001.py D:\source D:\data\encrypt_tbl.csv
#
# DB 적재 포함 (Linux 환경):
#   python3 /home/p190872/chksrc/sql_check_encrypt_v001.py /NAS/MIDP/DBMSVC/MIDP/SID /home/data/encrypt_tbl.csv --db
#
# DB 적재 포함 (Windows 환경):
#   python3 sql_check_encrypt_v001.py /NAS/MIDP/DBMSVC/MIDP/SID D:\data\encrypt_tbl.csv --db
#
# mysql.conf 별도 지정:
#   python3 sql_check_encrypt_v001.py /NAS/MIDP/SRC D:\data\encrypt_tbl.csv --db --conf /etc/mysql.conf
#
# ■ CSV 입력 포맷 예시
# ─────────────────────────────────────────────────────────────
# tbl_name,column_name,tobe_enc_key,tobe_end_rsn
# USERS,USER_ID,key_001,암호화필요
# USERS,USER_NAME,key_002,개인정보
# ORDERS,ORDER_NO,key_003,주민번호사용
# CUSTOMERS,CUST_EMAIL,key_004,암호화대상
#
# ■ CSV 출력 컬럼
# ─────────────────────────────────────────────────────────────
# base_directory, file_name, file_path, line_no, line_content,
# tbl_name, column_name, tobe_enc_key, tobe_end_rsn
#
# ===============================================================

import os
import sys
import csv
import re
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 설정
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]

# 대상 확장자 규칙
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}

# MySQL 드라이버 동적 로드
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
    """MySQL 연결"""
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
        raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql")


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
    
    # Shell 파일: "#" 주석 제거
    elif file_ext_lower == ".sh":
        comment_pos = line.find("#")
        if comment_pos != -1:
            line = line[:comment_pos]
    
    return line.strip()


# ============================================================
# CSV 파일로 결과 저장 함수
# ============================================================
def save_results_to_csv(rows_buffer: list, csv_path: str, timestamp: str) -> str:
    """
    검색 결과를 CSV 파일로 저장
    파일명: {원본CSV파일명}_encrypt_chk_{timestamp}.csv
    경로: 원본 CSV 파일과 동일한 디렉토리
    """
    csv_dir = os.path.dirname(csv_path)
    csv_basename = os.path.basename(csv_path)
    csv_name_without_ext = os.path.splitext(csv_basename)[0]
    csv_output_path = os.path.join(
        csv_dir, 
        f"{csv_name_without_ext}_encrypt_chk_{timestamp}.csv"
    )
    
    try:
        with open(csv_output_path, "w", encoding="utf-8-sig", newline="") as f:
            fieldnames = [
                "base_directory", "file_name", "file_path", "line_no", "line_content",
                "tbl_name", "column_name", "tobe_enc_key", "tobe_end_rsn"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            if rows_buffer:
                writer.writerows(rows_buffer)
        
        return csv_output_path
    except Exception as e:
        raise Exception(f"CSV 파일 저장 실패 ({csv_output_path}): {e}")


# ============================================================
# MySQL DB 적재 함수
# ============================================================
def create_db_table_ddl(table_name: str) -> str:
    """테이블 생성 DDL"""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        base_directory  VARCHAR(500)  NOT NULL,
        file_name       VARCHAR(500)  NOT NULL,
        file_path       VARCHAR(1000) NOT NULL,
        line_no         INT           NOT NULL,
        line_content    TEXT          NOT NULL,
        tbl_name        VARCHAR(200)  NOT NULL,
        column_name     VARCHAR(200)  NOT NULL,
        tobe_enc_key    VARCHAR(200)  NULL,
        tobe_end_rsn    VARCHAR(500)  NULL,
        op_dtm          DATETIME      NOT NULL,
        UNIQUE KEY unique_loc (file_path, line_no, tbl_name, column_name)
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """
    return ddl


def db_insert_matches(match_buffer: list, table_name: str, 
                     op_dtm: str, mysql_conf: dict) -> int:
    """매칭 결과를 MySQL DB에 적재"""
    if not match_buffer:
        return 0
    
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        
        # 테이블 생성
        create_sql = create_db_table_ddl(table_name)
        cursor.execute(create_sql)
        
        # 기존 데이터 삭제
        truncate_sql = f"TRUNCATE TABLE {table_name}"
        cursor.execute(truncate_sql)
        
        # 데이터 삽입
        insert_sql = f"""
        INSERT INTO {table_name} 
        (base_directory, file_name, file_path, line_no, line_content,
         tbl_name, column_name, tobe_enc_key, tobe_end_rsn, op_dtm)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        rows = []
        for row in match_buffer:
            rows.append((
                row["base_directory"],
                row["file_name"],
                row["file_path"],
                row["line_no"],
                row["line_content"],
                row["tbl_name"],
                row["column_name"],
                row["tobe_enc_key"],
                row["tobe_end_rsn"],
                op_dtm
            ))
        
        cursor.executemany(insert_sql, rows)
        conn.commit()
        
        inserted_cnt = cursor.rowcount
        cursor.close()
        conn.close()
        
        return inserted_cnt
    except Exception as e:
        raise Exception(f"DB 적재 실패: {e}")


# ============================================================
# 인수 파싱
# ============================================================
def parse_args() -> tuple:
    """명령행 인수 파싱"""
    args = sys.argv[1:]
    search_dir  = None
    csv_path    = None
    use_db      = False
    mysql_conf_file = "mysql.conf"

    if len(args) < 2:
        print(f"사용법: python3 {PROGRAM_NAME}.py <검색대상_디렉토리> <CSV파일_절대경로> [--db] [--conf 경로]")
        print("")
        print("예시:")
        print(f"  python3 {PROGRAM_NAME}.py D:\\source D:\\data\\encrypt_tbl.csv")
        print(f"  python3 {PROGRAM_NAME}.py /NAS/MIDP/SRC D:\\data\\encrypt_tbl.csv --db")
        print(f"  python3 {PROGRAM_NAME}.py /NAS/MIDP/SRC D:\\data\\encrypt_tbl.csv --db --conf /etc/mysql.conf")
        sys.exit(1)

    search_dir = os.path.abspath(args[0])
    csv_path = os.path.abspath(args[1])
    
    # 옵션 파싱
    i = 2
    while i < len(args):
        if args[i] == "--db":
            use_db = True
        elif args[i] == "--conf" and i + 1 < len(args):
            mysql_conf_file = args[i + 1]
            i += 1
        i += 1

    # 유효성 검사
    if not os.path.isdir(search_dir):
        print(f"[오류] 유효한 검색 디렉토리가 아닙니다: {search_dir}")
        sys.exit(1)

    if not os.path.isfile(csv_path):
        print(f"[오류] 지정한 CSV 파일이 존재하지 않습니다: {csv_path}")
        sys.exit(1)

    return search_dir, csv_path, use_db, mysql_conf_file


# ============================================================
# MAIN
# ============================================================
def main():
    search_dir, csv_path, use_db, mysql_conf_file = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [암호화 테이블/컬럼 검사 시작]")
    print("=" * 70)
    print(f"  검색 대상 디렉토리 : {search_dir}")
    print(f"  CSV 파일경로       : {csv_path}")
    print(f"  DB 적재 옵션       : {'ON' if use_db else 'OFF'}")
    print(f"  처리일시 (op_dtm)  : {op_dtm}")
    print(f"  타임스탬프         : {timestamp}")
    print("-" * 70)

    # 1. CSV 파일을 읽어 암호화 테이블/컬럼 리스트 추출
    print("[INFO] CSV 파일에서 암호화 정보 추출 중...")

    encrypt_list = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            count_in_file = 0
            for row in reader:
                tbl_name = row.get("tbl_name", "").strip()
                column_name = row.get("column_name", "").strip()
                tobe_enc_key = row.get("tobe_enc_key", "").strip()
                tobe_end_rsn = row.get("tobe_end_rsn", "").strip()
                
                if tbl_name and column_name:
                    encrypt_list.append({
                        "tbl_name": tbl_name,
                        "column_name": column_name,
                        "tobe_enc_key": tobe_enc_key,
                        "tobe_end_rsn": tobe_end_rsn
                    })
                    count_in_file += 1
        print(f"  - {csv_path}: {count_in_file:,}개 테이블/컬럼 정보 추출 완료")
    except Exception as e:
        print(f"  - [ERROR] CSV 파일 읽기 실패: {e}")
        sys.exit(1)

    if not encrypt_list:
        print(f"[ERROR] CSV 파일에서 암호화 대상 정보를 찾지 못했습니다.")
        sys.exit(1)

    print(f"[INFO] 메모리에 저장된 암호화 대상: {len(encrypt_list):,}개")
    print("[INFO] 암호화 대상 리스트:")
    for idx, item in enumerate(sorted(encrypt_list, key=lambda x: (x['tbl_name'], x['column_name'])), 1):
        print(f"       {idx:3d}. {item['tbl_name']}.{item['column_name']} (Key: {item['tobe_enc_key']}, 사유: {item['tobe_end_rsn']})")
    print("-" * 70)

    # 2. 검색대상 디렉토리에서 파일 찾기 및 매칭
    print("[INFO] 소스 파일 스캔 및 매칭 시작...")
    match_buffer        = []
    total_files_scanned = 0
    total_lines_scanned = 0
    total_lines_skipped = 0
    total_matches       = 0

    # 빠른 검색을 위해 dict 구성
    tbl_column_map = {}
    for item in encrypt_list:
        key = (item["tbl_name"].upper(), item["column_name"].upper())
        tbl_column_map[key] = item

    for root, _, files in os.walk(search_dir):
        for file in sorted(files):
            # 파일 확장자 필터링
            _, file_ext = os.path.splitext(file)
            if file_ext.lower() not in TARGET_EXTENSIONS:
                continue

            full_path = os.path.join(root, file)
            base_dir = os.path.abspath(root)
            total_files_scanned += 1

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

                        # 테이블명/컬럼명 매칭
                        line_upper = line_without_comments.upper()
                        
                        for (tbl_upper, col_upper), encrypt_info in tbl_column_map.items():
                            # 테이블명과 컬럼명이 모두 라인에 포함되어 있는지 확인
                            if tbl_upper in line_upper and col_upper in line_upper:
                                total_matches += 1
                                match_buffer.append({
                                    "base_directory": base_dir,
                                    "file_name": file,
                                    "file_path": full_path,
                                    "line_no": line_no,
                                    "line_content": line_without_comments,
                                    "tbl_name": encrypt_info["tbl_name"],
                                    "column_name": encrypt_info["column_name"],
                                    "tobe_enc_key": encrypt_info["tobe_enc_key"],
                                    "tobe_end_rsn": encrypt_info["tobe_end_rsn"],
                                })

            except Exception as e:
                print(f"  - [WARN] 소스 파일 읽기 실패: {full_path} ({e})")

    print("[INFO] 소스 파일 스캔 완료:")
    print(f"  - 스캔한 파일 개수  : {total_files_scanned:,} 개")
    print(f"  - 스캔한 총 라인 수 : {total_lines_scanned:,} 줄")
    print(f"  - 스킵된 주석 라인  : {total_lines_skipped:,} 줄")
    print(f"  - 매칭 발견 건수    : {total_matches:,} 건")
    print("-" * 70)

    # 3. 결과를 CSV 파일로 저장
    print("[INFO] 검색 결과를 CSV 파일로 저장 중...")
    try:
        csv_output_path = save_results_to_csv(match_buffer, csv_path, timestamp)
        print(f"  - CSV 파일 저장 완료: {csv_output_path}")
        print(f"  - 저장된 레코드 수  : {len(match_buffer):,} 건")
    except Exception as e:
        print(f"  - [ERROR] CSV 저장 실패: {e}")
        sys.exit(1)

    print("-" * 70)

    # 4. DB 적재 (--db 옵션 사용 시)
    if use_db:
        print("[INFO] MySQL DB에 결과 적재 시작...")
        try:
            # mysql.conf 읽기
            if not os.path.isfile(mysql_conf_file):
                print(f"  - [ERROR] mysql.conf 파일을 찾을 수 없습니다: {mysql_conf_file}")
                sys.exit(1)
            
            conf = configparser.ConfigParser()
            conf.read(mysql_conf_file, encoding="utf-8")
            mysql_conf = dict(conf.items("mysql"))
            
            # 테이블명 생성
            last_dir = os.path.basename(os.path.normpath(search_dir))
            db_table = f"{mysql_conf.get('table_prefix', 'sql_chk')}_{last_dir}_encrypt"
            
            inserted_cnt = db_insert_matches(match_buffer, db_table, op_dtm, mysql_conf)
            print(f"  - DB 테이블 적재 완료: {db_table}")
            print(f"  - 적재된 레코드 수  : {inserted_cnt:,} 건")
        except Exception as e:
            print(f"  - [ERROR] DB 적재 실패: {e}")
            sys.exit(1)

    print("=" * 70)
    print(" 암호화 검사 작업 완료")
    print("=" * 70)
    print(f"  검색 결과 파일     : {csv_output_path}")
    print(f"  스캔한 파일 개수   : {total_files_scanned:,} 개")
    print(f"  발견된 매칭 건수   : {len(match_buffer):,} 건")
    print(f"  처리일시           : {op_dtm}")
    print("=" * 70)


if __name__ == "__main__":
    main()
