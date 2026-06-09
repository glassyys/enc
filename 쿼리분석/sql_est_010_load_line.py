#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# 실행방법 예시:
# python3 sql_est_010_load_line.py /home/p190872/chksrc/SIDHUB
# python3 sql_est_010_load_line.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB
# python3 sql_est_010_load_line.py /NAS/MIDP/DBMSVC/MIDP/SID --conf /path/to/mysql.conf
#
# 설명:
# 1. 지정한 소스 디렉토리에서 쿼리를 추출하여 out/ 폴더에 .dat 파일로 생성합니다.
# 2. 생성된 .dat 파일을 읽어 MySQL 테이블에 즉시 적재(Load)합니다.
# (추가) 소스의 라인 넘버를 파일과 테이블에 함께 저장합니다.
# ===============================================================

import os
import re
import sys
import glob
import codecs
from datetime import datetime

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

# ============================================================
# 프로그램명 / 경로 설정
# ============================================================
PROGRAM_NAME    = os.path.splitext(os.path.basename(sys.argv[0]))[0]
SCRIPT_DIR      = os.path.dirname(os.path.abspath(sys.argv[0]))
OUT_DIR         = os.path.join(SCRIPT_DIR, "out")
MYSQL_CONF_FILE = "mysql.conf"
DELIMITER       = "^"
TARGET_EXTENSIONS = ('.sh', '.hql', '.sql', '.uld', '.ld')

EXCLUDE_PATTERNS = [
    "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)"
]

ONLY_FROM_DUAL_PATTERN = re.compile(
    r'^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$',
    re.IGNORECASE | re.DOTALL
)

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
  `crud_type`      VARCHAR(1)    NULL      COMMENT 'C/R/U/D',
  `line_number`    INT           NULL      COMMENT '소스 라인 넘버',
  `query_line`     LONGTEXT      NULL      COMMENT '쿼리 라인 텍스트',
  `op_dtm`         DATETIME      NOT NULL  COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id` (`run_id`),
  KEY `idx_file`   (`file_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL 추출 쿼리 정보';
"""

_SQL_INSERT = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file, crud_type, line_number, query_line, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s)
"""

# ============================================================
# 동적 테이블명 생성 함수
# ============================================================
def build_dynamic_table_name(dat_filename):
    base_name = os.path.basename(dat_filename)
    name_without_ext = os.path.splitext(base_name)[0]
    
    parts = name_without_ext.split('_')
    if len(parts) >= 5:
        dir_part = parts[-3]
        return "%s_%s" % (PROGRAM_NAME, dir_part)
    elif len(parts) >= 2:
        return "%s_%s" % (PROGRAM_NAME, parts[1])
    else:
        return "%s_load" % PROGRAM_NAME

