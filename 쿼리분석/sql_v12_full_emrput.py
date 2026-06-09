## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TMT --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TMT --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDIA --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDIA --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDM --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDM --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_v12_full_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID --mode DETAIL --db
## 
## 1~4번 내용대로 처리하여 수정한 파이썬 전체소스
## 
## 1. mysql DB연결
## "[mysql.conf 파일 예시]"처럼 mysql.conf 파일을 생성후
## 읽는데 table명은 선택옵션으로 사용하지 않고
## 
## "mysql.conf" 정보 기준으로 mysql DB연결하고 
## 
## [mysql.conf 파일생성 예시]
## [mysql]
## host     = localhost
## port     = 3306
## user     = root
## password = secret
## database = lineage_db
## table    = sql_lineage
## charset  = utf8mb4
## 
## 2. 파일명기준 테이블 생성
## database.csv파일명 기준으로 미존재시 
## "[테이블 스크립트 예시]" 처럼 생성후
## 
## [테이블 스크립트 예시]
## create table midp_project.csv파일명 (
## base_directory varchar(500) not null,
## file_name varchar(500) not null,
## dir_file varchar(1000) not null,
## sql_type varchar(50) not null,
## source_schema varchar(100) null,
## source_table varchar(500) null,
## target_schema varchar(100) null,
## target_table varchar(500) null
## )
## 
## 3. 파일생성내용기준 테이블 등록
## TRUNCATE 후 INSERT_INTO 처리하도록 소스 개선
## 
## 4. 출력문 보완
## 출력문을 파일생성시 조사한 파일수 결과 행수와
## DB적재정보도 출력하도록 수정
## 
## 추가로 파일생성은 실행디렉토리 하으 out 디렉토리에 생성하도록만 수정한 전체소스
## 테이블 칼럼 op_dtm 처리일시 추가한 기준으로 수정한 전체소스
## ■sql_tb_chk_v08_merge_db.py의 DB/CSV 인프라에 sql_lng_014_with.py의 고급 쿼리 파싱 엔진을 통합한 완성본입니다.
## 요청 내용을 확인했습니다. MAIN_QUERY_START 키워드 다음 ; 까지의 쿼리 텍스트를 저장하는 
## 추가 테이블(id, base_directory, file_name, dir_file, crud_type, sql_type, query_text, op_dtm)을 생성하고 등록하는 로직을 추가
## 1. _DDL_CREATE_QUERY_TEXT — 쿼리 텍스트 테이블 DDL
## 
##    id, base_directory, file_name, dir_file, crud_type, sql_type, query_text, op_dtm
## 
## 2. _SQL_INSERT_QUERY_TEXT — 쿼리 텍스트 테이블 INSERT 문
## 3. build_query_text_table_name() — 테이블명 생성 함수
## → 리니지 테이블명 뒤에 _query_text 를 붙여 구분
## (예: sql_tb_chk_v09_full_mydir_simple_query_text)
## 4. db_insert_query_text_all() — 쿼리 텍스트 테이블 DROP→CREATE→INSERT 함수
## 5. extract_queries_from_file() 반환값 변경
## 기존 (queries, total_lines) → (queries_with_raw, total_lines)
## 각 원소가 (preprocessed_query, raw_query) 튜플로 변경 (현재는 동일 값, 원본 주석 포함 버전이 필요하면 offset 매핑 추가 가능)
## 6. main() 내 query_text_buffer 수집 및 적재
## 모든 쿼리에 대해 crud_type, sql_type, query_text 를 버퍼에 쌓고, --db 옵션 시 리니지 테이블과 함께 쿼리 텍스트 테이블도 DROP→재생성→적재
## 
## sql_v11_full_emrput.py 추가요건
## "[추가] EMRPUT 라인 추출 함수" 에  EMRPUTF 인 경우도 추출할 수 있도록 수정한 소스요청
## sql_v12_full_emrput.py 추가요건
## 1. EMRPUT/EMRPUTF 라인 추출 - 기존 기능 유지
## 2. default 포함 라인 추출 → 동일 양식 CSV 파일 생성 (오타 키워드 그대로)
## 3. key_mst 포함 라인 추출 → 동일 양식 CSV 파일 생성
## 
## ① extract_keyword_lines() 범용 함수 추가
## default, key_mst 등 임의의 키워드를 추출하는 공통 함수입니다. case_sensitive 파라미터로 대소문자 구분 여부를 제어하며, 기본값은 False(대소문자 무시)입니다.
## ② 파일 루프 내 3개 키워드 동시 수집
## pythonextract_emrput_lines(full_path)          # EMRPUTF / EMRPUT
## extract_keyword_lines(full_path, "default")  # default
## extract_keyword_lines(full_path, "key_mst")  # key_mst
## ③ save_keyword_csv() 헬퍼 함수 추가
## suffix(파일명 식별자)와 header를 인자로 받아 3개 CSV를 동일한 방식으로 저장합니다.
## ④ 생성되는 CSV 파일 3개
## # 파일명 패턴 컬럼
## 1*_emrput_*.csvbase_directory, file_name, dir_file, emrput_type, emrput_line
## 2*_default_*.csvbase_directory, file_name, dir_file, keyword, line
## 3*_key_mst_*.csvbase_directory, file_name, dir_file, keyword, line

#!/usr/bin/env python3
# ===============================================================
# sql_v12_full_emrput.py
#
# 실행예시:
#   python3 sql_v12_full_emrput.py <분석대상_디렉토리>
#          [--mode SIMPLE|DETAIL] [--db] [--conf 경로]
#
# 옵션:
#   --mode SIMPLE (기본값) : CTE 투명 처리, 물리소스->타겟만 출력
#   --mode DETAIL          : WITH절 CTE 흐름 포함 출력
#   --db                   : CSV 생성 + MySQL DB 등록 (mysql.conf 필요)
#   --conf 경로            : mysql.conf 파일 경로 지정
#
# 출력 컬럼 (CSV / DB):
#   base_directory, file_name, dir_file,
#   crud_type, sql_type,
#   source_table, source_type,
#   target_table, target_type,
#   depth,
#   src_schema, src_table,
#   tgt_schema, tgt_table,
#   op_dtm
#
# 추가 테이블 (query_text):
#   id, base_directory, file_name, dir_file,
#   crud_type, sql_type, query_text, op_dtm
#
# v12 변경사항:
#   - extract_keyword_lines(): EMRPUTF/EMRPUT/default/key_mst 범용 키워드 추출 함수로 통합
#   - 키워드별 CSV 3개 파일 생성:
#       (1) *_emrput_*.csv   : EMRPUTF 또는 EMRPUT 포함 라인
#                              컬럼: base_directory, file_name, dir_file, emrput_type, emrput_line
#       (2) *_default_*.csv  : default 포함 라인
#                              컬럼: base_directory, file_name, dir_file, keyword, line
#       (3) *_key_mst_*.csv  : key_mst 포함 라인
#                              컬럼: base_directory, file_name, dir_file, keyword, line
# ===============================================================

