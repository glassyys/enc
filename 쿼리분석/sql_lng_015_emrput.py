## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB/mi --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID/SRC/SIDHUB --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TMT --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TMT --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDIA --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDIA --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDM --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/TDM --mode DETAIL --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID --mode SIMPLE --db
## python3 /home/p190872/spsrc/sql_lng_015_emrput.py /NAS/MIDP/DBMSVC/MIDP/SID --mode DETAIL --db
## 
## "--conf 경로파일명(예시: /home/p190872/spsrc/mysql.conf)"  미지정시 현재디렉토리의 mysql.conf 파일 읽음
##
## [mysql연결해서 DB등록하는 로직추가 수정]
## 아래 [원본소스]에 대해 csv파일생성하는 전체로직 유지하고 
## 추가로 csv생성레이아웃대로 mysql연결후 
## 테이블에 등록하는 부분 추가하도록 수정한 전체소스요청
## 
## 답변:추가된 내용 요약
## 원본 소스의 CSV 생성 로직은 한 줄도 변경하지 않고, 아래 항목만 추가했습니다.
## 새로운 실행 옵션
## bashpython3 sql_lng_007_with.py 소스디렉토리 [--mode SIMPLE|DETAIL] [--db] [--conf 경로]
## 
## --db 미지정 → 기존과 동일하게 CSV만 생성
## --db 지정 → CSV 생성 + MySQL DB 등록
## 
## 추가된 구성요소
## 항목	내용
## _MYSQL_DRIVER 자동 감지	mysql-connector-python 우선, 없으면 pymysql 자동 폴백
## load_mysql_conf()	mysql.conf (INI 형식) 로드, 필수항목 누락 시 오류 출력
## _DDL_CREATE	sql_lineage 테이블 CREATE TABLE IF NOT EXISTS 자동 실행
## db_insert_all()	executemany 일괄 INSERT, 실패 시 rollback 후 오류 메시지 반환
## run_id	타임스탬프(실행 단위 식별자), 같은 실행 건을 DB에서 묶어 조회 가능
## --conf 경로	mysql.conf 위치를 직접 지정 가능 (기본: 실행 디렉토리)
## 
## mysql.conf 예시 (실행 디렉토리에 생성)
## ini[mysql]
## host     = localhost
## port     = 3306
## user     = root
## password = secret
## database = lineage_db
## table    = sql_lineage
## charset  = utf8mb4
## [주의]
## 파일생성시 소스에 설명된 아래 내용 중 주석적용이 안됨
##    table    = sql_lineage    # 선택 (기본값: sql_lineage)
##    charset  = utf8mb4        # 선택 (기본값: utf8mb4)
## "    # 선택 (기본값: sql_lineage)"
## "        # 선택 (기본값: utf8mb4)"
## 이 내용 모두 값으로 인식하기 때문에 mysql.conf 파일생성시 삭제필요
## ★아래처럼 생성해야 함★:
## " 'NoneType' object has no attribute 'encoding'" 오류 발생함
## 원인 "charset"값을 "utf8mb4" 값으로 인식못하고 "utf8mb4        # 선택 (기본값: utf8mb4)" 전체로 인식
##   table    = sql_lineage
##   charset  = utf8mb4
## 
## ■생성되는 테이블 예시
## 실행:
## python3 sql_lng_015_emrput.py /data/project1 --mode DETAIL --db
## 
## 생성 테이블명:
## sql_lng_015_emrput_project1_detail
## 아래 현재소스에서
## 아래내용중 2단계가 skip 되고 있는데 이 부분 보완해서 처리하기위해 수정해야할 부분 소스수정한 전체소스부탁
## 
## 단계 (Depth)	소스 (Source)	타겟 (Target)	유형
## 1	S1, S2, S3	cte_1, cte_2, cte_3	CTE 생성
## 2	cte_1, cte_2, cte_3	cte_4	중간 가공
## 3	cte_1, 2, 3, cte_4	tb	최종 적재
## 
## [";" 있는 쿼리만 추출]
## 예외케이스가 추출되는데
## MAIN_QUERY_START 중
## merge로 인해 추출되지만 실제쿼리가 아닌 경우가 추출되고 있습니다.
## 
## MAIN_QUERY_START 값 다음에 ";" 이 없는 자료는 추출안되도록 수정한 전체소스
## 기존로직에는 변함이 없고 요청한 MAIN_QUERY_START 값 뒤에 ";" 이 없는 쿼리는 분석을 하지 않도록 수정한 최종소스구현
## 파일은 sql_lng_013_with.py 로 생성요청
##
## 테이블생성전 DROP 명령추가(sql_lng_015_emrput.py)

#!/usr/bin/env python3
# sql_lng_015_emrput.py
#
# 실행방법:
# python3 sql_lng_015_emrput.py 소스디렉토리 [--mode SIMPLE|DETAIL] [--db] [--conf 경로]
#
# 옵션:
# --mode SIMPLE (기본값) : CTE 투명 처리, 물리소스->타겟만 출력
# --mode DETAIL : WITH절 CTE 흐름 포함 출력
# --db : CSV 생성 + MySQL DB 등록 (mysql.conf 필요)
# (미지정 시 CSV 만 생성)
# --conf 경로 : mysql.conf 파일 경로 지정
# (미지정 시 실행 디렉토리의 mysql.conf 사용)
#
# 출력 컬럼:
# base_directory, file_name, dir_file, crud_type, sql_typ,
# source_table, source_type(TABLE/CTE/TEMP),
# target_table, target_type(TABLE/CTE/TEMP),
# depth, src_schema, src_table, tgt_schema, tgt_table
#
# mysql.conf (INI 형식):
# [mysql]
# host = localhost
# port = 3306
# user = root
# password = secret
# database = lineage_db
# table = sql_lineage # 선택 (기본값: sql_lineage)
# charset = utf8mb4 # 선택 (기본값: utf8mb4)
import os
import re
import sys
import csv
import configparser
from datetime import datetime
# ============================================================
# 프로그램/경로 기반 테이블명 생성
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
# ============================================================
# [추가] MySQL 드라이버 동적 로드
# mysql-connector-python 우선, 없으면 pymysql 폴백
# ============================================================
_MYSQL_DRIVER = None # 'connector' | 'pymysql' | None

