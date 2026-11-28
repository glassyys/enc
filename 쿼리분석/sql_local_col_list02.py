#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===============================================================
# sql_local_col_list02.py (2026-11-28 수정 완료)
#
# [목적]
#   파라미터 파일(--in)의 '한 줄에 단어 하나' 목록 (또는 --col 직접 입력)이
#   <검색디렉토리> 하위 소스(.uld .ld .sh .sql .hql)에 존재하는지 조회한다.
#   --db 를 지정하면 조회 결과를 <검색결과테이블명> 에 등록(mid 단위 DELETE 후 INSERT)한다.
#
# [수정 사항 요약 및 이력]
#   - 2026-11-28 (최초 작성): sql_v12_full_new_02_local_col.py 로직 검증 후 sql_local_cal_list01.py 로 신규 작성
#     * 원본의 is_pure_column(단순 컬럼 라인 제외)/diff_cols(비교 컬럼) 로직을 제거하고
#       '단어 존재 조회' 로 목적 단일화 (SELECT col, WHERE col='1' 같은 평범한 사용 라인 누락 해소).
#     * 파라미터 파일 BOM(utf-8-sig) 처리 및 cp949 fallback (원본은 BOM 때문에 첫 단어 매칭 불가).
#     * 주석 제거 시 문자열 리터럴 보호 (문자열 안의 '#', '--' 를 주석으로 오인하던 문제 해소).
#     * 소스 전체 라인 단위 직접 스캔 (세미콜론 없는 쿼리/쉘 라인 누락 및 인접 쿼리 오귀속 해소).
#     * Python 2.7 SyntaxError 제거 (print(..., file=sys.stderr) -> from __future__ import print_function).
#     * DB 적재 보정: 매칭 0건이어도 해당 mid DELETE, 실패 시 테이블 DROP & CREATE 로직 제거.
#     * 단어별 건수 및 미발견 단어 요약 추가.
#   - 2026-11-28 (list02 1차 수정): 파라미터 파일 형식 변경 (쉼표 구분 -> 여러 행)
#     * --in 파일을 쉼표(,) 로 분리하지 않고 '한 줄 = 한 단어' 로 읽도록 변경.
#       (한 줄 전체가 하나의 단어이며, 줄 안의 쉼표는 구분자로 취급하지 않음)
#     * 빈 줄 및 '#' 으로 시작하는 줄은 무시, 줄 앞뒤 공백/따옴표 제거, 대소문자 무시 중복 단어는 1회만 검색.
#     * --col 옵션(명령행 직접 입력)은 기존대로 쉼표(,) 구분 유지.
#     * 파일명을 sql_local_col_list02.py 로 변경, 도움말/실행 예시 갱신.
#   - 2026-11-28 (list02 2차 수정): grep 형식 라인 출력 추가
#     * 매칭된 라인을 단어별로 grep -n 형식('파일경로:라인번호:내용')으로 화면에 출력하는 [GREP 출력] 구간 추가.
#     * 동일 내용을 out/p190872_<테이블>_<mid>_grep.txt 파일로 저장 (기존 파일은 타임스탬프 백업).
#     * 매칭이 없는 단어도 '(0 건)' 으로 표시하여 grep 결과 없음을 확인 가능.
#     * 화면 출력 파일(_print.txt)에도 [GREP 출력] 내용 포함.
#
# [파라미터 파일 형식 예시] (한 줄에 단어 하나)
#   aa
#   bbb
#   cust_no
#
# [실행 예시]
#   python sql_local_col_list02.py D:\workspace\src my_db.my_result --in param.txt
#   python sql_local_col_list02.py D:\workspace\src my_db.my_result --col col1,col2 --mid abc,def
#   python sql_local_col_list02.py D:\workspace\src my_db.my_result --in param.txt --db --conf D:\workspace\mysql.conf
#
# [옵션]
#   --in FILE      단어 목록 파일 (한 줄에 단어 하나, '#' 로 시작하는 줄은 무시)
#   --col a,b,c    단어 직접 입력 (쉼표 구분, --in 과 함께 지정 시 합쳐서 사용)
#   --mid m1,m2    검색디렉토리 하위 MID 디렉토리 (미지정 시 전체를 'all' 로 처리)
#   --db           결과를 DB 테이블에 적재
#   --conf FILE    mysql.conf 경로 (기본: 현재 디렉토리 -> 스크립트 디렉토리)
#   --incl-comment 주석 영역도 검색 대상에 포함 (기본: 주석 제외)
#   --ignore-case-off  대소문자 구분 검색 (기본: 대소문자 무시)
# ===============================================================
from __future__ import print_function