import os
import re
import sys
import csv
import configparser
from datetime import datetime

# ============================================================
# 프로그램명 / OUT_DIR
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
OUT_DIR      = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "out")

# ============================================================
# MySQL 드라이버 동적 로드 (mysql-connector-python 우선, pymysql 폴백)
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
        raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql")


# ============================================================
# 키워드 라인 추출 범용 함수
# ============================================================

def extract_emrput_lines(file_path: str) -> list:
    """
    파일에서 EMRPUTF 또는 EMRPUT 키워드가 포함된 라인을 추출한다.

    - EMRPUTF 가 EMRPUT 를 문자열로 포함하므로, EMRPUTF 여부를 먼저 확인한다.
    - 반환값: list of dict
        {
            "line":        str,   # 원본 라인(strip)
            "emrput_type": str,   # "EMRPUTF" | "EMRPUT"
        }
    """
    results = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f:
                line = raw_line.strip()
                if "EMRPUTF" in line:
                    results.append({"line": line, "emrput_type": "EMRPUTF"})
                elif "EMRPUT" in line:
                    results.append({"line": line, "emrput_type": "EMRPUT"})
    except Exception:
        pass
    return results


def extract_keyword_lines(file_path: str, keyword: str,
                          case_sensitive: bool = False) -> list:
    """
    파일에서 특정 keyword 가 포함된 라인을 추출하는 범용 함수.

    Parameters
    ----------
    file_path      : 검색 대상 파일 경로
    keyword        : 검색 키워드 (예: "default", "key_mst")
    case_sensitive : True 이면 대소문자 구분, False 이면 구분 없음 (기본 False)

    반환값: list of dict
        {
            "line":    str,   # 원본 라인(strip)
            "keyword": str,   # 실제 매칭에 사용된 keyword 원문
        }
    """
    results    = []
    search_kw  = keyword if case_sensitive else keyword.lower()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f:
                line        = raw_line.strip()
                search_line = line if case_sensitive else line.lower()
                if search_kw in search_line:
                    results.append({"line": line, "keyword": keyword})
    except Exception:
        pass
    return results


# ============================================================
# 키워드별 CSV 저장 헬퍼
# ============================================================

