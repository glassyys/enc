#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# sql_v12_gen_select_limit_query.py
#
# 개요:
#   이전에 작성한 sql_v12_full_new_05_col.py 와 동일한 방식
#   (mysql.conf 설정파일 + mysql-connector-python/pymysql 동적 로드)으로
#   MySQL 서버에 접속하여 테이블 목록을 조회한 뒤, 각 테이블에 대해
#       SELECT * FROM `db`.`tb` LIMIT 10;
#   형태의 조회쿼리를 자동 생성한다.
#
# 실행예시:
#   # mysql.conf 의 database 하나만 대상으로, LIMIT 10 (기본값)
#   python sql_v12_gen_select_limit_query.py
#
#   # 특정 DB(들)만 지정 (콤마로 여러 개 가능)
#   python sql_v12_gen_select_limit_query.py --database sidtest,midp_db
#
#   # 서버의 모든 사용자 DB(information_schema 등 시스템 DB 제외) 대상
#   python sql_v12_gen_select_limit_query.py --all-db
#
#   # 테이블명 LIKE 필터 + VIEW 포함 + LIMIT 개수 변경
#   python sql_v12_gen_select_limit_query.py --table-like "%_tb" --include-view --limit 20
#
#   # mysql.conf 경로 직접 지정 + 결과를 파일로 저장
#   python sql_v12_gen_select_limit_query.py --conf /home/p190872/chksrc/mysql.conf \
#       --out /home/p190872/chksrc/out/select_queries.sql
#
# [mysql.conf 파일 예시] (스크립트와 동일 디렉토리에 두면 --conf 생략 가능)
#   [mysql]
#   host     = localhost
#   port     = 3306
#   user     = root
#   password = secret
#   database = midp_db
#   charset  = utf8mb4
# ===============================================================

import os
import sys
import configparser
from datetime import datetime

# ============================================================
# MySQL 드라이버 동적 로드 (mysql-connector-python 우선, pymysql 폴백)
#   - sql_v12_full_new_05_col.py 와 동일한 방식
# ============================================================
_MYSQL_DRIVER = None


def _detect_mysql_driver():
    global _MYSQL_DRIVER
    try:
        import mysql.connector  # noqa: F401
        _MYSQL_DRIVER = "connector"
    except ImportError:
        try:
            import pymysql  # noqa: F401
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
        raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql 또는 pip install mysql-connector-python")


# ============================================================
# 설정
# ============================================================
PROGRAM_NAME    = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR      = os.path.dirname(os.path.abspath(sys.argv[0]))
OUT_DIR         = os.path.join(SCRIPT_DIR, "out")
MYSQL_CONF_FILE = "mysql.conf"

# 테이블 목록 조회 시 제외할 시스템 스키마 (--all-db 사용 시에만 적용)
SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}


# ============================================================
# mysql.conf 로드 (sql_v12_full_new_05_col.py 와 동일 포맷)
# ============================================================
def load_mysql_conf(explicit_path=None):
    path = explicit_path if explicit_path else os.path.join(SCRIPT_DIR, MYSQL_CONF_FILE)
    if not os.path.exists(path):
        return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path

    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding="utf-8")
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)

    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."

    conf    = dict(cp.items("mysql"))
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
    return conf, None


# ============================================================
# 인자 파싱 (원본 소스와 동일하게 argparse 미사용, 수동 파싱)
# ============================================================
def parse_args():
    args        = sys.argv[1:]
    conf_path   = None
    databases   = []       # --database 로 지정된 DB 목록
    all_db      = False    # --all-db
    table_like  = None     # --table-like 패턴
    include_vw  = False    # --include-view
    limit       = 10       # --limit
    out_path    = None     # --out

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--conf":
            if i + 1 >= len(args):
                print("오류: --conf 다음에 mysql.conf 경로를 지정하세요.")
                sys.exit(1)
            conf_path = args[i + 1]
            i += 2
        elif a == "--database":
            if i + 1 >= len(args):
                print("오류: --database 다음에 DB명을 지정하세요. (콤마로 여러 개 가능)")
                sys.exit(1)
            databases = [d.strip() for d in args[i + 1].split(",") if d.strip()]
            i += 2
        elif a == "--all-db":
            all_db = True
            i += 1
        elif a == "--table-like":
            if i + 1 >= len(args):
                print("오류: --table-like 다음에 LIKE 패턴을 지정하세요. (예: %%_tb)")
                sys.exit(1)
            table_like = args[i + 1]
            i += 2
        elif a == "--include-view":
            include_vw = True
            i += 1
        elif a == "--limit":
            if i + 1 >= len(args):
                print("오류: --limit 다음에 숫자를 지정하세요.")
                sys.exit(1)
            try:
                limit = int(args[i + 1])
            except ValueError:
                print("오류: --limit 값은 숫자여야 합니다.")
                sys.exit(1)
            i += 2
        elif a == "--out":
            if i + 1 >= len(args):
                print("오류: --out 다음에 저장할 파일 경로를 지정하세요.")
                sys.exit(1)
            out_path = args[i + 1]
            i += 2
        elif a in ("-h", "--help"):
            print("사용법: python %s [--conf mysql.conf경로] [--database db1,db2] "
                  "[--all-db] [--table-like 패턴] [--include-view] "
                  "[--limit N] [--out 저장경로]" % PROGRAM_NAME)
            sys.exit(0)
        else:
            print("알 수 없는 옵션: %s" % a)
            sys.exit(1)
        i = i

    return {
        "conf_path":  conf_path,
        "databases":  databases,
        "all_db":     all_db,
        "table_like": table_like,
        "include_vw": include_vw,
        "limit":      limit,
        "out_path":   out_path,
    }


