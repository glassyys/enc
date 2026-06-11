#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# sql_find_v001_01_local.py
#
# ■ 버전 이력
# ─────────────────────────────────────────────────────────────
# v001_local (2026-06-11)
#   1) CSV 파일을 Windows 디렉토리로 직접 지정 (절대경로 사용)
#   2) CSV 파일의 지정된 칼럼(search_column) 값을 파일명 리스트로 사용
#   3) 각 파일명을 검색대상_디렉토리 하위에서 검색
#   4) 검색 대상 확장자: .sql, .hql, .uld, .ld 만 처리
#   5) 결과 파일을 CSV 파일과 동일한 경로에 {CSV파일명}_out.csv 형식으로 저장
#   6) DB 테이블 생성 및 적재 부분 주석처리
#   7) 파일명: sql_find_v001_01_local.py
#
# v001_01 (기존)
#   - in 디렉토리에서 CSV 파일 읽음
#   - 검색 단어 개수만 표시
#   - 검색할 칼럼리스트 표시
#   - DB 직접 적재
# 
# 실행예시:
#   python3 sql_find_v001_01_local.py <검색대상_디렉토리> <CSV파일_절대경로> <search_column>
#
# 예시:
#   python3 sql_find_v001_01_local.py D:\source D:\data\target_files.csv search_column
#   python3 sql_find_v001_01_local.py /NAS/MIDP/SRC D:\data\key_list.csv search_column
#
# ■ 프로그램 설명
# ─────────────────────────────────────────────────────────────
# find 로컬버전 (sql_find_v001_01_local.py)
# 1) 실행시 검색대상 디렉토리, CSV 파일 절대경로, 칼럼명을 파라미터로 전달
# 2) CSV 파일을 Windows 디렉토리(절대경로)로 직접 지정
# 3) CSV 첫번째 행을 칼럼명으로 인식하고, 지정된 칼럼의 데이터를 파일명 리스트로 메모리 저장
# 4) 각 파일명을 검색대상 디렉토리 하위에서 찾기
# 5) 찾은 파일의 모든 소스 라인에서 검색 수행
# 6) 매칭 결과를 CSV 파일과 동일한 경로에 {CSV파일명}_out.csv 형식으로 저장
# 7) DB 테이블 생성 및 적재는 수행하지 않음 (주석처리)
# ===============================================================

import os
import sys
import csv
from datetime import datetime

# ============================================================
# 프로그램명 설정
# ============================================================
PROGRAM_NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]