# ============================================================
# 전처리 및 쿼리 추출 로직 (sql_est_010.py)
# ============================================================
def preprocess(content):
    content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith("#")
    )

    content = "\n".join(
        line for line in content.splitlines()
        if not re.match(r'(?i)^\s*DBMS_OUTPUT', line)
    )

    content = "\n".join(
        line for line in content.splitlines()
        if not (line.strip().startswith("/*") and line.strip().endswith("*/"))
    )

    pattern = re.compile(
        r"""
        ('([^']|'')*') |
        ("([^"]|"")*") |
        (--[^\n]*$) |
        (/\*.*?\*/)
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )

    def replacer(match):
        if match.group(1) or match.group(3):
            return match.group(0)
        return ""

    return pattern.sub(replacer, content)


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

END_IF_PATTERN = re.compile(r'^\s*END\s+IF\b', re.IGNORECASE)

def extract_queries_from_file(file_path):
    queries = []
    try:
        with codecs.open(file_path, 'r', 'utf-8', 'ignore') as f:
            orig_content = f.read()
            
        orig_lines = orig_content.splitlines()
        content = preprocess(orig_content)

        pos = 0
        length = len(content)
        last_orig_idx = 0

        while pos < length:
            match = MAIN_QUERY_START.search(content, pos)
            if not match:
                break

            start = match.start()
            keyword = match.group(1).upper()

            end = start
            in_string = False
            quote_char = None

            while end < length:
                ch = content[end]

                if ch in ("'", '"'):
                    if not in_string:
                        in_string = True
                        quote_char = ch
                    elif quote_char == ch:
                        in_string = False

                if ch == ";" and not in_string:
                    end += 1
                    break

                end += 1

            query = content[start:end].strip()

            if query:
                lower_query = query.lower()

                exclude = False
                for p in EXCLUDE_PATTERNS:
                    if p.lower() in lower_query:
                        exclude = True
                        break
                
                if exclude:
                    pos = end
                    continue

                if ONLY_FROM_DUAL_PATTERN.match(query.strip()):
                    pos = end
                    continue

                # 라인 넘버 찾기 (원본 파일 기준)
                start_line_num = 1
                first_query_line = query.splitlines()[0].strip()
                if first_query_line:
                    for idx in range(last_orig_idx, len(orig_lines)):
                        if first_query_line in orig_lines[idx]:
                            start_line_num = idx + 1
                            last_orig_idx = idx + 1
                            break

                queries.append((query, start_line_num))

            pos = end

    except Exception as e:
        print("[ERROR] 파일 읽기 실패: %s (%s)" % (file_path, str(e)))

    return queries


def classify_query(query):
    q = query.strip().upper()

    if q.startswith(("CREATE", "INSERT", "MERGE", "UPSERT", "EXECUTE")):
        return "C"
    elif q.startswith("SELECT") or q.startswith("WITH"):
        return "R"
    elif q.startswith("UPDATE"):
        return "U"
    elif q.startswith("DELETE"):
        return "D"
    elif q.startswith(("ALTER", "REPLACE", "DROP", "TRUNCATE")):
        return "U"
    else:
        return "R"

# ============================================================
# DB 적재 (CREATE IF NOT EXISTS → BATCH INSERT)
# ============================================================
def db_insert_matches(dat_file_path, run_id, op_dtm, mysql_conf):
    table_name = build_dynamic_table_name(dat_file_path)
    conn   = None
    cursor = None
    inserted_cnt = 0
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        cursor.execute(_DDL_DROP.format(table=table_name))
        conn.commit()

        cursor.execute(_DDL_CREATE.format(table=table_name))
        conn.commit()

        batch = []
        batch_size = 10000

        with codecs.open(dat_file_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip('\r\n')
                if not line:
                    continue
                
                parts = line.split(DELIMITER)
                if len(parts) >= 6:
                    crud_type      = parts[0]
                    base_directory = parts[1]
                    file_name      = parts[2]
                    dir_file       = parts[3]
                    line_number    = parts[4]
                    query_line     = DELIMITER.join(parts[5:])
                elif len(parts) >= 5:
                    crud_type      = parts[0]
                    base_directory = parts[1]
                    file_name      = parts[2]
                    dir_file       = parts[3]
                    line_number    = 0
                    query_line     = DELIMITER.join(parts[4:])
                else:
                    continue
                
                batch.append((
                    run_id,
                    base_directory, file_name, dir_file,
                    crud_type, line_number, query_line, op_dtm
                ))

                if len(batch) >= batch_size:
                    cursor.executemany(_SQL_INSERT.format(table=table_name), batch)
                    conn.commit()
                    inserted_cnt += len(batch)
                    batch = []

        if batch:
            cursor.executemany(_SQL_INSERT.format(table=table_name), batch)
            conn.commit()
            inserted_cnt += len(batch)

        return inserted_cnt, table_name

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
    source_dir = None
    conf_path  = None

    i = 0
    while i < len(args):
        if args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]
                i += 2
            else:
                print("[오류] --conf 다음에는 mysql.conf 파일의 경로를 입력해 주십시오.")
                sys.exit(1)
        elif not args[i].startswith("--"):
            if source_dir is None:
                source_dir = args[i]
            else:
                print("[오류] 여러 개의 소스 디렉토리를 지정할 수 없습니다.")
                sys.exit(1)
            i += 1
        else:
            print("[오류] 알 수 없는 옵션: %s" % args[i])
            print("사용법: python %s <소스분석할 디렉토리경로> [--conf mysql.conf 경로]" % PROGRAM_NAME)
            sys.exit(1)

    if not source_dir:
        print("사용법: python %s.py <소스분석할 디렉토리경로> [--conf mysql.conf 경로]" % PROGRAM_NAME)
        sys.exit(1)

    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        print("오류: 유효한 디렉토리가 아닙니다: %s" % source_dir)
        sys.exit(1)

    return source_dir, conf_path

# ============================================================
# MAIN
# ============================================================
def main():
    source_dir, conf_path = parse_args()

    if _MYSQL_DRIVER is None:
        print("[ERROR] MySQL 드라이버가 없습니다. pymysql 또는 mysql-connector-python을 설치하십시오.")
        sys.exit(1)

    mysql_conf, err = load_mysql_conf(conf_path)
    if err:
        print("[ERROR] %s" % err)
        sys.exit(1)

    out_dir = os.path.join(os.getcwd(), "out")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    source_last_dir = os.path.basename(source_dir.rstrip(os.sep))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = "%s_%s_%s.dat" % (PROGRAM_NAME, source_last_dir, timestamp)
    output_path = os.path.join(out_dir, output_filename)

    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print(" [1단계: SQL 추출 시작]")
    print("=" * 60)
    print("  소스 디렉토리      : %s" % source_dir)
    print("  생성될 DAT 파일    : %s" % output_path)
    
    total_files = 0
    total_queries = 0
    total_output_rows = 0
    total_file_lines = 0

    with codecs.open(output_path, 'w', encoding='utf-8') as out_file:
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.lower().endswith(TARGET_EXTENSIONS):
                    total_files += 1
                    full_path = os.path.join(root, file)
                    abs_path = os.path.abspath(root)

                    try:
                        with codecs.open(full_path, 'r', 'utf-8', 'ignore') as f:
                            total_file_lines += sum(1 for _ in f)
                    except:
                        pass

                    queries = extract_queries_from_file(full_path)

                    for query_info in queries:
                        query = query_info[0]
                        start_line_num = query_info[1]
                        
                        total_queries += 1
                        crud_type = classify_query(query)

                        current_line = start_line_num
                        for line in query.splitlines():
                            if line.strip():
                                out_file.write(
                                    "%s%s%s%s%s%s%s%s%s%s%s\n" % (
                                        crud_type, DELIMITER,
                                        abs_path, DELIMITER,
                                        file, DELIMITER,
                                        full_path, DELIMITER,
                                        current_line, DELIMITER,
                                        line.rstrip()
                                    )
                                )
                                total_output_rows += 1
                            current_line += 1

    print("====================================")
    print(" SQL 추출 완료")
    print("====================================")
    print("DAT 파일 위치        : %s" % output_path)
    print("처리 파일 건수        : %d" % total_files)
    print("추출 쿼리 건수        : %d" % total_queries)
    print("생성 행 건수          : %d" % total_output_rows)
    print("전체 파일 총 행 건수  : %d" % total_file_lines)
    print("====================================")

    if total_output_rows == 0:
        print("[INFO] 추출된 데이터가 없어 DB 적재를 생략합니다.")
        sys.exit(0)

    print("=" * 60)
    print(" [2단계: SQL 쿼리 DB 적재 시작]")
    print("=" * 60)
    print("  DAT 대상 파일      : %s" % output_path)
    print("  처리일시 (op_dtm)  : %s" % op_dtm)
    print("  실행 ID (run_id)   : %s" % run_id)
    print("-" * 60)

    try:
        inserted_cnt, table_name = db_insert_matches(output_path, run_id, op_dtm, mysql_conf)
    except Exception as e:
        print("=" * 60)
        print(" SQL 쿼리 데이터 적재 실패")
        print("=" * 60)
        print("  DB 오류 내용       : %s" % str(e))
        sys.exit(1)

    print("=" * 60)
    print(" SQL 쿼리 데이터 적재 성공")
    print("=" * 60)
    print("  적재 테이블        : %s.%s" % (mysql_conf.get('database', ''), table_name))
    print("  성공 적재 건수     : %d 건" % inserted_cnt)
    print("=" * 60)

if __name__ == "__main__":
    main()