import os
import re
import sys
import csv
import shutil
import codecs
import argparse
from datetime import datetime

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

PY2 = sys.version_info[0] < 3
if PY2:
    text_type = unicode  # noqa: F821
else:
    text_type = str

OUT_PREFIX = "p190872_"          # 결과 파일명 접두사 (원본과 동일)
ALLOWED_EXTS = (".uld", ".ld", ".sh", ".sql", ".hql")

CSV_FIELDNAMES = [
    "mid", "column_name", "source_file", "line_number",
    "matched_line", "vscode_open_cmd", "op_dtm"
]


# ============================================================
# 출력 유틸 (Python2 에서 유니코드 출력 오류 방지)
# ============================================================
def out(msg=""):
    if PY2 and isinstance(msg, text_type):
        msg = msg.encode("utf-8")
    print(msg)


def to_text(v):
    if v is None:
        return u""
    if PY2:
        if isinstance(v, str):
            return v.decode("utf-8", "ignore")
        return text_type(v)
    return str(v)


# ============================================================
# MySQL 드라이버 / 설정
# ============================================================
_MYSQL_DRIVER = None
try:
    import mysql.connector  # noqa: F401
    _MYSQL_DRIVER = "connector"
except ImportError:
    try:
        import pymysql  # noqa: F401
        _MYSQL_DRIVER = "pymysql"
    except ImportError:
        _MYSQL_DRIVER = None


def mysql_connect(conf):
    kw = dict(host=conf.get("host", "localhost"), port=int(conf.get("port", 3306)),
              user=conf.get("user", ""), password=conf.get("password", ""),
              database=conf.get("database", ""), charset=conf.get("charset", "utf8mb4"))
    if _MYSQL_DRIVER == "connector":
        import mysql.connector
        return mysql.connector.connect(**kw)
    if _MYSQL_DRIVER == "pymysql":
        import pymysql
        return pymysql.connect(autocommit=False, **kw)
    raise ImportError("MySQL 드라이버가 없습니다. pip install pymysql 또는 mysql-connector-python")


def load_mysql_conf(explicit_path=None):
    path = os.path.abspath(explicit_path if explicit_path else os.path.join(os.getcwd(), "mysql.conf"))
    if not os.path.isfile(path):
        fallback = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "mysql.conf")
        if os.path.isfile(fallback):
            path = fallback
        else:
            return None, "mysql.conf 파일을 찾을 수 없습니다: %s" % path
    cp = configparser.ConfigParser()
    try:
        with codecs.open(path, "r", encoding="utf-8-sig") as f:
            if hasattr(cp, "read_file"):
                cp.read_file(f)
            else:
                cp.readfp(f)
    except Exception as e:
        return None, "mysql.conf 읽기 오류: %s" % str(e)
    if not cp.has_section("mysql"):
        return None, "mysql.conf 에 [mysql] 섹션이 없습니다."
    conf = dict((o, cp.get("mysql", o)) for o in cp.options("mysql"))
    missing = [k for k in ("host", "user", "password", "database") if not conf.get(k)]
    if missing:
        return None, "mysql.conf 필수 항목 누락: %s" % ", ".join(missing)
    return conf, None


def split_schema_table(full_table):
    parts = full_table.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", parts[0].strip()


def make_fq(schema, table):
    return "`%s`.`%s`" % (schema, table) if schema else "`%s`" % table


# ============================================================
# 파일 읽기 (BOM / utf-8 / cp949 순차 시도)
# ============================================================
def read_text_file(path):
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "ignore")