# 대상 확장자 규칙 (기존 소스 기준)
TARGET_EXTENSIONS = {".sql", ".hql", ".uld", ".ld", ".sh"}

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
# CSV 파일로 결과 저장 함수
# ============================================================
def save_results_to_csv(rows_buffer: list, csv_path: str) -> str:
    """
    검색 결과를 CSV 파일로 저장
    파일명: {원본CSV파일명}_out.csv
    경로: 원본 CSV 파일과 동일한 디렉토리
    """
    # 원본 CSV 경로 기반으로 출력 파일명 생성
    csv_dir = os.path.dirname(csv_path)
    csv_basename = os.path.basename(csv_path)
    csv_name_without_ext = os.path.splitext(csv_basename)[0]
    csv_output_path = os.path.join(csv_dir, f"{csv_name_without_ext}_out.csv")
    
    try:
        with open(csv_output_path, "w", encoding="utf-8", newline="") as f:
            if not rows_buffer:
                # 빈 버퍼일 경우 헤더만 저장
                writer = csv.DictWriter(f, fieldnames=[
                    "base_directory", "file_name", "file_path",
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
# 인수 파싱
# ============================================================
def parse_args() -> tuple:
    args = sys.argv[1:]
    search_dir   = None
    csv_path     = None
    column_name  = None

    if len(args) < 3:
        print(f"사용법: python3 {PROGRAM_NAME}.py <검색대상_디렉토리> <CSV파일_절대경로> <search_column>")
        print("")
        print("예시:")
        print(f"  python3 {PROGRAM_NAME}.py D:\\source D:\\data\\target_files.csv search_column")
        print(f"  python3 {PROGRAM_NAME}.py /NAS/MIDP/SRC D:\\data\\key_list.csv search_column")
        sys.exit(1)

    search_dir = os.path.abspath(args[0])
    csv_path = os.path.abspath(args[1])
    column_name = args[2]

    # 유효성 검사
    if not os.path.isdir(search_dir):
        print(f"[오류] 유효한 검색 디렉토리가 아닙니다: {search_dir}")
        sys.exit(1)

    if not os.path.isfile(csv_path):
        print(f"[오류] 지정한 CSV 파일이 존재하지 않습니다: {csv_path}")
        sys.exit(1)

    return search_dir, csv_path, column_name

# ============================================================
# MAIN
# ============================================================
def main():
    search_dir, csv_path, column_name = parse_args()
    op_dtm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(" [로컬 소스 키워드 탐색 시작]")
    print("=" * 70)
    print(f"  검색 대상 디렉토리 : {search_dir}")
    print(f"  CSV 파일경로       : {csv_path}")
    print(f"  검색 기준 칼럼명   : {column_name}")
    print(f"  처리일시 (op_dtm)  : {op_dtm}")
    print(f"  실행 ID (run_id)   : {run_id}")
    print("-" * 70)

    # 1. CSV 파일을 읽어 검색 단어 추출
    print("[INFO] CSV 파일에서 검색 단어 추출 중...")

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
        print(f"  - {csv_path}: '{column_name}' 컬럼에서 {count_in_file:,}개 단어 추출 완료")
    except Exception as e:
        print(f"  - [ERROR] CSV 파일 읽기 실패: {e}")
        sys.exit(1)

    if not search_words:
        print(f"[ERROR] CSV 파일 내에서 '{column_name}' 컬럼 값을 찾지 못했거나 값이 모두 비어 있습니다.")
        sys.exit(1)

    print(f"[INFO] 메모리에 저장된 검색 단어 개수: {len(search_words):,} 개")
    print("[INFO] 검색할 단어 리스트:")
    for idx, word in enumerate(sorted(search_words), 1):
        print(f"       {idx:3d}. {word}")
    print("-" * 70)

    # 2. 검색대상 디렉토리에서 파일 찾기 및 매칭
    print("[INFO] 소스 파일 검색 및 매칭 시작...")
    match_buffer         = []
    total_files_found    = 0
    total_files_scanned  = 0
    total_lines_scanned  = 0
    total_lines_skipped  = 0  # 주석 라인 스킵 카운트

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

                        # 검색 단어가 라인에 있는지 확인 (대소문자 구분)
                        for search_word in search_words:
                            if search_word in line_without_comments:
                                total_files_found += 1
                                match_buffer.append({
                                    "base_directory": base_dir,
                                    "file_name": file,
                                    "file_path": full_path,
                                    "line_no": line_no,
                                    "line_content": line_without_comments,
                                    "search_column": column_name,
                                    "matched_word": search_word,
                                })
                                break  # 이 라인에서 매칭된 단어 저장 후 다음 라인으로

            except Exception as e:
                print(f"  - [WARN] 소스 파일 읽기 실패: {full_path} ({e})")

    print("[INFO] 소스 탐색 완료:")
    print(f"  - 스캔한 파일 개수  : {total_files_scanned:,} 개")
    print(f"  - 스캔한 총 라인 수 : {total_lines_scanned:,} 줄")
    print(f"  - 스킵된 주석 라인  : {total_lines_skipped:,} 줄")
    print(f"  - 매칭 발견 건수    : {len(match_buffer):,} 건")
    print("-" * 70)

    # 3. 결과를 CSV 파일로 저장
    print("[INFO] 검색 결과를 CSV 파일로 저장 중...")
    try:
        csv_output_path = save_results_to_csv(match_buffer, csv_path)
        print(f"  - CSV 파일 저장 완료: {csv_output_path}")
        print(f"  - 저장된 레코드 수  : {len(match_buffer):,} 건")
    except Exception as e:
        print(f"  - [ERROR] CSV 저장 실패: {e}")
        sys.exit(1)

    print("-" * 70)

    # [주석처리: DB 테이블 생성 및 적재 부분]
    # print("[INFO] MySQL 테이블에 매칭 데이터 적재 시작...")
    # try:
    #     inserted_cnt = db_insert_matches(match_buffer, run_id, op_dtm, mysql_conf, search_dir)
    # except Exception as e:
    #     print("=" * 70)
    #     print(" 소스 키워드 탐색 적재 실패")
    #     print("=" * 70)
    #     print(f"  DB 오류 내용       : {e}")
    #     sys.exit(1)

    print("=" * 70)
    print(" 로컬 소스 키워드 탐색 성공 완료")
    print("=" * 70)
    print(f"  검색 결과 파일     : {csv_output_path}")
    print(f"  스캔한 파일 개수   : {total_files_scanned:,} 개")
    print(f"  총 매칭 건수       : {len(match_buffer):,} 건")
    print(f"  run_id (실행 ID)   : {run_id}")
    print("=" * 70)


if __name__ == "__main__":
    main()
