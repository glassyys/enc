#!/usr/bin/env python3
# ===============================================================
# sql_unload_v001.py
#
# 실행예시:
#   python3 sql_unload_v001.py <SQL파일명> [--conf mysql.conf 경로]
#
# 예시:
#   python3 sql_unload_v001.py query.sql
#   python3 sql_unload_v001.py query
#
# 설명:
#   1. 실행 소스의 하위 디렉토리 'sql' 폴더에서 지정된 .sql 파일을 로드합니다.
#   2. mysql.conf 설정 파일을 로드하여 DB에 연동합니다.
#   3. 해당 쿼리를 실행하여 조회하고, 첫 번째 행에 칼럼명을 포함해 CSV로 저장합니다.
#   4. CSV 파일은 하위 디렉토리 'out' 폴더에 저장됩니다.
# ===============================================================

import os
import sys
import csv
import re
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 / 디렉토리 경로 설정
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR   = os.path.dirname(os.path.abspath(sys.argv[0]))
SQL_DIR      = os.path.join(SCRIPT_DIR, "sql")
OUT_DIR      = os.path.join(SCRIPT_DIR, "out")
MYSQL_CONF_FILE = "mysql.conf"

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
        raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql 또는 mysql-connector-python을 설치하세요.")

# ============================================================
# mysql.conf 로드
# ============================================================
def load_mysql_conf(explicit_path=None) -> tuple:
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), MYSQL_CONF_FILE)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        # 실행 소스 위치의 mysql.conf 도 보조 탐색
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
# 인수 파싱
# ============================================================
def parse_args():
    args = sys.argv[1:]
    sql_filename = None
    conf_path = None

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
            if sql_filename is None:
                sql_filename = args[i]
            i += 1

    if sql_filename is None:
        print(f"사용법: python3 {PROGRAM_NAME}.py <SQL파일명> [--conf mysql.conf 경로]")
        sys.exit(1)

    # 확장자 .sql 보완
    if not sql_filename.lower().endswith(".sql"):
        sql_filename += ".sql"

    return sql_filename, conf_path

# ============================================================
# MAIN
# ============================================================
def main():
    sql_filename, conf_path = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # DB 드라이버 검사
    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다. pymysql 또는 mysql-connector-python을 설치하십시오.")
        sys.exit(1)

    # DB 설정 파일 로드
    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print(f"[ERROR] {err}")
        sys.exit(1)

    # SQL 파일 탐색
    sql_file_path = os.path.join(SQL_DIR, sql_filename)
    if not os.path.isfile(sql_file_path):
        print(f"[ERROR] SQL 파일을 찾을 수 없습니다: {sql_file_path}")
        sys.exit(1)

    print("=" * 60)
    print(f" [SQL Unload 시작] {sql_filename}")
    print("=" * 60)
    print(f"  SQL 파일 경로  : {sql_file_path}")
    print(f"  DB 호스트      : {mysql_conf.get('host')}:{mysql_conf.get('port', 3306)}")
    print(f"  데이터베이스   : {mysql_conf.get('database')}")
    print("-" * 60)

    # 1. SQL 쿼리 파일 읽기
    try:
        with open(sql_file_path, "r", encoding="utf-8", errors="ignore") as f:
            query = f.read().strip()
    except Exception as e:
        print(f"[ERROR] SQL 파일을 읽는 도중 오류가 발생했습니다: {e}")
        sys.exit(1)

    if not query:
        print("[ERROR] SQL 파일 내용이 비어 있습니다.")
        sys.exit(1)

    # 2. DB 연결 및 조회
    conn = None
    cursor = None
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()
        
        print("[INFO] 쿼리를 실행 중입니다...")
        cursor.execute(query)

        # 칼럼 헤더 추출 (cursor.description 활용)
        if cursor.description is None:
            print("[WARN] 실행한 쿼리 결과에 반환할 레코드가 없습니다. (조회 쿼리인지 확인하십시오)")
            conn.close()
            sys.exit(0)

        headers = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        print(f"[INFO] 조회 완료: 총 {len(rows):,} 건 추출됨")
        
    except Exception as e:
        print(f"[ERROR] DB 조회 중 오류가 발생했습니다:\n{e}")
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        sys.exit(1)

    # 3. CSV 파일로 생성 및 저장
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        
        # 출력 파일명 생성 규칙 (SQL 파일명 기준 + timestamp)
        base_name = os.path.splitext(sql_filename)[0]
        csv_file_name = f"{base_name}_unload_{timestamp}.csv"
        csv_file_path = os.path.join(OUT_DIR, csv_file_name)
        
        print(f"[INFO] CSV 파일 작성을 시작합니다: {csv_file_path}")
        
        with open(csv_file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            # 첫 번째 행에 칼럼명 표시
            writer.writerow(headers)
            # 데이터 행 작성
            writer.writerows(rows)
            
        print("=" * 60)
        print(f" SQL Unload 성공 완료")
        print("=" * 60)
        print(f"  출력 CSV 파일  : {csv_file_path}")
        print(f"  추출 행 건수   : {len(rows):,}")
        print(f"  처리일시       : {op_dtm}")
        print("=" * 60)

    except Exception as e:
        print(f"[ERROR] CSV 파일 저장 중 오류가 발생했습니다: {e}")
        sys.exit(1)
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

if __name__ == "__main__":
    main()