def save_keyword_csv(rows: list, suffix: str,
                     source_dir: str, op_dtm: str,
                     header: list) -> str:
    """
    키워드 추출 결과를 CSV 로 저장하고 파일 경로를 반환한다.

    Parameters
    ----------
    rows       : list of list  (각 행, header 순서와 일치)
    suffix     : 파일명 중간 식별자 (예: "emrput", "default", "key_mst")
    source_dir : 분석 대상 디렉토리 (파일명 생성에 사용)
    op_dtm     : 처리일시 문자열 (YYYY-MM-DD HH:MM:SS)
    header     : CSV 헤더 컬럼 리스트
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir  = os.path.basename(os.path.normpath(source_dir))
    timestamp = op_dtm.replace("-", "").replace(" ", "_").replace(":", "")
    csv_path  = os.path.join(
        OUT_DIR,
        f"{PROGRAM_NAME}_{last_dir}_{suffix}_{timestamp}.csv"
    )
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return csv_path


# ============================================================
# 설정
# ============================================================
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}
ENV_FILE          = "db_schema.env"
MYSQL_CONF_FILE   = "mysql.conf"

EXCLUDE_PATTERNS = [
    "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)",
    "sidtest.ad1901_rgb_ac190212_svc",
]

RESERVED_WORDS = {
    "SET","WHERE","AND","OR","ON","WHEN","THEN","ELSE",
    "VALUES","SELECT","UPDATE","INSERT","DELETE","MERGE",
    "USING","FROM","JOIN","INTO","GROUP","ORDER","BY",
    "HAVING","TABLE","OVERWRITE","POSITION","SUBSTRING",
    "CAST","TRIM","COUNT","SUM","MAX","MIN","AVG","SESSION"
}

# ============================================================
# 정규식
# ============================================================
SINGLE_LINE_COMMENT   = re.compile(r"--.*?$",            re.MULTILINE)
MULTI_LINE_COMMENT    = re.compile(r"/\*.*?\*/",          re.DOTALL)
ONLY_FROM_DUAL_PATTERN = re.compile(
    r"^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$",
    re.IGNORECASE | re.DOTALL
)
TEMP_CREATE_PAT = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY|TEMP)\s+(?:TABLE|VIEW)"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(;]+)",
    re.IGNORECASE
)
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
END_IF_PATTERN       = re.compile(r"^\s*END\s+IF\b",  re.IGNORECASE)
DECLARE_BEGIN_RE     = re.compile(r"^\s*(DECLARE|BEGIN)\b", re.IGNORECASE)
INNER_DML_RE         = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|REPLACE|ALTER)\b",
    re.IGNORECASE
)


# ============================================================
# 인수 파싱
# ============================================================
def parse_args():
    args      = sys.argv[1:]
    src_dir   = None
    mode      = "SIMPLE"
    use_db    = False
    conf_path = None
    i = 0
    while i < len(args):
        if args[i] == "--mode":
            if i + 1 < len(args):
                mode = args[i + 1].upper()
                if mode not in ("SIMPLE", "DETAIL"):
                    print("오류: --mode 값은 SIMPLE 또는 DETAIL 이어야 합니다.")
                    sys.exit(1)
                i += 2
            else:
                print("오류: --mode 다음에 SIMPLE 또는 DETAIL 을 지정하세요.")
                sys.exit(1)
        elif args[i] == "--db":
            use_db = True
            i += 1
        elif args[i] == "--conf":
            if i + 1 < len(args):
                conf_path = args[i + 1]
                i += 2
            else:
                print("오류: --conf 다음에 mysql.conf 경로를 지정하세요.")
                sys.exit(1)
        else:
            if src_dir is None:
                src_dir = args[i]
            i += 1

    if src_dir is None:
        print("사용법: python3 sql_v12_full_emrput.py 소스디렉토리 "
              "[--mode SIMPLE|DETAIL] [--db] [--conf 경로]")
        sys.exit(1)

    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        print(f"오류: 유효한 디렉토리가 아닙니다: {src_dir}")
        sys.exit(1)

    return src_dir, mode, use_db, conf_path


SOURCE_DIR, MODE, USE_DB, CONF_PATH = parse_args()


# ============================================================
# mysql.conf 로드
# ============================================================
def load_mysql_conf(explicit_path=None) -> tuple:
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), MYSQL_CONF_FILE)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
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
# db_schema.env 로드
# ============================================================
def load_schema_variables() -> dict:
    env_path   = os.path.join(os.getcwd(), ENV_FILE)
    schema_map = {}
    if not os.path.isfile(env_path):
        print(f"[WARN] db_schema.env 파일 없음: {env_path} → 변수 치환 생략")
        return schema_map
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^(\w+)=[\"']?([^\"']*)[\"']?$", line)
                if m:
                    schema_map[m.group(1)] = m.group(2).strip()
    except Exception as e:
        print(f"[WARN] db_schema.env 읽기 오류: {e}")
    return schema_map


SCHEMA_VARS = load_schema_variables()


# ============================================================
# schema 변수 치환 + schema/table 분리
# ============================================================
def resolve_and_split_schema_table(full_name: str) -> tuple:
    if not full_name:
        return "", ""

    def replace_var(match):
        var = match.group(1) or match.group(2)
        return SCHEMA_VARS.get(var, match.group(0))

    resolved = re.sub(r"\$\{(\w+)\}", replace_var, full_name)
    resolved = re.sub(r"\$(\w+)(?=\W|$)", replace_var, resolved)

    parts = resolved.split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", resolved.strip()


# ============================================================
# DDL / INSERT SQL  (기존 리니지 테이블)
# ============================================================
_DDL_CREATE = """
CREATE TABLE IF NOT EXISTS `{table}` (
  `id`           BIGINT        NOT NULL AUTO_INCREMENT,
  `run_id`       VARCHAR(30)   NOT NULL  COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `base_directory` VARCHAR(500) NOT NULL COMMENT '소스파일 디렉토리 경로',
  `file_name`    VARCHAR(500)  NOT NULL  COMMENT '파일명',
  `dir_file`     TEXT          NOT NULL  COMMENT '소스파일 전체경로',
  `crud_type`    VARCHAR(1)    NULL      COMMENT 'C/R/U/D',
  `sql_type`     VARCHAR(30)   NULL      COMMENT 'INSERT/SELECT/UPDATE/...',
  `source_table` VARCHAR(500)  NULL      COMMENT '소스 테이블 (원본명)',
  `source_type`  VARCHAR(10)   NULL      COMMENT 'TABLE/CTE/TEMP',
  `target_table` VARCHAR(500)  NULL      COMMENT '타겟 테이블 (원본명)',
  `target_type`  VARCHAR(10)   NULL      COMMENT 'TABLE/CTE/TEMP',
  `depth`        INT           NULL      COMMENT '데이터 흐름 단계',
  `src_schema`   VARCHAR(200)  NULL      COMMENT '소스 스키마명',
  `src_table`    VARCHAR(300)  NULL      COMMENT '소스 테이블명 (스키마 제외)',
  `tgt_schema`   VARCHAR(200)  NULL      COMMENT '타겟 스키마명',
  `tgt_table`    VARCHAR(300)  NULL      COMMENT '타겟 테이블명 (스키마 제외)',
  `op_dtm`       DATETIME      NOT NULL  COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_run_id`    (`run_id`),
  KEY `idx_file`      (`file_name`(191)),
  KEY `idx_src_table` (`src_table`(191)),
  KEY `idx_tgt_table` (`tgt_table`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='SQL 소스/타겟 리니지 정보';
"""

_SQL_INSERT = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file,
   crud_type, sql_type,
   source_table, source_type,
   target_table, target_type,
   depth,
   src_schema, src_table,
   tgt_schema, tgt_table,
   op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# ============================================================
# DDL / INSERT SQL  (추가: 쿼리 텍스트 테이블)
# ============================================================
_DDL_CREATE_QUERY_TEXT = """
CREATE TABLE IF NOT EXISTS `{table}` (
  `id`             BIGINT        NOT NULL AUTO_INCREMENT,
  `base_directory` VARCHAR(500)  NOT NULL COMMENT '소스파일 디렉토리 경로',
  `file_name`      VARCHAR(500)  NOT NULL COMMENT '파일명',
  `dir_file`       TEXT          NOT NULL COMMENT '소스파일 전체경로',
  `crud_type`      VARCHAR(1)    NULL     COMMENT 'C/R/U/D',
  `sql_type`       VARCHAR(30)   NULL     COMMENT 'INSERT/SELECT/UPDATE/...',
  `query_text`     LONGTEXT      NULL     COMMENT 'MAIN_QUERY_START ~ ; 까지의 원본 쿼리',
  `op_dtm`         DATETIME      NOT NULL COMMENT '처리일시',
  PRIMARY KEY (`id`),
  KEY `idx_file`      (`file_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='SQL 원본 쿼리 텍스트';
"""

_SQL_INSERT_QUERY_TEXT = """
INSERT INTO `{table}`
  (base_directory, file_name, dir_file,
   crud_type, sql_type, query_text, op_dtm)
VALUES
  (%s, %s, %s, %s, %s, %s, %s)
"""


# ============================================================
# 동적 테이블명 생성
# ============================================================
def build_dynamic_table_name(source_dir: str, mode: str) -> str:
    last_dir = os.path.basename(os.path.abspath(source_dir))
    return f"{PROGRAM_NAME}_{last_dir}_{mode.lower()}"


def build_query_text_table_name(source_dir: str, mode: str) -> str:
    base = build_dynamic_table_name(source_dir, mode)
    return f"{base}_query_text"


# ============================================================
# DB: DROP → CREATE → INSERT  (기존 리니지 테이블)
# ============================================================
def db_insert_all(rows_buffer: list, run_id: str, op_dtm: str,
                  mysql_conf: dict, source_dir: str, mode: str) -> tuple:
    table_name = build_dynamic_table_name(source_dir, mode)
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        conn.commit()

        cursor.execute(_DDL_CREATE.format(table=table_name))
        conn.commit()

        batch = []
        for r in rows_buffer:
            batch.append((
                run_id,
                r["base_directory"], r["file_name"], r["dir_file"],
                r["crud_type"],      r["sql_type"],
                r["source_table"],   r["source_type"],
                r["target_table"],   r["target_type"],
                r["depth"],
                r["src_schema"],     r["src_table"],
                r["tgt_schema"],     r["tgt_table"],
                op_dtm,
            ))

        if batch:
            cursor.executemany(_SQL_INSERT.format(table=table_name), batch)
            conn.commit()

        inserted = len(batch)
        cursor.close()
        conn.close()
        print(f"[INFO] MySQL 테이블 DROP→재생성→적재 완료: {table_name} ({inserted}건)")
        return inserted, None

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass
        return 0, str(e)


# ============================================================
# DB: DROP → CREATE → INSERT  (추가: 쿼리 텍스트 테이블)
# ============================================================
def db_insert_query_text_all(query_text_buffer: list, op_dtm: str,
                              mysql_conf: dict, source_dir: str, mode: str) -> tuple:
    table_name = build_query_text_table_name(source_dir, mode)
    try:
        conn   = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        conn.commit()

        cursor.execute(_DDL_CREATE_QUERY_TEXT.format(table=table_name))
        conn.commit()

        batch = []
        for r in query_text_buffer:
            batch.append((
                r["base_directory"],
                r["file_name"],
                r["dir_file"],
                r["crud_type"],
                r["sql_type"],
                r["query_text"],
                op_dtm,
            ))

        if batch:
            cursor.executemany(_SQL_INSERT_QUERY_TEXT.format(table=table_name), batch)
            conn.commit()

        inserted = len(batch)
        cursor.close()
        conn.close()
        print(f"[INFO] MySQL 쿼리텍스트 테이블 DROP→재생성→적재 완료: {table_name} ({inserted}건)")
        return inserted, None

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass
        return 0, str(e)


# ============================================================
# 전처리
# ============================================================
def preprocess(content: str) -> str:
    content = "\n".join(
        line for line in content.splitlines()
        if not line.lstrip().startswith("#")
    )
    content = "\n".join(
        line for line in content.splitlines()
        if not re.match(r"(?i)^\s*DBMS_OUTPUT", line)
    )
    content = "\n".join(
        line for line in content.splitlines()
        if not (line.strip().startswith("/*") and line.strip().endswith("*/"))
    )
    pattern = re.compile(
        r"""
        ('(?:[^']|'')*') |
        ("(?:[^"]|"")*") |
        (--[^\n]*$)       |
        (/\*.*?\*/)
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )
    def replacer(m):
        if m.group(1) or m.group(2):
            return m.group(0)
        return ""
    return pattern.sub(replacer, content)