_MYSQL_DRIVER = None

def _detect_mysql_driver():
    global _MYSQL_DRIVER
    try:
        import mysql.connector
        _MYSQL_DRIVER = 'connector'
    except ImportError:
        try:
            import pymysql
            _MYSQL_DRIVER = 'pymysql'
        except ImportError:
            _MYSQL_DRIVER = None

_detect_mysql_driver()

def _mysql_connect(conf):
    host = conf.get('host', 'localhost')
    port = int(conf.get('port', 3306))
    user = conf.get('user', '')
    password = conf.get('password', '')
    database = conf.get('database', '')
    charset = conf.get('charset', 'utf8mb4')
    if _MYSQL_DRIVER == 'connector':
        import mysql.connector
        return mysql.connector.connect(
            host=host, port=port,
            user=user, password=password,
            database=database, charset=charset
        )
    elif _MYSQL_DRIVER == 'pymysql':
        import pymysql
        return pymysql.connect(
            host=host, port=port,
            user=user, password=password,
            database=database, charset=charset,
            autocommit=False
        )
    else:
        raise ImportError("MySQL 드라이버가 없습니다.")

# ===========================
# [추가] EMRPUT 라인 추출 함수
# ===========================
def extract_emrput_lines(file_path):
    results = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "EMRPUT" in line:
                    results.append(line.strip())
    except Exception:
        pass
    return results

_DDL_CREATE = """
CREATE TABLE IF NOT EXISTS `{table}` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `run_id` VARCHAR(30) NOT NULL COMMENT '실행 타임스탬프(YYYYMMDD_HHMMSS)',
  `base_directory` TEXT COMMENT '소스파일 디렉토리 경로',
  `file_name` VARCHAR(500) COMMENT '파일명',
  `dir_file` TEXT COMMENT '소스파일 전체경로',
  `crud_type` VARCHAR(1) COMMENT 'C/R/U/D',
  `sql_typ` VARCHAR(20) COMMENT 'INSERT/SELECT/UPDATE/DELETE/...',
  `source_table` VARCHAR(500) COMMENT '소스 테이블 (원본명)',
  `source_type` VARCHAR(10) COMMENT 'TABLE/CTE/TEMP',
  `target_table` VARCHAR(500) COMMENT '타겟 테이블 (원본명)',
  `target_type` VARCHAR(10) COMMENT 'TABLE/CTE/TEMP',
  `depth` INT COMMENT '데이터 흐름 단계',
  `src_schema` VARCHAR(200) COMMENT '소스 스키마명',
  `src_table` VARCHAR(300) COMMENT '소스 테이블명 (스키마 제외)',
  `tgt_schema` VARCHAR(200) COMMENT '타겟 스키마명',
  `tgt_table` VARCHAR(300) COMMENT '타겟 테이블명 (스키마 제외)',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_run_id` (`run_id`),
  KEY `idx_file_name` (`file_name`(191)),
  KEY `idx_src_table` (`src_table`(191)),
  KEY `idx_tgt_table` (`tgt_table`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='SQL 소스/타겟 리니지 정보';
"""