# ============================================================
# 단어 목록 수집
# ============================================================
def collect_words(col_arg, in_arg):
    words = []
    if in_arg:
        fp = in_arg.strip().replace("\\", os.sep).replace("/", os.sep)
        cands = [os.path.abspath(fp)]
        if not os.path.dirname(fp):
            cands.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), fp))
        found = None
        for c in cands:
            if os.path.isfile(c):
                found = c
                break
        if not found:
            return None, "파라미터 파일을 찾을 수 없습니다: %s" % cands[0]
        try:
            txt = read_text_file(found)
        except Exception as e:
            return None, "파라미터 파일 읽기 실패: %s" % str(e)
        for line in txt.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # 한 줄 = 한 단어 (쉼표로 분리하지 않음)
            w = s.strip("'\"").strip()
            if w:
                words.append(w)
    if col_arg:
        txt = col_arg
        if PY2 and not isinstance(col_arg, text_type):
            try:
                txt = col_arg.decode("utf-8")
            except UnicodeDecodeError:
                txt = col_arg.decode("cp949", "ignore")
        for w in txt.split(","):
            w = w.strip().strip("'\"").strip()
            if w:
                words.append(w)

    uniq, seen = [], set()
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    return uniq, None


def build_word_regex(word, ignore_case=True):
    flags = re.IGNORECASE if ignore_case else 0
    # 단어 앞뒤가 영문/숫자/_ 로 이어지지 않을 때만 매칭 (cust_no 는 cust_no2 에 매칭되지 않음)
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(word) + r"(?![A-Za-z0-9_])", flags)


# ============================================================
# 주석 마스킹 (길이/줄바꿈 보존, 문자열 리터럴 보존)
# ============================================================
_COMMENT_RX = re.compile(
    r"('(?:[^']|'')*')|"
    r'("(?:[^"]|"")*")|'
    r"(--[^\n]*)|"
    r"(/\*.*?\*/)|"
    r"((?<=\s)#[^\n]*)",
    re.DOTALL
)


def mask_comments(raw):
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        st = line.lstrip()
        if st.startswith("#") or re.match(r"(?i)^\s*DBMS_OUTPUT", line):
            lines[i] = " " * len(line)
    content = "\n".join(lines)

    def repl(m):
        if m.group(1) or m.group(2):
            return m.group(0)
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))

    return _COMMENT_RX.sub(repl, content)


# ============================================================
# 쿼리 블록 위치 (DB 의 query_text 용, 못 찾으면 빈 값)
# ============================================================
_QUERY_START = re.compile(
    r"\b(CREATE\s+OR\s+REPLACE|CREATE|ALTER\s+(?:TABLE|VIEW)|DROP\s+(?:TABLE|VIEW)|TRUNCATE\s+TABLE|"
    r"MERGE|UPSERT|INSERT|UPDATE|DELETE|SELECT|WITH)\b", re.IGNORECASE)


def find_query_ranges(raw, masked):
    """[(start_line, end_line, query_text)] 1-based, 세미콜론으로 끝나는 쿼리 블록."""
    ranges = []
    length = len(masked)
    pos = 0
    while pos < length:
        m = _QUERY_START.search(masked, pos)
        if not m:
            break
        start = m.start()
        end, depth, in_str, qc = start, 0, False, None
        closed = False
        while end < length:
            ch = masked[end]
            if ch in ("'", '"'):
                if not in_str:
                    in_str, qc = True, ch
                elif qc == ch:
                    in_str = False
            elif not in_str:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(depth - 1, 0)
                elif ch == ";" and depth == 0:
                    end += 1
                    closed = True
                    break
            end += 1
        if closed:
            s_line = masked.count("\n", 0, start) + 1
            e_line = masked.count("\n", 0, end) + 1
            ranges.append((s_line, e_line, raw[start:end].strip()))
            pos = end
        else:
            pos = m.end()
    return ranges


# ============================================================
# 소스 파일 목록
# ============================================================
def is_binary_file(path):
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(1024)
    except Exception:
        return True


def walk_sources(base):
    files = []
    if os.path.isdir(base):
        for root, _, names in os.walk(base):
            for n in sorted(names):
                if os.path.splitext(n)[1].lower() in ALLOWED_EXTS:
                    p = os.path.join(root, n)
                    if not is_binary_file(p):
                        files.append(p)
    return sorted(files)