# ============================================================
# EXECUTE IMMEDIATE 내부 SQL 추출
# ============================================================
def extract_execute_immediate(content: str) -> list:
    results = []
    pattern = re.compile(
        r"\bEXECUTE\s+IMMEDIATE\s+'(.*?)'",
        re.IGNORECASE | re.DOTALL
    )
    for m in pattern.finditer(content):
        inner = m.group(1).strip()
        if inner:
            results.append(inner)
    return results


# ============================================================
# depth 기반 쿼리 추출
# ============================================================
def extract_queries_from_file(file_path: str) -> tuple:
    queries_with_raw = []
    total_lines      = 0
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        total_lines = raw.count("\n") + 1
        content     = preprocess(raw)
        ei_queries  = extract_execute_immediate(content)

        masked = re.sub(
            r"\bEXECUTE\s+IMMEDIATE\s+'.*?'",
            "EXECUTE_IMMEDIATE_MASKED",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        pos    = 0
        length = len(masked)
        while pos < length:
            match = MAIN_QUERY_START.search(masked, pos)
            if not match:
                break
            keyword = match.group(1).upper()
            start   = match.start()

            if keyword.startswith("END"):
                line_start = masked.rfind("\n", 0, start) + 1
                line_end   = masked.find("\n", start)
                if line_end == -1:
                    line_end = length
                if END_IF_PATTERN.match(masked[line_start:line_end]):
                    pos = line_end
                    continue

            end      = start
            depth    = 0
            in_str   = False
            q_char   = None
            while end < length:
                ch = masked[end]
                if ch in ("'", '"'):
                    if not in_str:
                        in_str = True
                        q_char = ch
                    elif q_char == ch:
                        in_str = False
                elif not in_str:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth = max(depth - 1, 0)
                    elif ch == ";" and depth == 0:
                        end += 1
                        break
                end += 1

            query = masked[start:end].strip()
            if query:
                if ";" not in query:
                    pos = end
                    continue
                lower_q = query.lower()
                if any(p.lower() in lower_q for p in EXCLUDE_PATTERNS):
                    pos = end
                    continue
                if ONLY_FROM_DUAL_PATTERN.match(query):
                    pos = end
                    continue
                if keyword.upper().startswith("ALTER") and \
                   not re.match(r"ALTER\s+(TABLE|VIEW)\b", query, re.IGNORECASE):
                    pos = end
                    continue
                queries_with_raw.append((query, query))
            pos = end

        for ei_q in ei_queries:
            queries_with_raw.append((ei_q, ei_q))

    except Exception:
        pass
    return queries_with_raw, total_lines


# ============================================================
# SQL TYPE 감지
# ============================================================
def has_top_level_dml(query: str, dml_keyword: str) -> bool:
    depth  = 0
    i      = 0
    q_up   = query.upper()
    length = len(query)
    pat    = re.compile(r"\b" + dml_keyword + r"\b")
    while i < length:
        ch = query[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0 and pat.match(q_up[i:]):
            return True
        i += 1
    return False


def detect_real_sql_type(query: str) -> str:
    q     = query.strip().upper()
    words = q.split()
    first = words[0] if words else "UNKNOWN"

    if first in ("DECLARE", "BEGIN"):
        m = INNER_DML_RE.search(query)
        return m.group(1).upper() if m else "UNKNOWN"

    if first == "WITH":
        if re.search(r"\bINSERT\b", q): return "INSERT"
        if re.search(r"\bUPDATE\b", q): return "UPDATE"
        if re.search(r"\bDELETE\b", q): return "DELETE"
        if re.search(r"\bMERGE\b",  q): return "MERGE"
        return "SELECT"

    if first == "CREATE": return "CREATE"
    if first == "DROP":   return "DROP"

    if first == "SELECT":
        if has_top_level_dml(query, "INSERT"):
            return "INSERT"
        return "SELECT"

    return first


def classify_crud_type(sql_type: str) -> str:
    u = sql_type.upper()
    if u in ("CREATE", "INSERT", "MERGE", "REPLACE", "UPSERT", "EXECUTE"):
        return "C"
    elif u == "SELECT":
        return "R"
    elif u in ("UPDATE", "ALTER"):
        return "U"
    elif u in ("DELETE", "DROP", "TRUNCATE"):
        return "D"
    return "R"


# ============================================================
# 테이블명 정제
# ============================================================
def clean_table(name: str):
    if not name:
        return None
    name  = name.strip()
    name  = re.split(r"\s+", name)[0]
    name  = name.rstrip(";,").replace("(", "").replace(")", "")
    upper = name.upper()
    if (not name
            or upper in RESERVED_WORDS
            or upper == "DUAL"
            or name.isdigit()
            or re.match(r"^\d", name)):
        return None
    return name


# ============================================================
# 파싱 헬퍼
# ============================================================
def strip_inline_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def remove_string_literals(sql: str) -> str:
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r'"[^"]*"', '""', sql)
    return sql


def extract_paren_content(sql: str, start: int) -> tuple:
    depth = 0
    i     = start
    while i < len(sql):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1:i], i
        i += 1
    return sql[start + 1:], len(sql) - 1


