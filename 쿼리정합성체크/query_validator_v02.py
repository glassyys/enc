# -*- coding: utf-8 -*-
"""
==========================================================================
[프로그램 개요]
본 프로그램(query_validator_v02.py)은 텍스트 파일에 저장된 SQL 쿼리문들을 
한 줄씩 읽어와서 괄호 및 따옴표의 문법적 쌍(Pair)이 올바르게 일치하는지 
검증하는 유틸리티입니다.

[주요 검증 조건]
1. 괄호 쌍 체크: 소괄호 '()', 중괄호 '{}', 대괄호 '[]'가 올바른 순서와 쌍으로 닫혔는지 검사합니다.
2. 따옴표 쌍 체크: 싱글 휫따옴표("'"), 더블 쌍따옴표('"'), 백틱('`')이 정상적으로 닫혔는지 검사합니다.
   - 따옴표 내부(문자열 리터럴)에 존재하는 괄호나 다른 따옴표는 문법 오류로 인식하지 않도록 예외 처리됩니다.
   - 따옴표 내부의 이스케이프 문자(\, \') 처리 기능을 포함합니다.

[실행 방법 및 파라미터]
>> python query_validator_v02.py [검증할_쿼리_파일경로] [로그가_저장될_디렉토리경로]
   - 파라미터 1: 검증 대상인 쿼리 텍스트 파일의 경로
   - 파라미터 2: 결과 로그 파일(.log)이 생성될 디렉토리(폴더) 경로

[실행 예시]
1. 검증 대상 파일 준비 (예: ./sample_data/queries.txt)
   --- 파일 내용 예시 ---
   SELECT * FROM users WHERE id = 1 AND name = '홍길동';
   SELECT * FROM table WHERE id = (1 + 2;
   ---------------------
2. 명령어 실행 (./outputs 디렉토리에 로그를 저장하고 싶은 경우)
   >> python query_validator_v02.py ./sample_data/queries.txt ./outputs
3. 실행 결과
   - 지정된 ./outputs 디렉토리 내에 [queries.txt.log] 파일이 자동으로 생성되어 상세 내역이 기록됩니다.
==========================================================================
"""

import sys
import os

def validate_query(query: str) -> tuple[bool, str]:
    """
    단일 쿼리문장의 괄호 및 따옴표 쌍이 일치하는지 스택(Stack) 구조를 활용해 검증합니다.
    """
    stack = []
    bracket_map = {')': '(', '}': '{', ']': '['}
    quote_chars = {'"', "'", "`"}
    
    in_quote = None  # 현재 열려 있는 따옴표 종류 종류 기록
    escaped = False  # 직전 문자가 백슬래시(\)였는지 여부
    
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
                stack.append(char)  # 여는 괄호는 스택에 삽입
            elif char in bracket_map.keys():
                # 닫는 괄호를 만났을 때 스택이 비어있거나 짝이 맞지 않으면 실패
                if not stack or stack[-1] != bracket_map[char]:
                    return False, f"짝이 맞지 않는 닫는 괄호 '{char}' 발견 (위치: {i}번째 문자)"
                stack.pop()

    # 최종 결과 반환
    if in_quote:
        return False, f"닫히지 않은 따옴표 [{in_quote}]가 존재합니다."
    if stack:
        return False, f"닫히지 않은 여는 괄호가 남아있습니다: {', '.join(stack)}"
        
    return True, "정상"


def check_query_and_save_log(file_path: str, log_dir: str):
    """
    쿼리 파일을 읽어 검증한 후, 사용자가 지정한 디렉토리 안에 [파일명.log]로 결과를 저장합니다.
    """
    # 1. 입력 파일 존재 여부 확인
    if not os.path.exists(file_path):
        print(f"[오류] 검증 대상 파일 '{file_path}'을(를) 찾을 수 없습니다.")
        return

    # 2. 결과 저장할 디렉토리 존재 여부 확인 및 생성 (없으면 자동 생성)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
            print(f"[알림] 존재하지 않는 로그 디렉토리를 생성했습니다: {log_dir}")
        except Exception as e:
            print(f"[오류] 로그 디렉토리 생성 실패: {e}")
            return

    # 3. 로그 파일명 정의 ([입력파일명].log)
    input_filename = os.path.basename(file_path)
    log_filename = f"{input_filename}.log"
    full_log_path = os.path.join(log_dir, log_filename)

    # 4. 쿼리 파일 읽기
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[오류] 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    # 5. 검증 수행 및 로그 내용 작성
    log_lines = []
    log_lines.append(f"========================================")
    log_lines.append(f" 쿼리 문법 검증 로그 (Query Validator)")
    log_lines.append(f" 대상 파일: {file_path}")
    log_lines.append(f"========================================\n")
    
    all_valid = True
    
    for line_num, line in enumerate(lines, start=1):
        clean_query = line.strip()
        if not clean_query:
            continue
            
        is_valid, message = validate_query(clean_query)
        
        if is_valid:
            log_lines.append(f"[Line {line_num:02d}] 성공 - 정상적인 쿼리")
        else:
            log_lines.append(f"[Line {line_num:02d}] 실패 - {message}")
            log_lines.append(f"  └─ 오류 쿼리문: {clean_query}")
            all_valid = False

    log_lines.append(f"\n" + "="*40)
    if all_valid:
        log_lines.append("최종 결과: 모든 쿼리 문장이 정상입니다.")
    else:
        log_lines.append("최종 결과: 일부 쿼리 문장에서 문법적 오류가 발견되었습니다.")

    # 6. 로그 파일 작성 및 완료 안내
    try:
        with open(full_log_path, 'w', encoding='utf-8') as log_file:
            log_file.write('\n'.join(log_lines))
        
        print(f"\n[검증 완료]")
        print(f"- 결과 로그 파일이 성공적으로 생성되었습니다.")
        print(f"- 로그 저장 경로: {full_log_path}")
    except Exception as e:
        print(f"[오류] 로그 파일 작성 중 예외 발생: {e}")


if __name__ == "__main__":
    # 아규먼트 개수 확인 (스크립트명, 대상파일경로, 로그디렉토리경로 총 3개 필요)
    if len(sys.argv) < 3:
        print(" [사용법 예시]")
        print("  python query_validator_v02.py [검증대상_파일경로] [결과로그_저장디렉토리]")
        print("\n [실행 예]")
        print("  python query_validator_v02.py ./queries.txt ./logs")
    else:
        target_file = sys.argv[1]
        output_directory = sys.argv[2]
        check_query_and_save_log(target_file, output_directory)