# ============================================================
# 대상 DB 목록 결정
# ============================================================
def resolve_databases(cursor, conf, opts):
    if opts["databases"]:
        return opts["databases"]
    if opts["all_db"]:
        cursor.execute("SHOW DATABASES")
        rows = cursor.fetchall()
        result = []
        for row in rows:
            name = row[0]
            if name not in SYSTEM_SCHEMAS:
                result.append(name)
        return result
    # 옵션 미지정 시 mysql.conf 의 database 하나만 대상
    return [conf.get("database")]


# ============================================================
# 테이블(뷰 포함 옵션) 목록 조회
# ============================================================
def fetch_tables(cursor, database, table_like=None, include_view=False):
    table_types = "('BASE TABLE','VIEW')" if include_view else "('BASE TABLE')"
    sql = (
        "SELECT TABLE_NAME "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s "
        "AND TABLE_TYPE IN " + table_types
    )
    params = [database]
    if table_like:
        sql += " AND TABLE_NAME LIKE %s"
        params.append(table_like)
    sql += " ORDER BY TABLE_NAME"

    cursor.execute(sql, tuple(params))
    return [row[0] for row in cursor.fetchall()]


# ============================================================
# SELECT * FROM db.tb LIMIT n; 쿼리 생성
# ============================================================
def build_select_queries(database, tables, limit):
    queries = []
    for tbl in tables:
        queries.append("SELECT * FROM `%s`.`%s` LIMIT %d;" % (database, tbl, limit))
    return queries


# ============================================================
# main
# ============================================================
def main():
    opts = parse_args()

    conf, err = load_mysql_conf(opts["conf_path"])
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    try:
        conn = _mysql_connect(conf)
    except Exception as e:
        print("[ERROR] MySQL 접속 실패: %s" % str(e))
        sys.exit(1)

    cursor = conn.cursor()
    all_queries = []

    try:
        databases = resolve_databases(cursor, conf, opts)
        if not databases or not databases[0]:
            print("[ERROR] 대상 DB가 없습니다. --database 또는 --all-db 옵션을 확인하세요.")
            sys.exit(1)

        for db in databases:
            tables = fetch_tables(
                cursor, db,
                table_like=opts["table_like"],
                include_view=opts["include_vw"],
            )
            if not tables:
                print("-- [%s] 대상 테이블 없음" % db)
                continue

            queries = build_select_queries(db, tables, opts["limit"])
            print("-- ================================================")
            print("-- DB: %s  (테이블 %d건)" % (db, len(tables)))
            print("-- ================================================")
            for q in queries:
                print(q)
            print("")
            all_queries.extend(queries)

    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # 파일 저장 (--out 지정 시, 미지정 시 out/ 디렉토리에 타임스탬프로 자동 저장)
    out_path = opts["out_path"]
    if not out_path:
        if not os.path.exists(OUT_DIR):
            try:
                os.makedirs(OUT_DIR)
            except OSError:
                pass
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(OUT_DIR, "select_limit_queries_%s.sql" % ts)

    try:
        with open(out_path, "w") as f:
            for q in all_queries:
                f.write(q + "\n")
        print("[INFO] 조회쿼리 %d건을 파일로 저장했습니다: %s" % (len(all_queries), out_path))
    except Exception as e:
        print("[WARN] 파일 저장 실패: %s" % str(e))


if __name__ == "__main__":
    main()