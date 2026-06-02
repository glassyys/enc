# -*- coding: utf-8 -*-
# ==========================================================================
# [프로그램 개요]
# 本 프로그램(query_validator_v03.py)은 텍스트 파일에 저장된 SQL 쿼리문들을 
# 한 줄씩 읽어와서 괄호 및 따옴표의 문법적 쌍(Pair)이 올바르게 일치하는지 
# 검증하는 유틸리티입니다.
# 
# [주요 검증 조건]
# 1. 괄호 쌍 체크: 소괄호 '()', 중괄호 '{}', 대괄호 '[]'가 올바른 순서와 쌍으로 닫혔는지 검사합니다.
# 2. 따옴표 쌍 체크: 싱글 휫따옴표("'"), 더블 쌍따옴표('"'), 백틱('`')이 정상적으로 닫혔는지 검사합니다.
#    - 따옴표 내부(문자열 리터럴)에 존재하는 괄호나 다른 따옴표는 문법 오류로 인식하지 않도록 예외 처리됩니다.
#    - 따옴표 내부의 이스케이프 문자(\, \') 처리 기능을 포함합니다.
# 
# [실행 방법 및 파라미터]
# >> python3 query_validator_v03.py [검증할_쿼리_파일경로] [결과가_저장될_디렉토리경로]
#    - 파라미터 1: 검증 대상인 쿼리 텍스트 파일의 경로
#    - 파라미터 2: 결과 로그(.log) 및 결과 데이터(.csv)가 생성될 디렉토리(폴더) 경로
# 
# [실행 예시]
# 1. 검증 대상 파일 준비 (예: ./sample_data/queries.txt)
#    --- 파일 내용 예시 ---
#    SELECT * FROM users WHERE id = 1 AND name = '홍길동';
#    SELECT * FROM table WHERE id = (1 + 2;
#    ---------------------
# 2. 명령어 실행 (./outputs 디렉토리에 결과를 저장하고 싶은 경우 - python3 사용)
#    >> python3 query_validator_v03.py ./sample_data/queries.txt ./outputs
# 3. 실행 결과
#    - 지정된 ./outputs 디렉토리 내에 2개의 파일이 자동으로 생성됩니다.
#      1) [queries.txt.log] : 전체 작업 내용과 요약 정보가 담긴 일반 텍스트 로그 파일
#      2) [queries.txt.csv] : 라인별 검증 정보(쿼리내용, 성공여부, 오류내용, 오류기호, 오류위치)가 담긴 스프레드시트 연동용 CSV 파일
# ==========================================================================

import sys
import os
import csv

def validate_query(query: str) -> dict:
    """
    단일 쿼리문장의 괄호 및 따옴표 쌍이 일치하는지 스택(Stack) 구조를 활용해 검증합니다.
    결과는 CSV 저장을 위해 상세 정보가 담긴 딕셔너리로 반환합니다.
    """
    stack = []
    # 닫는 괄호에 대응하는 여는 괄호 매핑 및 각 괄호의 짝 정의
    bracket_map = {')': '(', '}': '{', ']': '['}
    quote_chars = {'"', "'", "`"}
    
    in_quote = None  # 현재 열려 있는 따옴표 종류 기록
    escaped = False  # 직전 문자가 백슬래시(\)였는지 여부
    
    result_data = {
        "is_valid": True,
        "message": "정상",
        "error_char": "",
        "error_pos": ""
    }
    
    for i, char in enumerate(query):
        # 1. 이스케이프 문자 처리 (\ 다음 문자는 문법 검사 패스)
        if escaped:
            escaped = False
            continue
            
        if char == '\\':
            if in_quote:
                escaped = True
            continue
            
        # 2. 따옴표 내부 상태인 경우 처리
        if in_quote:
            if char == in_quote:
                in_quote = None  # 열린 따옴표와 일치하는 문자를 만나면 닫힘 처리
            continue  # 따옴표 내부의 괄호 등은 검사하지 않고 스킵
            
        # 3. 따옴표 외부 상태인 경우 처리
        else:
            if char in quote_chars:
                in_quote = char  # 따옴표 시작
                continue
            elif char in bracket_map.values():
                stack.append((char, i))  # 여는 괄호와 해당 위치를 스택에 삽입
            elif char in bracket_map.keys():
                # 닫는 괄호를 만났을 때 스택이 비어있거나 짝이 맞지 않으면 실패
                if not stack or stack[-1][0] != bracket_map[char]:
                    result_data["is_valid"] = False
                    result_data["message"] = "짝이 맞지 않는 닫는 괄호가 발견되었습니다."
                    result_data["error_char"] = char
                    result_data["error_pos"] = str(i + 1) # 1부터 시작하는 순서로 표기
                    return result_data
                stack.pop()

    # 최종 상태 결과 확인
    if in_quote:
        result_data["is_valid"] = False
        result_data["message"] = "닫히지 않은 따옴표가 존재합니다."
        result_data["error_char"] = in_quote
        result_data["error_pos"] = "문자열 끝"
        return result_data
        
    if stack:
        # 가장 마지막에 닫히지 않고 남아있는 여는 괄호 정보 추출
        last_char, last_pos = stack[-1]
        result_data["is_valid"] = False
        result_data["message"] = "닫히지 않은 여는 괄호가 남아있습니다."
        result_data["error_char"] = last_char
        result_data["error_pos"] = str(last_pos + 1)
        return result_data
        
    return result_data