def get_source_files(search_dir, mids=None):
    search_dir = os.path.abspath(search_dir)
    result = {}
    if not mids:
        result["all"] = walk_sources(search_dir)
    else:
        for mid in mids:
            mid_dir = os.path.join(search_dir, mid)
            if not os.path.isdir(mid_dir):
                out("[WARN] 디렉토리가 존재하지 않습니다: %s" % mid_dir)
            result[mid] = walk_sources(mid_dir)
    return result


# ============================================================
# 핵심: 한 파일에서 단어 조회
# ============================================================
def search_file(filepath, word_rx, any_rx, incl_comment):
    """[(word, line_no, matched_line, query_text)] 반환"""
    try:
        raw = read_text_file(filepath)
    except Exception as e:
        out("[WARN] 파일 읽기 실패: %s (%s)" % (filepath, str(e)))
        return []

    masked = raw if incl_comment else mask_comments(raw)
    if not any_rx.search(masked):
        return []

    orig_lines = raw.splitlines()
    mask_lines = masked.splitlines() if incl_comment else masked.split("\n")
    if len(mask_lines) != len(orig_lines):      # 방어: 줄 수 불일치 시 마스킹 없이 원문 사용
        mask_lines = orig_lines

    ranges = None
    hits = []
    for idx, mline in enumerate(mask_lines):
        if not mline.strip() or not any_rx.search(mline):
            continue
        for word, rx in word_rx:
            if rx.search(mline):
                if ranges is None:
                    ranges = find_query_ranges(raw, masked if not incl_comment else mask_comments(raw))
                l_no = idx + 1
                qtxt = u""
                for s, e, q in ranges:
                    if s <= l_no <= e:
                        qtxt = q
                        break
                hits.append((word, l_no, orig_lines[idx].strip(), qtxt))
    return hits


# ============================================================
# 파일 저장 / 백업
# ============================================================
def backup_existing_file(filepath):
    if not os.path.isfile(filepath):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(os.path.basename(filepath))
    bak = os.path.join(os.path.dirname(filepath), "%s_%s%s" % (name, ts, ext))
    try:
        shutil.copy2(filepath, bak)
        out("[BACKUP] %s -> %s" % (filepath, bak))
    except Exception as e:
        out("[WARNING] 백업 실패: %s (%s)" % (filepath, str(e)))


def save_csv(rows, filepath, op_dtm):
    d = os.path.dirname(filepath)
    if not os.path.exists(d):
        os.makedirs(d)
    if PY2:
        f = open(filepath, "wb")
        f.write(codecs.BOM_UTF8)
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {}
            for k in CSV_FIELDNAMES:
                v = op_dtm if k == "op_dtm" else r.get(k)
                v = u"" if v is None else (v if isinstance(v, text_type) else text_type(v))
                row[k] = v.encode("utf-8")
            w.writerow(row)
        f.close()
    else:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                row = dict(r)
                row["op_dtm"] = op_dtm
                w.writerow(row)


# ============================================================
# DB 적재 (mid 단위 DELETE 후 INSERT, 테이블 DROP 하지 않음)
# ============================================================
_DDL_RESULT = """
CREATE TABLE IF NOT EXISTS {table} (
  `id`               BIGINT        NOT NULL AUTO_INCREMENT  COMMENT '자동증가 PK',
  `mid`              VARCHAR(100)  NOT NULL                 COMMENT '검색 MID',
  `column_name`      VARCHAR(500)  NULL,
  `source_file`      VARCHAR(500)  NULL,
  `line_number`      INT           NULL,
  `matched_line`     TEXT          NULL,
  `vscode_open_cmd`  VARCHAR(1000) NULL,
  `query_text`       LONGTEXT      NULL,
  `op_dtm`           DATETIME      NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_mid`       (`mid`),
  KEY `idx_col_name`  (`column_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='소스 단어 조회 결과';
"""