_SQL_INSERT = """
INSERT INTO `{table}`
  (run_id, base_directory, file_name, dir_file, crud_type, sql_typ,
   source_table, source_type, target_table, target_type, depth,
   src_schema, src_table, tgt_schema, tgt_table)
VALUES
  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

def build_dynamic_table_name(source_dir, mode):
    source_last_dir = os.path.basename(os.path.abspath(source_dir))
    mode_suffix = mode.lower()
    table_name = f"{PROGRAM_NAME}_{source_last_dir}_{mode_suffix}"
    return table_name.lower()

def db_insert_all(rows_buffer, run_id, mysql_conf, source_dir, mode):
    table_name = build_dynamic_table_name(source_dir, mode)
    try:
        conn = _mysql_connect(mysql_conf)
        cursor = conn.cursor()

        # 테이블이 이미 존재하면 삭제 (컬럼 구조 변경 등에 대응)
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        conn.commit()

        # 테이블 생성
        cursor.execute(_DDL_CREATE.format(table=table_name))
        conn.commit()

        batch = []
        for r in rows_buffer:
            batch.append((
                run_id,
                r[0], r[1], r[2],
                r[3], r[4],
                r[5] or '', r[6] or '',
                r[7] or '', r[8] or '',
                r[9],
                r[10] or '', r[11] or '',
                r[12] or '', r[13] or '',
            ))

        if batch:
            cursor.executemany(_SQL_INSERT.format(table=table_name), batch)
            conn.commit()

        inserted = len(batch)
        cursor.close()
        conn.close()
        print(f"MySQL 테이블 DROP 후 재생성/적재 완료: {table_name} ({inserted}건)")
        return inserted, None

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        try:
            cursor.close()
            conn.close()
        except:
            pass
        return 0, str(e)
# ============================================================
# [추가] mysql.conf 로드
# ============================================================
def load_mysql_conf(explicit_path=None):
    path = explicit_path if explicit_path else os.path.join(os.getcwd(), "mysql.conf")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None, f"mysql.conf 파일을 찾을 수 없습니다: {path}"
    cp = configparser.ConfigParser()
    try:
        cp.read(path, encoding='utf-8')
    except Exception as e:
        return None, f"mysql.conf 읽기 오류: {e}"
    if not cp.has_section('mysql'):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."
    conf = dict(cp['mysql'])
    missing = [k for k in ('host', 'user', 'password', 'database') if not conf.get(k)]
    if missing:
        return None, f"mysql.conf 필수 항목 누락: {', '.join(missing)}"
    return conf, None

def parse_args():
    args = sys.argv[1:]
    src_dir = None
    mode = "SIMPLE"
    use_db = False
    conf_path = None
    i = 0
    while i < len(args):
        if args[i] == "--mode":
            if i + 1 < len(args):
                mode = args[i+1].upper()
                if mode not in ("SIMPLE","DETAIL"):
                    print(f"오류: --mode 값은 SIMPLE 또는 DETAIL 이어야 합니다.")
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
        print("사용법: python3 sql_lng_015_emrput.py 소스디렉토리 [--mode SIMPLE|DETAIL] [--db] [--conf 경로]")
        sys.exit(1)
    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        print("오류: 유효한 디렉토리가 아닙니다.")
        sys.exit(1)
    return src_dir, mode, use_db, conf_path

SOURCE_DIR, MODE, USE_DB, CONF_PATH = parse_args()
# ============================================================
# 신규: db_schema.env 변수 로드
# ============================================================
def load_schema_variables():
    env_path = os.path.join(os.getcwd(), "db_schema.env")
    schema_map = {}
    if not os.path.isfile(env_path):
        print(f"경고: db_schema.env 파일을 찾을 수 없습니다. ({env_path}) → 변수 치환 생략")
        return schema_map
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                m = re.match(r'^(\w+)=["\']?([^"\']*)["\']?$', line)
                if m:
                    key, value = m.groups()
                    schema_map[key] = value.strip()
    except Exception as e:
        print(f"db_schema.env 읽기 오류: {e} → 변수 치환 생략")
    return schema_map
SCHEMA_VARS = load_schema_variables()
# ============================================================
# 신규 헬퍼: schema 변수 치환 + split
# ============================================================
def resolve_and_split_schema_table(full_name):
    if not full_name:
        return "", ""
    resolved = full_name
    def replace_var(match):
        var_name = match.group(1) or match.group(2)
        return SCHEMA_VARS.get(var_name, match.group(0))
    resolved = re.sub(r'\$\{(\w+)\}', replace_var, resolved)
    resolved = re.sub(r'\$(\w+)(?=\W|$)', replace_var, resolved)
    parts = resolved.split(".", 1)
    if len(parts) == 2:
        schema, table = parts
        return schema.strip(), table.strip()
    else:
        return "", resolved.strip()
# ============================================================
# 2. 설정
# ============================================================
TARGET_EXTENSIONS = ('.sh', '.hql', '.sql', '.uld', '.ld')
DELIMITER = ","
EXCLUDE_PATTERNS = [
    "insert into sidtest.ad1901_rgb_ac190212_svc(svc_mgmt_num)",
    "sidtest.ad1901_rgb_ac190212_svc",
]
RESERVED_WORDS = {
    "SET","WHERE","AND","OR","ON","WHEN","THEN","ELSE",
    "VALUES","SELECT","UPDATE","INSERT","DELETE","MERGE",
    "USING","FROM","JOIN","INTO","GROUP","ORDER","BY",
    "HAVING","TABLE","OVERWRITE","POSITION","SUBSTRING",
    "CAST","TRIM","COUNT","SUM","MAX","MIN","AVG",
    "SESSION"
}
ONLY_FROM_DUAL_PATTERN = re.compile(
    r'^\s*SELECT\s+.*?\s+FROM\s+DUAL\s*;?\s*$',
    re.IGNORECASE | re.DOTALL
)
TEMP_CREATE_PAT = re.compile(
    r'\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY|TEMP)\s+(?:TABLE|VIEW)'
    r'\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(;]+)',
    re.IGNORECASE
)
# ============================================================
# 3. MAIN QUERY START 패턴
# ============================================================
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
DECLARE_BEGIN_BLOCK_RE = re.compile(r'^\s*(DECLARE|BEGIN)\b', re.IGNORECASE)
INNER_DML_RE = re.compile(
    r'\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|REPLACE|ALTER)\b',
    re.IGNORECASE
)
# ============================================================
# 4. 전처리
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
        ('(?:[^']|'')*') |
        ("(?:[^"]|"")*") |
        (--[^\n]*$) |
        (/\*.*?\*/)
        """,
        re.MULTILINE | re.DOTALL | re.VERBOSE
    )
    def replacer(match):
        if match.group(1) or match.group(2):
            return match.group(0)
        return ""
    return pattern.sub(replacer, content)
# ============================================================
# 5. EXECUTE IMMEDIATE 내부 SQL 추출
# ============================================================
def extract_execute_immediate(content):
    results = []
    pattern = re.compile(
        r'\bEXECUTE\s+IMMEDIATE\s+\'(.*?)\'',
        re.IGNORECASE | re.DOTALL
    )
    for m in pattern.finditer(content):
        inner_sql = m.group(1).strip()
        if inner_sql:
            results.append(inner_sql)
    return results