def strip_select_columns(sql: str) -> str:
    result = []
    i      = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r"\bSELECT\b", sql_up[i:], re.IGNORECASE)
        if not m:
            result.append(sql[i:])
            break
        sel_pos = i + m.start()
        result.append(sql[i:sel_pos])
        result.append("SELECT ")
        j          = sel_pos + len("SELECT")
        depth      = 0
        found_from = False
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    break
            elif depth == 0:
                if re.match(r"\bFROM\b", sql_up[j:], re.IGNORECASE):
                    result.append("__COLS__ ")
                    i          = j
                    found_from = True
                    break
                if ch == ";":
                    result.append(sql[j:j + 1])
                    i          = j + 1
                    found_from = True
                    break
            j += 1
        if not found_from:
            result.append(sql[j:])
            break
    return "".join(result)


def strip_update_set(sql: str) -> str:
    result = []
    i      = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r"\bSET\b", sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        set_pos = i + m.start()
        result.append(sql[i:set_pos])
        result.append("SET ")
        j     = set_pos + len("SET")
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bWHEN\b", up)
                        or re.match(r"\bON\b", up) or re.match(r"\bFROM\b", up)
                        or ch == ";"):
                    break
            j += 1
        result.append("__SET__ ")
        i = j
    return "".join(result)


def strip_insert_col_list(sql: str) -> str:
    pattern = re.compile(
        r"(INSERT\s+(?:OVERWRITE\s+)?(?:TABLE\s+)?[\w${}.\-]+)"
        r"(\s*\([^)]*\))"
        r"(\s*(?:WITH|SELECT|VALUES)\b)",
        re.IGNORECASE | re.DOTALL,
    )
    return pattern.sub(r"\1 __INSERT_COLS__\3", sql)