def check_query_process(file_path: str, output_dir: str):
    """
    쿼리 파일을 읽어 검증한 후, 사용자가 지정한 디렉토리 안에 [파일명.log] 및 [파일명.csv] 파일을 생성합니다.
    """
    # 1. 입력 파일 존재 여부 확인
    if not os.path.exists(file_path):
        print(f"[오류] 검증 대상 파일 '{file_path}'을(를) 찾을 수 없습니다.")
        return

    # 2. 결과 저장할 디렉토리 존재 여부 확인 및 생성 (없으면 자동 생성)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"[알림] 존재하지 않는 출력 디렉토리를 생성했습니다: {output_dir}")
        except Exception as e:
            print(f"[오류] 출력 디렉토리 생성 실패: {e}")
            return

    # 3. 출력 파일명 정의 ([입력파일명].log 및 [입력파일명].csv)
    input_filename = os.path.basename(file_path)
    log_filepath = os.path.join(output_dir, f"{input_filename}.log")
    csv_filepath = os.path.join(output_dir, f"{input_filename}.csv")

    # 4. 쿼리 파일 읽기
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[오류] 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    # 5. 검증 수행 및 결과 바인딩
    log_lines = []
    log_lines.append("========================================")
    log_lines.append(" 쿼리 문법 검증 로그 (Query Validator)")
    log_lines.append(f" 대상 파일: {file_path}")
    log_lines.append("========================================\n")
    
    csv_rows = []
    all_valid = True
    
    for line_num, line in enumerate(lines, start=1):
        clean_query = line.strip()
        if not clean_query:
            continue
            
        # 검증 함수 실행
        res = validate_query(clean_query)
        status_str = "정상" if res["is_valid"] else "오류"
        
        # 1) 로그 파일용 라인 작성
        if res["is_valid"]:
            log_lines.append(f"[Line {line_num:02d}] 성공 - 정상적인 쿼리")
        else:
            log_lines.append(f"[Line {line_num:02d}] 실패 - {res['message']} (기호: {res['error_char']}, 위치: {res['error_pos']})")
            log_lines.append(f"  └─ 오류 쿼리문: {clean_query}")
            all_valid = False
            
        # 2) CSV 파일용 행 데이터 구조화
        csv_rows.append({
            "라인번호": line_num,
            "쿼리내용": clean_query,
            "정상여부": status_str,
            "오류내용": res["message"] if not res["is_valid"] else "",
            "오류기호": res["error_char"],
            "오류위치(글자수)": res["error_pos"]
        })

    log_lines.append(f"\n" + "="*40)
    if all_valid:
        log_lines.append("최종 결과: 모든 쿼리 문장이 정상입니다.")
    else:
        log_lines.append("최종 결과: 일부 쿼리 문장에서 문법적 오류가 발견되었습니다.")

    # 6. 로그 파일(.log) 저장
    try:
        with open(log_filepath, 'w', encoding='utf-8') as log_file:
            log_file.write('\n'.join(log_lines))
    except Exception as e:
        print(f"[오류] 로그 파일 작성 중 예외 발생: {e}")
        return

    # 7. 데이터 파일(.csv) 저장 (Excel 호환성 보장을 위해 utf-8-sig 인코딩 사용)
    try:
        fieldnames = ["라인번호", "쿼리내용", "정상여부", "오류내용", "오류기호", "오류위치(글자수)"]
        with open(csv_filepath, 'w', encoding='utf-8-sig', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
            
        print(f"\n[검증 프로세스 완료]")
        print(f"- 결과 로그 파일: {log_filepath}")
        print(f"- 결과 데이터 파일: {csv_filepath}")
    except Exception as e:
        print(f"[오류] CSV 파일 작성 중 예외 발생: {e}")


if __name__ == "__main__":
    # 아규먼트 개수 확인 (스크립트명, 대상파일경로, 결과디렉토리경로 총 3개 필요)
    if len(sys.argv) < 3:
        print(" [사용법 예시]")
        print("  python3 query_validator_v03.py [검증대상_파일경로] [결과_저장디렉토리]")
        print("\n [실행 예]")
        print("  python3 query_validator_v03.py ./queries.txt ./logs")
    else:
        target_file = sys.argv[1]
        output_directory = sys.argv[2]
        check_query_process(target_file, output_directory)