_SQL_INSERT = """
INSERT INTO {table}
  (mid, column_name, source_file, line_number, matched_line, vscode_open_cmd, query_text, op_dtm)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def db_load(mysql_conf, fq_table, rows, mid, op_dtm):
    batch = [(mid, r["column_name"], r["source_file"], r["line_number"], r["matched_line"],
              r["vscode_open_cmd"], r["query_text"], op_dtm) for r in rows]
    conn, cur = None, None
    try:
        conn = mysql_connect(mysql_conf)
        cur = conn.cursor()
        cur.execute(_DDL_RESULT.format(table=fq_table))
        conn.commit()
        cur.execute("DELETE FROM %s WHERE `mid` = %%s" % fq_table, (mid,))
        step = 1000
        for i in range(0, len(batch), step):
            cur.executemany(_SQL_INSERT.format(table=fq_table), batch[i:i + step])
        conn.commit()
        out("[INFO] DB 적재 완료: %s (mid=%s, %d 건)" % (fq_table, mid, len(batch)))
        return len(batch), None
    except Exception as e:
        out("[ERROR] DB 적재 실패: %s" % str(e))
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return 0, str(e)
    finally:
        for o in (cur, conn):
            if o:
                try:
                    o.close()
                except Exception:
                    pass


# ============================================================
# MAIN
# ============================================================
def main():
    start_time = datetime.now()
    ap = argparse.ArgumentParser(description="소스 단어 조회 스크립트 (파라미터 파일: 한 줄 = 한 단어)")
    ap.add_argument("search_dir", help="검색디렉토리")
    ap.add_argument("out_table", help="검색결과테이블명 (schema.table)")
    ap.add_argument("--in", dest="in_file", default=None, help="단어 목록 파라미터 파일 (한 줄에 단어 하나)")
    ap.add_argument("--col", default=None, help="쉼표(,) 구분 단어 목록 (명령행 직접 입력)")
    ap.add_argument("--mid", default=None, help="검색디렉토리 하위 MID (쉼표 구분)")
    ap.add_argument("--db", action="store_true", help="DB 적재")
    ap.add_argument("--conf", default=None, help="mysql.conf 경로")
    ap.add_argument("--incl-comment", action="store_true", help="주석 영역도 검색")
    ap.add_argument("--ignore-case-off", action="store_true", help="대소문자 구분 검색")
    args = ap.parse_args()

    if not args.in_file and not args.col:
        out("[ERROR] --in 또는 --col 중 하나는 반드시 지정해야 합니다.")
        sys.exit(1)
    if not os.path.isdir(args.search_dir):
        out("[ERROR] 검색디렉토리가 존재하지 않습니다: %s" % args.search_dir)
        sys.exit(1)

    words, err = collect_words(args.col, args.in_file)
    if err:
        out("[ERROR] %s" % err)
        sys.exit(1)
    if not words:
        out("[ERROR] 검색 대상 단어가 비어 있습니다.")
        sys.exit(1)

    out("=" * 80)
    out("[INFO] 검색 단어 %d 개: %s" % (len(words), ", ".join(words)))

    mysql_conf = {}
    if args.db:
        if _MYSQL_DRIVER is None:
            out("[ERROR] MySQL 드라이버가 없습니다.")
            sys.exit(1)
        mysql_conf, err = load_mysql_conf(args.conf)
        if err:
            out("[ERROR] %s" % err)
            sys.exit(1)

    ignore_case = not args.ignore_case_off
    word_rx = [(w, build_word_regex(w, ignore_case)) for w in words]
    any_rx = re.compile(
        "|".join("(?<![A-Za-z0-9_])" + re.escape(w) + "(?![A-Za-z0-9_])" for w in
                 sorted(words, key=len, reverse=True)),
        re.IGNORECASE if ignore_case else 0)

    op_dtm = start_time.strftime("%Y-%m-%d %H:%M:%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "out")
    out_schema, out_tbl_only = split_schema_table(args.out_table)
    fq_out_table = make_fq(out_schema, out_tbl_only)

    mids = [m.strip() for m in args.mid.split(",") if m.strip()] if args.mid else None
    src_by_mid = get_source_files(args.search_dir, mids)

    out("  검색 디렉토리 : %s" % args.search_dir)
    out("  결과 테이블   : %s" % args.out_table)
    out("  MID           : %s" % (args.mid if args.mid else "(미지정 -> all)"))
    out("  DB 적재       : %s" % ("YES" if args.db else "NO"))
    out("  주석 검색     : %s" % ("포함" if args.incl_comment else "제외"))
    out("=" * 80)

    for mid, files in src_by_mid.items():
        results = []
        files_with_hit = set()
        per_word = dict((w, {"lines": 0, "files": set()}) for w in words)
        seen = set()

        for fp in files:
            for word, l_no, mline, qtxt in search_file(fp, word_rx, any_rx, args.incl_comment):
                key = (fp, l_no, word.lower())
                if key in seen:
                    continue
                seen.add(key)
                afp = os.path.abspath(fp)
                results.append({
                    "mid": mid, "column_name": word, "source_file": afp,
                    "line_number": l_no, "matched_line": mline,
                    "vscode_open_cmd": "code -g %s:%s" % (afp, l_no),
                    "query_text": qtxt
                })
                files_with_hit.add(fp)
                per_word[word]["lines"] += 1
                per_word[word]["files"].add(fp)

        buf = ["-" * 80, "-- 검색MID : %s" % mid, "-" * 80]
        for r in results:
            buf.append("[매칭] %s %s" % (r["vscode_open_cmd"], r["column_name"]))
            buf.append("[내용] %s" % r["matched_line"])
            buf.append("-" * 80)

        # grep -n 형식 출력: 단어별 '파일경로:라인번호:내용'
        grep_buf = ["=" * 80, " [GREP 출력 - MID: %s]  (형식: 파일경로:라인번호:내용)" % mid, "=" * 80]
        for w in words:
            w_rows = [r for r in results if r["column_name"] == w]
            grep_buf.append("### %s (%d 건)" % (w, len(w_rows)))
            for r in w_rows:
                grep_buf.append("%s:%s:%s" % (r["source_file"], r["line_number"], r["matched_line"]))
            grep_buf.append("")

        summ = ["=" * 80, " [조회 요약 - MID: %s]" % mid, "=" * 80,
                "  - 검색 대상 소스 파일 수 : %d 개" % len(files),
                "  - 매칭 발생 소스 파일 수 : %d 개" % len(files_with_hit),
                "  - 매칭 건수              : %d 건" % len(results),
                "-" * 80, "  [단어별 현황]"]
        not_found = []
        for w in words:
            c = per_word[w]
            if c["lines"]:
                summ.append("   %-30s : %d 건 / %d 개 파일" % (w, c["lines"], len(c["files"])))
            else:
                not_found.append(w)
        summ.append("  [미발견 단어 %d 개] %s" % (len(not_found), ", ".join(not_found) if not_found else "(없음)"))
        summ.append("=" * 80)

        for line in buf + grep_buf + summ:
            out(line)

        csv_path = os.path.abspath(os.path.join(out_dir, "%s%s_%s.csv" % (OUT_PREFIX, out_tbl_only, mid)))
        prt_path = os.path.abspath(os.path.join(out_dir, "%s%s_%s_print.txt" % (OUT_PREFIX, out_tbl_only, mid)))
        backup_existing_file(csv_path)
        save_csv(results, csv_path, op_dtm)
        backup_existing_file(prt_path)
        with codecs.open(prt_path, "w", encoding="utf-8") as pf:
            pf.write(u"\n".join(to_text(x) for x in buf + grep_buf + summ) + u"\n")
        grep_path = os.path.abspath(os.path.join(out_dir, "%s%s_%s_grep.txt" % (OUT_PREFIX, out_tbl_only, mid)))
        backup_existing_file(grep_path)
        with codecs.open(grep_path, "w", encoding="utf-8") as gf:
            gf.write(u"\n".join(to_text(x) for x in grep_buf) + u"\n")
        out("[INFO] 파일 저장: %s (%d 건)" % (csv_path, len(results)))
        out("[INFO] 파일 저장: %s" % prt_path)
        out("[INFO] 파일 저장: %s" % grep_path)

        if args.db:
            db_load(mysql_conf, fq_out_table, results, mid, op_dtm)

    elapsed = datetime.now() - start_time
    out("[완료] 시작 %s / 소요 %s" % (op_dtm, str(elapsed)))


if __name__ == "__main__":
    main()