def strip_function_args(sql: str) -> str:
    result = []
    i      = 0
    length = len(sql)
    sql_up = sql.upper()
    SKIP = {
        "FROM","JOIN","USING","WITH","ON","AS",
        "SELECT","WHERE","HAVING","SET",
        "INSERT","UPDATE","DELETE","MERGE",
        "CREATE","TABLE","VIEW","INTO",
        "WHEN","THEN","ELSE","AND","OR","NOT",
        "EXISTS","IN","ANY","ALL","CASE"
    }
    while i < length:
        m = re.search(r"(\b\w+)\s*\(", sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        fn_start    = i + m.start()
        fn_name     = m.group(1).upper()
        paren_start = i + m.end() - 1
        if fn_name in SKIP:
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        if fn_start > 0 and sql[fn_start - 1] in (".", "}", "$"):
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        result.append(sql[i:fn_start + len(m.group(1))])
        inner, end_pos = extract_paren_content(sql, paren_start)
        result.append("(__FUNC_ARGS__)")
        i = end_pos + 1
    return "".join(result)


# ============================================================
# CTE 분석
# ============================================================
def extract_cte_map(query: str) -> dict:
    cte_map = {}
    query   = strip_inline_comments(query)
    if "WITH" not in query.upper():
        return cte_map
    with_m = re.search(r"\bWITH\b", query, re.IGNORECASE)
    if not with_m:
        return cte_map

    pos    = with_m.end()
    length = len(query)
    q_up   = query.upper()
    DML_KW = {"SELECT","INSERT","UPDATE","DELETE","MERGE"}

    while pos < length:
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        alias_m = re.match(r"(\w+)", query[pos:])
        if not alias_m:
            break
        alias    = alias_m.group(1)
        alias_up = alias.upper()
        if alias_up in DML_KW:
            break
        pos += alias_m.end()
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        if not re.match(r"\bAS\b", q_up[pos:], re.IGNORECASE):
            break
        pos += 2
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length or query[pos] != "(":
            break
        inner, end_pos = extract_paren_content(query, pos)
        pos = end_pos + 1
        cte_map[alias_up] = extract_sources_recursive(inner)
        while pos < length and query[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        if query[pos] == ",":
            pos += 1
            continue
        break
    return cte_map


# ============================================================
# SET 절 서브쿼리 소스 추출
# ============================================================
def _extract_sources_from_set_subqueries(sql: str) -> set:
    sources = set()
    sql_up  = sql.upper()
    length  = len(sql)
    for set_m in re.finditer(r"\bSET\b", sql_up):
        j     = set_m.end()
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == "(":
                depth += 1
                if depth == 1:
                    inner, end_pos = extract_paren_content(sql, j)
                    inner_up = inner.upper()
                    if re.search(r"\bSELECT\b", inner_up) and re.search(r"\bFROM\b", inner_up):
                        sources.update(extract_sources_recursive(inner))
                    j     = end_pos + 1
                    depth = 0
                    continue
                else:
                    j += 1
                    continue
            elif ch == ")":
                depth = max(depth - 1, 0)
            elif depth == 0:
                up = sql_up[j:]
                if (re.match(r"\bWHERE\b", up) or re.match(r"\bFROM\b", up)
                        or re.match(r"\bWHEN\b", up) or ch == ";"):
                    break
            j += 1
    return sources


# ============================================================
# 소스 테이블 추출 (재귀, 인라인뷰 포함)
# ============================================================
def extract_sources_recursive(query: str) -> set:
    sources = set()
    query   = strip_inline_comments(query)
    q       = remove_string_literals(query)
    q       = strip_select_columns(q)
    sources.update(_extract_sources_from_set_subqueries(q))
    q       = strip_update_set(q)
    q       = strip_insert_col_list(q)
    q       = strip_function_args(q)

    length     = len(q)
    kw_pattern = re.compile(r"\b(FROM|JOIN|USING)\b", re.IGNORECASE)
    CLAUSE_END = {
        "WHERE","ON","WHEN","SET","HAVING","GROUP","ORDER",
        "UNION","INTERSECT","EXCEPT","LIMIT","SELECT",
        "INSERT","UPDATE","DELETE","MERGE","WITH",
        "INNER","LEFT","RIGHT","FULL","CROSS",
        "JOIN","FROM","USING"
    }

    for kw_m in kw_pattern.finditer(q):
        j = kw_m.end()
        while j < length and q[j] in " \t\n\r":
            j += 1
        if j >= length:
            continue

        if q[j] == "(":
            inner, end_pos = extract_paren_content(q, j)
            sources.update(extract_sources_recursive(inner))
            j = end_pos + 1
            alias_m = re.match(r"[\s]+(\w+)", q[j:])
            if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                j += alias_m.end()
            while j < length and q[j] in " \t\n\r":
                j += 1
            if j >= length or q[j] != ",":
                continue
            j += 1

        while j < length:
            while j < length and q[j] in " \t\n\r":
                j += 1
            if j >= length or q[j] in (";", ")"):
                break
            if q[j] == "(":
                inner, end_pos = extract_paren_content(q, j)
                sources.update(extract_sources_recursive(inner))
                j = end_pos + 1
                alias_m = re.match(r"[\s]+(\w+)", q[j:])
                if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                    j += alias_m.end()
            else:
                tok_m = re.match(r"([^\s,;()\n]+)", q[j:])
                if not tok_m:
                    break
                token    = tok_m.group(1)
                token_up = token.upper().rstrip(",;")
                if token_up in CLAUSE_END:
                    break
                tbl = clean_table(token)
                if tbl:
                    sources.add(tbl)
                j += tok_m.end()
                alias_m = re.match(r"[\s]+([^\s,;()\n]+)", q[j:])
                if alias_m:
                    alias_word = alias_m.group(1).upper()
                    if alias_word not in CLAUSE_END and not alias_word.startswith(","):
                        j += alias_m.end()

            while j < length and q[j] in " \t\n\r":
                j += 1
            if j < length and q[j] == ",":
                j += 1
            else:
                break

    return sources


# ============================================================
# 타겟 테이블 추출
# ============================================================
def extract_target_tables(query: str) -> set:
    targets  = set()
    patterns = [
        r"\bINSERT\s+OVERWRITE\s+TABLE\s+([^\s(]+)",
        r"\bINSERT\s+OVERWRITE\s+(?!TABLE\b)([^\s(]+)",
        r"\bINSERT\s+INTO\s+TABLE\s+([^\s(]+)",
        r"\bINSERT\s+INTO\s+(?!TABLE\b)([^\s(]+)",
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?"
        r"(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)",
        r"(?<![_\w])\bUPDATE\s+([^\s(]+)",
        r"\bDELETE\s+FROM\s+([^\s(]+)",
        r"\bMERGE\s+INTO\s+([^\s(]+)",
        r"\bMERGE\s+(?!INTO\b)([^\s(]+)",
        r"\bALTER\s+TABLE\s+([^\s(]+)",
        r"\bTRUNCATE\s+TABLE\s+([^\s(]+)",
        r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([^\s;]+)",
        r"\bDROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?([^\s;]+)",
    ]
    POST_KW = {
        "PARTITION","CLUSTER","STORED","LOCATION","ROW","FORMAT",
        "FIELDS","LINES","TERMINATED","WITH","SELECT","AS","SET",
        "WHERE","VALUES","ON","USING","IF"
    }
    for pat in patterns:
        for m in re.finditer(pat, query, re.IGNORECASE):
            raw = m.group(1).strip().rstrip(";,")
            if not raw or raw.upper() in POST_KW:
                continue
            tbl = clean_table(raw)
            if tbl:
                targets.add(tbl)
    return targets


# ============================================================
# TEMP 레지스트리 수집
# ============================================================
def build_temp_registry(source_dir: str) -> set:
    temp_set = set()
    for root, _, files in os.walk(source_dir):
        for file in files:
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue
            full_path = os.path.join(root, file)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                for m in TEMP_CREATE_PAT.finditer(preprocess(raw)):
                    name = clean_table(m.group(1))
                    if name:
                        temp_set.add(name.upper())
            except Exception:
                pass
    return temp_set


# ============================================================
# 타입 판별
# ============================================================
def get_table_type(name, cte_names_upper: set, temp_registry: set) -> str:
    if not name:
        return ""
    nu = name.upper()
    if nu in cte_names_upper:
        return "CTE"
    if nu in temp_registry:
        return "TEMP"
    return "TABLE"


# ============================================================
# CTE depth 계산
# ============================================================
def compute_cte_depths(cte_map: dict) -> dict:
    cte_names = set(cte_map.keys())
    depth_map = {}

    def get_depth(cte_name, visiting=None):
        if cte_name in depth_map:
            return depth_map[cte_name]
        if visiting is None:
            visiting = set()
        if cte_name in visiting:
            return 1
        current_visiting = visiting | {cte_name}
        deps = [s.upper() for s in cte_map.get(cte_name, set())
                if s and s.upper() in cte_names]
        depth_map[cte_name] = (
            max(get_depth(d, current_visiting) for d in deps) + 1
            if deps else 1
        )
        return depth_map[cte_name]

    for name in cte_map:
        get_depth(name)
    return depth_map


# ============================================================
# 출력 행 생성
# ============================================================
def build_rows(cte_map, sources_raw, targets, crud_type, sql_type,
               base_directory, file_name, dir_file, mode,
               cte_names_upper, temp_registry) -> list:
    rows          = []
    seen          = set()
    cte_depth_map = compute_cte_depths(cte_map) if mode == "DETAIL" else {}

    def add_row(src, tgt, d):
        pair = (src, tgt)
        if pair in seen:
            return
        seen.add(pair)
        src_type = get_table_type(src, cte_names_upper, temp_registry)
        tgt_type = get_table_type(tgt, cte_names_upper, temp_registry)
        src_schema, src_table = resolve_and_split_schema_table(src)
        tgt_schema, tgt_table = resolve_and_split_schema_table(tgt)
        rows.append({
            "base_directory": base_directory,
            "file_name":      file_name,
            "dir_file":       dir_file,
            "crud_type":      crud_type,
            "sql_type":       sql_type,
            "source_table":   src or "",
            "source_type":    src_type,
            "target_table":   tgt or "",
            "target_type":    tgt_type,
            "depth":          d,
            "src_schema":     src_schema,
            "src_table":      src_table,
            "tgt_schema":     tgt_schema,
            "tgt_table":      tgt_table,
        })

    real_sources = set()
    for s in sources_raw:
        if s and s.upper() in cte_names_upper:
            real_sources.update(cte_map[s.upper()])
        elif s:
            real_sources.add(s)
    real_sources = {s for s in real_sources
                    if s and s.upper() not in cte_names_upper}

    tgt_set = targets if targets else {None}
    src_set = real_sources if real_sources else {None}
    has_src = any(s is not None for s in src_set)

    for tgt in sorted(tgt_set, key=lambda x: x or ""):
        for src in sorted(src_set, key=lambda x: x or ""):
            if has_src and src is None:
                continue
            add_row(src, tgt, 1)

    if mode == "DETAIL" and cte_map and targets:
        for cte_name, cte_srcs in cte_map.items():
            cte_d = cte_depth_map.get(cte_name, 1)
            for src in sorted(cte_srcs, key=lambda x: x or ""):
                if src:
                    add_row(src, cte_name, cte_d)

        cte_refs = {s for s in sources_raw
                    if s and s.upper() in cte_names_upper}
        if not cte_refs:
            cte_refs = set(cte_map.keys())

        for cte_name in sorted(cte_refs, key=lambda x: x or ""):
            cte_d = cte_depth_map.get(cte_name.upper(), 1)
            for tgt in sorted(targets, key=lambda x: x or ""):
                add_row(cte_name, tgt, cte_d + 1)

    return rows


# ============================================================
# CSV 저장 (리니지)
# ============================================================
FIELDNAMES = [
    "base_directory", "file_name", "dir_file",
    "crud_type", "sql_type",
    "source_table", "source_type",
    "target_table", "target_type",
    "depth",
    "src_schema", "src_table",
    "tgt_schema",  "tgt_table",
    "op_dtm",
]

def save_csv(rows_buffer: list, source_dir: str, op_dtm: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    last_dir  = os.path.basename(os.path.normpath(source_dir))
    timestamp = op_dtm.replace("-", "").replace(" ", "_").replace(":", "")
    csv_file  = f"{PROGRAM_NAME}_{last_dir}_{MODE.lower()}_{timestamp}.csv"
    csv_path  = os.path.join(OUT_DIR, csv_file)

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows_buffer:
            row = dict(r)
            row["op_dtm"] = op_dtm
            writer.writerow(row)

    return csv_path


# ============================================================
# MAIN
# ============================================================
def main():
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    total_files      = 0
    total_queries    = 0
    total_rows       = 0
    total_file_lines = 0

    # --db 옵션: mysql.conf 사전 확인
    mysql_conf = None
    if USE_DB:
        if _MYSQL_DRIVER is None:
            print("[ERROR] MySQL 드라이버가 없습니다.")
            print("        pip install pymysql  또는  pip install mysql-connector-python")
            sys.exit(1)
        mysql_conf, err = load_mysql_conf(CONF_PATH)
        if err:
            print(f"[ERROR] {err}")
            sys.exit(1)
        table_name            = build_dynamic_table_name(SOURCE_DIR, MODE)
        query_text_table_name = build_query_text_table_name(SOURCE_DIR, MODE)
        print("=" * 60)
        print(f"[INFO] MySQL 드라이버       : {_MYSQL_DRIVER}")
        print(f"[INFO] 접속 호스트          : {mysql_conf.get('host')}:{mysql_conf.get('port', 3306)}")
        print(f"[INFO] 데이터베이스         : {mysql_conf.get('database')}")
        print(f"[INFO] 등록 테이블 (리니지) : {table_name}")
        print(f"[INFO] 등록 테이블 (쿼리)   : {query_text_table_name}")
        print("=" * 60)

    print(f"\n[INFO] 분석 시작        : {os.path.abspath(SOURCE_DIR)}")
    print(f"[INFO] 실행 모드        : {MODE}")
    print(f"[INFO] 처리일시 (op_dtm): {op_dtm}")
    print("-" * 60)

    temp_registry = build_temp_registry(SOURCE_DIR)

    rows_buffer       = []
    query_text_buffer = []

    # ================================================================
    # 키워드 추출 결과 버퍼
    # ----------------------------------------------------------------
    # (1) emrput_rows : EMRPUTF / EMRPUT 포함 라인
    #     컬럼: base_directory, file_name, dir_file, emrput_type, emrput_line
    #
    # (2) default_rows : "default" 포함 라인
    #     컬럼: base_directory, file_name, dir_file, keyword, line
    #
    # (3) key_mst_rows : "key_mst" 포함 라인
    #     컬럼: base_directory, file_name, dir_file, keyword, line
    # ================================================================
    emrput_rows  = []   # list of [base_dir, file, path, emrput_type, line]
    default_rows = []   # list of [base_dir, file, path, keyword, line]
    key_mst_rows = []   # list of [base_dir, file, path, keyword, line]

    for root, _, files in os.walk(SOURCE_DIR):
        for file in sorted(files):
            if not file.lower().endswith(tuple(TARGET_EXTENSIONS)):
                continue
            total_files   += 1
            full_path      = os.path.join(root, file)
            base_directory = os.path.abspath(root)

            # ── (1) EMRPUTF / EMRPUT 라인 수집 ──────────────────────
            for item in extract_emrput_lines(full_path):
                emrput_rows.append([
                    base_directory,
                    file,
                    full_path,
                    item["emrput_type"],   # "EMRPUTF" 또는 "EMRPUT"
                    item["line"],
                ])

            # ── (2) default 라인 수집 (대소문자 무시) ────────────────
            for item in extract_keyword_lines(full_path, "default", case_sensitive=False):
                default_rows.append([
                    base_directory,
                    file,
                    full_path,
                    item["keyword"],
                    item["line"],
                ])

            # ── (3) key_mst 라인 수집 (대소문자 무시) ────────────────
            for item in extract_keyword_lines(full_path, "key_mst", case_sensitive=False):
                key_mst_rows.append([
                    base_directory,
                    file,
                    full_path,
                    item["keyword"],
                    item["line"],
                ])

            # ── 쿼리 추출 ────────────────────────────────────────────
            queries_with_raw, file_lines = extract_queries_from_file(full_path)
            total_file_lines += file_lines
            total_queries    += len(queries_with_raw)

            for query, raw_query in queries_with_raw:
                sql_type  = detect_real_sql_type(query)
                crud_type = classify_crud_type(sql_type)
                cte_map   = extract_cte_map(query)
                sources   = extract_sources_recursive(query)
                targets   = extract_target_tables(query)
                cte_upper = set(cte_map.keys())

                query_text_buffer.append({
                    "base_directory": base_directory,
                    "file_name":      file,
                    "dir_file":       full_path,
                    "crud_type":      crud_type,
                    "sql_type":       sql_type,
                    "query_text":     raw_query,
                })

                if not sources and not targets:
                    continue

                rows = build_rows(
                    cte_map, sources, targets,
                    crud_type, sql_type,
                    base_directory, file, full_path,
                    MODE, cte_upper, temp_registry,
                )
                rows_buffer.extend(rows)
                total_rows += len(rows)

    # ── 진행 요약 ────────────────────────────────────────────────────
    print(f"  조사 파일 수    : {total_files:>8,} 개  "
          f"(확장자: {', '.join(sorted(TARGET_EXTENSIONS))})")
    print(f"  추출 쿼리 수    : {total_queries:>8,} 건")
    print(f"  총 파일 라인 수 : {total_file_lines:>8,} 줄")
    print(f"  분석 결과 행 수 : {total_rows:>8,} 건")
    print(f"  쿼리 텍스트 건수: {len(query_text_buffer):>8,} 건")

    if not rows_buffer and not query_text_buffer:
        print("\n[WARN] 분석 결과가 없어 CSV/DB 저장을 건너뜁니다.")
        return

    # ── 리니지 CSV 저장 ──────────────────────────────────────────────
    csv_path = ""
    if rows_buffer:
        csv_path = save_csv(rows_buffer, SOURCE_DIR, op_dtm)
        print(f"  저장 CSV 파일   : {csv_path}")

    # ── DB 적재 (--db 옵션) ──────────────────────────────────────────
    db_inserted    = 0
    db_err         = None
    db_qt_inserted = 0
    db_qt_err      = None

    if USE_DB and mysql_conf:
        if rows_buffer:
            print("\n[INFO] MySQL 리니지 테이블 적재 시작 ...")
            db_inserted, db_err = db_insert_all(
                rows_buffer, run_id, op_dtm, mysql_conf, SOURCE_DIR, MODE
            )
        if query_text_buffer:
            print("[INFO] MySQL 쿼리 텍스트 테이블 적재 시작 ...")
            db_qt_inserted, db_qt_err = db_insert_query_text_all(
                query_text_buffer, op_dtm, mysql_conf, SOURCE_DIR, MODE
            )

    # ── 결과 요약 출력 ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f" SQL 소스/타겟 테이블 추출 완료 [{MODE}]")
    print("=" * 60)
    print(f"  실행 모드         : {MODE}")
    print(f"  처리일시          : {op_dtm}")
    if csv_path:
        print(f"  CSV 파일 위치     : {csv_path}")
    print(f"  처리 파일 건수    : {total_files:,}")
    print(f"  추출 쿼리 건수    : {total_queries:,}")
    print(f"  생성 행 건수      : {total_rows:,}")
    print(f"  쿼리 텍스트 건수  : {len(query_text_buffer):,}")

    if USE_DB:
        print("-" * 60)
        if db_err:
            print(f"  DB 리니지 등록    : 실패")
            print(f"  DB 오류 내용      : {db_err}")
        else:
            tbl = build_dynamic_table_name(SOURCE_DIR, MODE)
            print(f"  DB 리니지 등록    : 성공")
            print(f"  DB 리니지 테이블  : {mysql_conf.get('database')}.{tbl}")
            print(f"  DB 리니지 건수    : {db_inserted:,}")
            print(f"  DB run_id         : {run_id}")

        if db_qt_err:
            print(f"  DB 쿼리텍스트 등록: 실패")
            print(f"  DB 오류 내용      : {db_qt_err}")
        else:
            qt_tbl = build_query_text_table_name(SOURCE_DIR, MODE)
            print(f"  DB 쿼리텍스트 등록: 성공")
            print(f"  DB 쿼리텍스트 테이블: {mysql_conf.get('database')}.{qt_tbl}")
            print(f"  DB 쿼리텍스트 건수: {db_qt_inserted:,}")

    print("=" * 60)
    print("[INFO] 모든 처리가 완료되었습니다.\n")

    # ================================================================
    # 키워드 CSV 3개 파일 생성
    # ================================================================
    print("------------------------------------")
    print("[INFO] 키워드 CSV 파일 생성 시작")
    print("------------------------------------")

    # ── (1) EMRPUT / EMRPUTF CSV ─────────────────────────────────────
    if emrput_rows:
        cnt_emrputf = sum(1 for r in emrput_rows if r[3] == "EMRPUTF")
        cnt_emrput  = sum(1 for r in emrput_rows if r[3] == "EMRPUT")
        path = save_keyword_csv(
            rows   = emrput_rows,
            suffix = "emrput",
            source_dir = SOURCE_DIR,
            op_dtm     = op_dtm,
            header = ["base_directory", "file_name", "dir_file",
                      "emrput_type", "emrput_line"],
        )
        print(f"[1] EMRPUT  파일 : {path}")
        print(f"    EMRPUTF 건수  : {cnt_emrputf:,}")
        print(f"    EMRPUT  건수  : {cnt_emrput:,}")
        print(f"    합계    건수  : {len(emrput_rows):,}")
    else:
        print("[1] EMRPUT  : 해당 라인 없음 (CSV 미생성)")

    # ── (2) default CSV ──────────────────────────────────────────────
    if default_rows:
        path = save_keyword_csv(
            rows   = default_rows,
            suffix = "default",
            source_dir = SOURCE_DIR,
            op_dtm     = op_dtm,
            header = ["base_directory", "file_name", "dir_file",
                      "keyword", "line"],
        )
        print(f"[2] default 파일 : {path}")
        print(f"    default 건수  : {len(default_rows):,}")
    else:
        print("[2] default : 해당 라인 없음 (CSV 미생성)")

    # ── (3) key_mst CSV ──────────────────────────────────────────────
    if key_mst_rows:
        path = save_keyword_csv(
            rows   = key_mst_rows,
            suffix = "key_mst",
            source_dir = SOURCE_DIR,
            op_dtm     = op_dtm,
            header = ["base_directory", "file_name", "dir_file",
                      "keyword", "line"],
        )
        print(f"[3] key_mst 파일 : {path}")
        print(f"    key_mst 건수  : {len(key_mst_rows):,}")
    else:
        print("[3] key_mst : 해당 라인 없음 (CSV 미생성)")

    print("====================================")
    print("처리 완료")
    print(f"파일 수 : {total_files:,}")
    print(f"쿼리 수 : {total_queries:,}")
    print("====================================")


if __name__ == "__main__":
    main()