# ============================================================
# 6. depth 기반 쿼리 추출
# ============================================================
def extract_queries_from_file(file_path):
    queries = []
    total_lines = 0
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
        total_lines = raw.count("\n") + 1
        content = preprocess(raw)
        ei_queries = extract_execute_immediate(content)
        masked = re.sub(
            r'\bEXECUTE\s+IMMEDIATE\s+\'.*?\'',
            'EXECUTE_IMMEDIATE_MASKED',
            content,
            flags=re.IGNORECASE | re.DOTALL
        )
        pos = 0
        length = len(masked)
        while pos < length:
            match = MAIN_QUERY_START.search(masked, pos)
            if not match:
                break
            keyword = match.group(1).upper()
            start = match.start()
            if keyword.startswith("END"):
                line_start = masked.rfind("\n", 0, start) + 1
                line_end = masked.find("\n", start)
                if line_end == -1:
                    line_end = length
                line_text = masked[line_start:line_end]
                if END_IF_PATTERN.match(line_text):
                    pos = line_end
                    continue
            end = start
            depth = 0
            in_string = False
            quote_char = None
            while end < length:
                ch = masked[end]
                if ch in ("'", '"'):
                    if not in_string:
                        in_string = True
                        quote_char = ch
                    elif quote_char == ch:
                        in_string = False
                elif not in_string:
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
                # 🔥 요청하신 수정: MAIN_QUERY_START 매칭 후 ";" 이 없는 경우는 추출/분석하지 않음
                # (MERGE로 인한 비실제 쿼리 예외 완전 차단)
                # 기존 로직은 100% 그대로 유지
                if ';' not in query:
                    pos = end
                    continue
                lower_query = query.lower()
                if any(p.lower() in lower_query for p in EXCLUDE_PATTERNS):
                    pos = end
                    continue
                if ONLY_FROM_DUAL_PATTERN.match(query):
                    pos = end
                    continue
                kw_up = keyword.replace(" ", "")
                if keyword.upper().startswith("ALTER") and \
                   not re.match(r'ALTER\s+(TABLE|VIEW)\b', query, re.IGNORECASE):
                    pos = end
                    continue
                queries.append(query)
            pos = end
        queries.extend(ei_queries)
    except Exception as e:
        pass
    return queries, total_lines
# ============================================================
# 7. SQL TYPE 감지
# ============================================================
def has_top_level_dml(query, dml_keyword):
    depth = 0
    i = 0
    q_up = query.upper()
    length = len(query)
    pat = re.compile(r'\b' + dml_keyword + r'\b')
    while i < length:
        ch = query[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(depth - 1, 0)
        elif depth == 0:
            if pat.match(q_up[i:]):
                return True
        i += 1
    return False
# ============================================================
# detect_real_sql_type() 에 DROP 명시적으로 처리 추가 (안전장치)
# ============================================================
def detect_real_sql_type(query):
    q = query.strip().upper()
    words = q.split()
    first_word = words[0] if words else "UNKNOWN"

    if first_word in ("DECLARE", "BEGIN"):
        m = INNER_DML_RE.search(query)
        return m.group(1).upper() if m else "UNKNOWN"

    if first_word == "WITH":
        if re.search(r'\bINSERT\b', q): return "INSERT"
        if re.search(r'\bUPDATE\b', q): return "UPDATE"
        if re.search(r'\bDELETE\b', q): return "DELETE"
        if re.search(r'\bMERGE\b', q): return "MERGE"
        return "SELECT"

    if first_word == "CREATE":
        return "CREATE"

    if first_word == "DROP":          # ← 여기 추가!
        return "DROP"

    if first_word == "SELECT":
        if has_top_level_dml(query, "INSERT"):
            return "INSERT"
        return "SELECT"

    return first_word
def classify_sql_type(sql_typ):
    sql_up = sql_typ.upper()
    if sql_up in ("CREATE", "INSERT", "MERGE", "REPLACE", "UPSERT", "EXECUTE"):
        return "C"
    elif sql_up == "SELECT":
        return "R"
    elif sql_up in ("UPDATE", "ALTER"):
        return "U"
    elif sql_up in ("DELETE", "DROP", "TRUNCATE"):
        return "D"
    return "R"
# ============================================================
# 8. 테이블명 정제
# ============================================================
def clean_table(name):
    if not name:
        return None
    name = name.strip()
    name = re.split(r'\s+', name)[0]
    name = name.rstrip(";,")
    name = name.replace("(", "").replace(")", "")
    upper = name.upper()
    if (not name
            or upper in RESERVED_WORDS
            or upper == "DUAL"
            or name.isdigit()
            or re.match(r'^\d', name)):
        return None
    return name
# ============================================================
# 9. 파싱 전처리 헬퍼
# ============================================================
def strip_inline_comments(sql):
    sql = re.sub(r'--[^\n]*', '', sql)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql
def remove_string_literals(sql):
    result = re.sub(r"'[^']*'", "''", sql)
    result = re.sub(r'"[^"]*"', '""', result)
    return result
def extract_paren_content(sql, start):
    depth = 0
    i = start
    while i < len(sql):
        if sql[i] == '(':
            depth += 1
        elif sql[i] == ')':
            depth -= 1
            if depth == 0:
                return sql[start + 1:i], i
        i += 1
    return sql[start + 1:], len(sql) - 1
def strip_select_columns(sql):
    result = []
    i = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r'\bSELECT\b', sql_up[i:], re.IGNORECASE)
        if not m:
            result.append(sql[i:])
            break
        sel_pos = i + m.start()
        result.append(sql[i:sel_pos])
        result.append('SELECT ')
        j = sel_pos + len('SELECT')
        depth = 0
        found_from = False
        while j < length:
            ch = sql[j]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    break
            elif depth == 0:
                if re.match(r'\bFROM\b', sql_up[j:], re.IGNORECASE):
                    result.append('__COLS__ ')
                    i = j
                    found_from = True
                    break
                if ch == ';':
                    result.append(sql[j:j + 1])
                    i = j + 1
                    found_from = True
                    break
            j += 1
        if not found_from:
            result.append(sql[j:])
            break
    return ''.join(result)
def strip_update_set(sql):
    result = []
    i = 0
    sql_up = sql.upper()
    length = len(sql)
    while i < length:
        m = re.search(r'\bSET\b', sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        set_pos = i + m.start()
        result.append(sql[i:set_pos])
        result.append('SET ')
        j = set_pos + len('SET')
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                up_remain = sql_up[j:]
                if (re.match(r'\bWHERE\b', up_remain) or
                        re.match(r'\bWHEN\b', up_remain) or
                        re.match(r'\bON\b', up_remain) or
                        re.match(r'\bFROM\b', up_remain)):
                    break
                if ch == ';':
                    break
            j += 1
        result.append('__SET__ ')
        i = j
    return ''.join(result)
def strip_insert_col_list(sql):
    pattern = re.compile(
        r'(INSERT\s+(?:OVERWRITE\s+)?(?:TABLE\s+)?[\w${}.\-]+)'
        r'(\s*\([^)]*\))'
        r'(\s*(?:WITH|SELECT|VALUES)\b)',
        re.IGNORECASE | re.DOTALL
    )
    return pattern.sub(r'\1 __INSERT_COLS__\3', sql)
def strip_function_args(sql):
    result = []
    i = 0
    length = len(sql)
    sql_up = sql.upper()
    SKIP_NAMES = {
        'FROM', 'JOIN', 'USING', 'WITH', 'ON', 'AS',
        'SELECT', 'WHERE', 'HAVING', 'SET',
        'INSERT', 'UPDATE', 'DELETE', 'MERGE',
        'CREATE', 'TABLE', 'VIEW', 'INTO',
        'WHEN', 'THEN', 'ELSE', 'AND', 'OR', 'NOT',
        'EXISTS', 'IN', 'ANY', 'ALL', 'CASE'
    }
    while i < length:
        m = re.search(r'(\b\w+)\s*\(', sql_up[i:])
        if not m:
            result.append(sql[i:])
            break
        fn_start = i + m.start()
        fn_name = m.group(1).upper()
        paren_start = i + m.end() - 1
        if fn_name in SKIP_NAMES:
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        if fn_start > 0 and sql[fn_start - 1] in ('.', '}', '$'):
            result.append(sql[i:paren_start + 1])
            i = paren_start + 1
            continue
        result.append(sql[i:fn_start + len(m.group(1))])
        inner, end_pos = extract_paren_content(sql, paren_start)
        result.append('(__FUNC_ARGS__)')
        i = end_pos + 1
    return ''.join(result)
# ============================================================
# 10. CTE 분석
# ============================================================
def extract_cte_map(query):
    cte_map = {}
    query = strip_inline_comments(query)
    if 'WITH' not in query.upper():
        return cte_map
    with_match = re.search(r'\bWITH\b', query, re.IGNORECASE)
    if not with_match:
        return cte_map
    pos = with_match.end()
    length = len(query)
    q_up = query.upper()
    DML_KEYWORDS = {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE'}
    while pos < length:
        while pos < length and query[pos] in ' \t\n\r':
            pos += 1
        if pos >= length:
            break
        alias_m = re.match(r'(\w+)', query[pos:])
        if not alias_m:
            break
        alias = alias_m.group(1)
        alias_up = alias.upper()
        if alias_up in DML_KEYWORDS:
            break
        pos += alias_m.end()
        while pos < length and query[pos] in ' \t\n\r':
            pos += 1
        if pos >= length:
            break
        as_m = re.match(r'\bAS\b', q_up[pos:], re.IGNORECASE)
        if not as_m:
            break
        pos += as_m.end()
        while pos < length and query[pos] in ' \t\n\r':
            pos += 1
        if pos >= length or query[pos] != '(':
            break
        inner, end_pos = extract_paren_content(query, pos)
        pos = end_pos + 1
        cte_map[alias_up] = extract_sources_recursive(inner)
        while pos < length and query[pos] in ' \t\n\r':
            pos += 1
        if pos >= length:
            break
        if query[pos] == ',':
            pos += 1
            continue
        break
    return cte_map
# ============================================================
# 11. SET 절 서브쿼리 소스 추출
# ============================================================
def _extract_sources_from_set_subqueries(sql):
    sources = set()
    sql_up = sql.upper()
    length = len(sql)
    for set_m in re.finditer(r'\bSET\b', sql_up):
        j = set_m.end()
        depth = 0
        while j < length:
            ch = sql[j]
            if ch == '(':
                depth += 1
                if depth == 1:
                    inner, end_pos = extract_paren_content(sql, j)
                    inner_up = inner.upper()
                    if (re.search(r'\bSELECT\b', inner_up) and
                            re.search(r'\bFROM\b', inner_up)):
                        sources.update(extract_sources_recursive(inner))
                    j = end_pos + 1
                    depth = 0
                    continue
                else:
                    j += 1
                    continue
            elif ch == ')':
                depth = max(depth - 1, 0)
            elif depth == 0:
                up_remain = sql_up[j:]
                if (re.match(r'\bWHERE\b', up_remain) or
                        re.match(r'\bFROM\b', up_remain) or
                        re.match(r'\bWHEN\b', up_remain) or
                        ch == ';'):
                    break
            j += 1
    return sources
# ============================================================
# 12. 소스 테이블 추출 (재귀, 인라인뷰 포함)
# ============================================================
def extract_sources_recursive(query):
    sources = set()
    query = strip_inline_comments(query)
    q = remove_string_literals(query)
    q = strip_select_columns(q)
    sources.update(_extract_sources_from_set_subqueries(q))
    q = strip_update_set(q)
    q = strip_insert_col_list(q)
    q = strip_function_args(q)
    length = len(q)
    kw_pattern = re.compile(r'\b(FROM|JOIN|USING)\b', re.IGNORECASE)
    CLAUSE_END = {
        'WHERE', 'ON', 'WHEN', 'SET', 'HAVING', 'GROUP', 'ORDER',
        'UNION', 'INTERSECT', 'EXCEPT', 'LIMIT', 'SELECT',
        'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'WITH',
        'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS',
        'JOIN', 'FROM', 'USING'
    }
    for kw_match in kw_pattern.finditer(q):
        j = kw_match.end()
        while j < length and q[j] in ' \t\n\r':
            j += 1
        if j >= length:
            continue
        if q[j] == '(':
            inner, end_pos = extract_paren_content(q, j)
            sources.update(extract_sources_recursive(inner))
            j = end_pos + 1
            alias_m = re.match(r'[\s]+(\w+)', q[j:])
            if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                j += alias_m.end()
            while j < length and q[j] in ' \t\n\r':
                j += 1
            if j >= length or q[j] != ',':
                continue
            j += 1
        while j < length:
            while j < length and q[j] in ' \t\n\r':
                j += 1
            if j >= length or q[j] in (';', ')'):
                break
            if q[j] == '(':
                inner, end_pos = extract_paren_content(q, j)
                sources.update(extract_sources_recursive(inner))
                j = end_pos + 1
                alias_m = re.match(r'[\s]+(\w+)', q[j:])
                if alias_m and alias_m.group(1).upper() not in CLAUSE_END:
                    j += alias_m.end()
            else:
                tok_m = re.match(r'([^\s,;()\n]+)', q[j:])
                if not tok_m:
                    break
                token = tok_m.group(1)
                token_up = token.upper().rstrip(',;')
                if token_up in CLAUSE_END:
                    break
                tbl = clean_table(token)
                if tbl:
                    sources.add(tbl)
                j += tok_m.end()
                alias_m = re.match(r'[\s]+([^\s,;()\n]+)', q[j:])
                if alias_m:
                    alias_word = alias_m.group(1).upper()
                    if alias_word not in CLAUSE_END and not alias_word.startswith(','):
                        j += alias_m.end()
            while j < length and q[j] in ' \t\n\r':
                j += 1
            if j < length and q[j] == ',':
                j += 1
            else:
                break
    return sources
# ============================================================
# 13. 타겟 테이블 추출
# ============================================================
# ============================================================
# ★★★ 핵심 수정 부분 ★★★
# extract_target_tables() 패턴 강화
# ============================================================
def extract_target_tables(query):
    targets = set()
    patterns = [
        # INSERT 관련 (기존)
        r'\bINSERT\s+OVERWRITE\s+TABLE\s+([^\s(]+)',
        r'\bINSERT\s+OVERWRITE\s+(?!TABLE\b)([^\s(]+)',
        r'\bINSERT\s+INTO\s+TABLE\s+([^\s(]+)',
        r'\bINSERT\s+INTO\s+(?!TABLE\b)([^\s(]+)',

        # CREATE 관련 (기존)
        r'\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:GLOBAL\s+)?(?:TEMPORARY\s+|TEMP\s+)?'
        r'(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)',

        # UPDATE, DELETE, MERGE, ALTER, TRUNCATE (기존)
        r'(?<![_\w])\bUPDATE\s+([^\s(]+)',
        r'\bDELETE\s+FROM\s+([^\s(]+)',
        r'\bMERGE\s+INTO\s+([^\s(]+)',
        r'\bMERGE\s+(?!INTO\b)([^\s(]+)',
        r'\bALTER\s+TABLE\s+([^\s(]+)',
        r'\bTRUNCATE\s+TABLE\s+([^\s(]+)',

        # ★ DROP TABLE 강화 (IF EXISTS 포함) ★
        r'\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([^\s;]+)',
        r'\bDROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?([^\s;]+)',   # VIEW도 혹시 모르니 추가
    ]

    POST_TABLE_KEYWORDS = {
        'PARTITION', 'CLUSTER', 'STORED', 'LOCATION', 'ROW', 'FORMAT',
        'FIELDS', 'LINES', 'TERMINATED', 'WITH', 'SELECT', 'AS', 'SET',
        'WHERE', 'VALUES', 'ON', 'USING', 'IF'
    }

    q_upper = query.upper()
    for pat in patterns:
        for match in re.finditer(pat, query, re.IGNORECASE):
            raw = match.group(1).strip().rstrip(';,')
            if not raw or raw.upper() in POST_TABLE_KEYWORDS:
                continue
            tbl = clean_table(raw)
            if tbl:
                targets.add(tbl)

    return targets
# ============================================================
# 14. TEMP 레지스트리 수집
# ============================================================
def build_temp_registry(source_dir):
    temp_set = set()
    for root, _, files in os.walk(source_dir):
        for file in files:
            if not file.lower().endswith(TARGET_EXTENSIONS):
                continue
            full_path = os.path.join(root, file)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
                content_pp = preprocess(raw)
                for m in TEMP_CREATE_PAT.finditer(content_pp):
                    name = clean_table(m.group(1))
                    if name:
                        temp_set.add(name.upper())
            except Exception:
                pass
    return temp_set
# ============================================================
# 15. 타입 판별
# ============================================================
def get_table_type(name, cte_names_upper, temp_registry_upper):
    if name is None:
        return ''
    nu = name.upper()
    if nu in cte_names_upper:
        return 'CTE'
    if nu in temp_registry_upper:
        return 'TEMP'
    return 'TABLE'
# ============================================================
# 16. CTE depth 계산
# ============================================================
def compute_cte_depths(cte_map):
    cte_names = set(cte_map.keys())
    depth_map = {}
    def get_depth(cte_name, visiting=None):
        if cte_name in depth_map:
            return depth_map[cte_name]
        if visiting is None:
            visiting = set()
        if cte_name in visiting:
            return 1
        visiting.add(cte_name)
        srcs = cte_map.get(cte_name, set())
        cte_deps = [s.upper() for s in srcs if s and s.upper() in cte_names]
        if not cte_deps:
            depth_map[cte_name] = 1
        else:
            depth_map[cte_name] = max(get_depth(d, visiting.copy()) for d in cte_deps) + 1
        return depth_map[cte_name]
    for cte_name in cte_map:
        get_depth(cte_name)
    return depth_map
# ============================================================
# 17. 출력 행 생성 (치환 함수로 변경)
# ============================================================
def build_rows(cte_map, sources_raw, targets, crud_type, sql_typ,
               base_directory, file_name, dir_file, mode,
               cte_names_upper, temp_registry):
    """
    행 구조 (인덱스 0~13):
      [0]base_directory [1]file_name [2]dir_file
      [3]crud_type [4]sql_typ
      [5]source_table [6]source_type
      [7]target_table [8]target_type
      [9]depth
      [10]src_schema [11]src_table
      [12]tgt_schema [13]tgt_table
    """
    rows = []
    seen = set()
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
        rows.append([
            base_directory, file_name, dir_file, crud_type, sql_typ,
            src, src_type,
            tgt, tgt_type,
            d,
            src_schema, src_table,
            tgt_schema, tgt_table
        ])
    # SIMPLE 행: 물리소스 -> 최종타겟 (depth=1)
    real_sources = set()
    for s in sources_raw:
        if s and s.upper() in cte_names_upper:
            real_sources.update(cte_map[s.upper()])
        elif s:
            real_sources.add(s)
    real_sources = {s for s in real_sources if s and s.upper() not in cte_names_upper}
    tgt_set = targets if targets else {None}
    src_set = real_sources if real_sources else {None}
    has_src = any(s is not None for s in src_set)
    for tgt in sorted(tgt_set, key=lambda x: x or ''):
        for src in sorted(src_set, key=lambda x: x or ''):
            if has_src and src is None:
                continue
            add_row(src, tgt, 1)
    # ── DETAIL 추가 행 ──────────────────────────────────────────────────
    if mode == "DETAIL" and cte_map and targets:
        # ② 모든 소스(물리테이블 + CTE 모두) → CTE명
        # depth = 해당 CTE의 의존 단계
        # 수정 핵심: 기존에는 물리소스만 출력했으나
        # CTE가 다른 CTE를 참조하는 경우(중간 가공 단계)도 포함
        # 예) cte_4 AS (SELECT FROM cte_1, cte_2, cte_3)
        # → cte_1→cte_4, cte_2→cte_4, cte_3→cte_4 (depth=2)
        for cte_name, cte_srcs in cte_map.items():
            cte_d = cte_depth_map.get(cte_name, 1)
            for src in sorted(cte_srcs, key=lambda x: x or ''):
                if not src:
                    continue
                # 물리테이블(TABLE/TEMP) → CTE 또는 CTE → CTE(중간가공) 모두 출력
                add_row(src, cte_name, cte_d)
        # ③ CTE명 → 최종타겟
        # depth = 해당 CTE의 의존 단계 + 1
        # (최종 SELECT/FROM 에서 직접 참조된 CTE 우선 사용)
        cte_refs = {s for s in sources_raw if s and s.upper() in cte_names_upper}
        if not cte_refs:
            cte_refs = set(cte_map.keys())
        for cte_name in sorted(cte_refs, key=lambda x: x or ''):
            cte_d = cte_depth_map.get(cte_name.upper(), 1)
            for tgt in sorted(targets, key=lambda x: x or ''):
                add_row(cte_name, tgt, cte_d + 1)
    return rows
# ============================================================
# 18. 메인 (CSV 기존 로직 유지 + MySQL DB 등록 추가)
# ============================================================
def main():
    total_files = 0
    total_queries = 0
    total_output_rows = 0
    total_file_lines = 0
    program_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    source_last_dir = os.path.basename(SOURCE_DIR.rstrip(os.sep))
    out_dir = os.path.join(os.getcwd(), "out")
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_suffix = MODE.lower()
    output_filename = f"{program_name}_{source_last_dir}_{mode_suffix}_{timestamp}.csv"
    output_path = os.path.join(out_dir, output_filename)
    # [추가] --db 옵션 시 mysql.conf 사전 확인
    mysql_conf = None
    if USE_DB:
        if _MYSQL_DRIVER is None:
            print("오류: MySQL 드라이버가 없습니다.")
            print(" pip install mysql-connector-python")
            print(" 또는 pip install pymysql")
            sys.exit(1)
        mysql_conf, err = load_mysql_conf(CONF_PATH)
        if err:
            print(f"오류: {err}")
            sys.exit(1)
        # mysql_conf 내용의 테이블
        # tbl_name = mysql_conf.get('table', 'sql_lineage')
        table_name = build_dynamic_table_name(SOURCE_DIR, MODE)
        print("------------------------------------")
        print(f"MySQL 드라이버 : {_MYSQL_DRIVER}")
        print(f"접속 호스트 : {mysql_conf.get('host')}:{mysql_conf.get('port', 3306)}")
        print(f"데이터베이스 : {mysql_conf.get('database')}")
        print(f"등록 테이블 : {table_name}")
        print("------------------------------------")
    # 분석 실행 (기존 로직 동일)
    temp_registry = build_temp_registry(SOURCE_DIR)
    rows_buffer = []

    # ===========================
    # [추가] EMRPUT 저장 리스트
    # ===========================
    emrput_rows = []

    for root, _, files in os.walk(SOURCE_DIR):
        for file_name in files:
            if not file_name.lower().endswith(('.sh', '.hql', '.sql', '.uld', '.ld')):
                continue
            total_files += 1
            dir_file = os.path.join(root, file_name)
            base_directory = os.path.abspath(root)
            # ===========================
            # [추가] EMRPUT 라인 수집
            # ===========================
            emr_lines = extract_emrput_lines(dir_file)
            for line in emr_lines:
                emrput_rows.append([
                    base_directory,
                    file_name,
                    dir_file,
                    line
                ])

            queries, file_lines = extract_queries_from_file(dir_file)
            total_file_lines += file_lines
            total_queries += len(queries)
            for query in queries:
                sql_typ = detect_real_sql_type(query)
                crud_type = classify_sql_type(sql_typ)
                cte_map = extract_cte_map(query)
                sources_raw = extract_sources_recursive(query)
                targets = extract_target_tables(query)
                cte_names_upper = set(cte_map.keys())
                if not sources_raw and not targets:
                    continue
                rows = build_rows(
                    cte_map, sources_raw, targets,
                    crud_type, sql_typ,
                    base_directory, file_name, dir_file,
                    MODE,
                    cte_names_upper,
                    temp_registry
                )
                rows_buffer.extend(rows)
                total_output_rows += len(rows)
    if total_output_rows == 0:
        print("====================================")
        print(f" SQL 소스/타겟 테이블 추출 완료 [{MODE}]")
        print("====================================")
        print("CSV 파일 생성 대상이 없습니다.")
        print("====================================")
        return
    # CSV 저장 (기존 로직 동일 - 항상 실행)
    with open(output_path, 'w', newline='', encoding='utf-8') as out_file:
        writer = csv.writer(out_file, delimiter=",")
        writer.writerow([
            "base_directory", "file_name", "dir_file",
            "crud_type", "sql_typ",
            "source_table", "source_type",
            "target_table", "target_type",
            "depth",
            "src_schema", "src_table",
            "tgt_schema", "tgt_table"
        ])
        writer.writerows(rows_buffer)

    # [추가] MySQL DB 등록 (--db 옵션 지정 시만 실행)
    db_inserted = 0
    db_err_msg = None
    if USE_DB and mysql_conf:
        db_inserted, db_err_msg = db_insert_all(rows_buffer, timestamp, mysql_conf, SOURCE_DIR, MODE)
    # 결과 출력 (기존 + DB 결과 추가)
    print("====================================")
    print(f" SQL 소스/타겟 테이블 추출 완료 [{MODE}]")
    print("====================================")
    print(f"실행 모드 : {MODE}")
    print(f"CSV 파일 위치 : {output_path}")
    print(f"처리 파일 건수 : {total_files}")
    print(f"추출 쿼리 건수 : {total_queries}")
    print(f"생성 행 건수 : {total_output_rows}")
    print(f"전체 파일 총 행 : {total_file_lines}")
    if USE_DB:
        print("------------------------------------")
        if db_err_msg:
            print(f"DB 등록 결과 : 실패")
            print(f"DB 오류 내용 : {db_err_msg}")
        else:
            # mysql_conf 내용의 테이블
            # tbl = mysql_conf.get('table', 'sql_lineage')
            table_name = build_dynamic_table_name(SOURCE_DIR, MODE)
            print(f"DB 등록 결과 : 성공")
            print(f"DB 등록 테이블 : {mysql_conf.get('database')}.{table_name}")
            print(f"DB 등록 건수 : {db_inserted}")
            print(f"DB run_id : {timestamp}")
    print("====================================")

    print(f"기존 CSV 생성 완료: {output_path}")

    # ===========================
    # [추가] EMRPUT CSV 생성
    # ===========================
    if emrput_rows:
        emr_output_path = os.path.join(
            out_dir,
            f"{program_name}_{source_last_dir}_emrput_{timestamp}.csv"
        )

        with open(emr_output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "base_directory",
                "file_name",
                "dir_file",
                "emrput_line"
            ])
            writer.writerows(emrput_rows)

        print("------------------------------------")
        print(f"EMRPUT 파일 생성 : {emr_output_path}")
        print(f"EMRPUT 건수 : {len(emrput_rows)}")

    print("====================================")
    print("처리 완료")
    print(f"파일 수 : {total_files}")
    print(f"쿼리 수 : {total_queries}")
    print("====================================")

if __name__ == "__main__":
    main()
