import sys
import os

def validate_query(query: str) -> tuple[bool, str]:
    """
    단일 쿼리문장의 괄호 및 따옴표 쌍이 일치하는지 검증합니다.
    """
    stack = []
    # 체크할 괄호 정의 (우괄호: 좌괄호 대응)
    bracket_map = {')': '(', '}': '{', ']': '['}
    # 체크할 따옴표 정의
    quote_chars = {'"', "'", "`"}
    
    in_quote = None  # 현재 어떤 따옴표 안에 있는지 저장 (None이면 따옴표 밖)
    escaped = False  # 바로 직전 문자가 백슬래시(\)였는지 여부
    
    for i, char in enumerate(query):
        # 1. 이스케이프 문자 처리
        if escaped:
            escaped = False
            continue
            
        if char == '\\':
            if in_quote:  # 따옴표 내부에서만 백슬래시를 이스케이프 문자로 인식
                escaped = True
            continue
            
        # 2. 따옴표 내부인 경우 처리
        if in_quote:
            if char == in_quote:  # 열렸던 따옴표와 같은 따옴표를 만나면 닫힘 처리
                in_quote = None
            continue  # 따옴표 내부의 괄호나 다른 따옴표는 문법 검사에서 제외
            
        # 3. 따옴표 외부인 경우 처리
        else:
            # 따옴표가 시작되는 경우
            if char in quote_chars:
                in_quote = char
                continue
            # 좌괄호가 시작되는 경우 스택에 추가
            elif char in bracket_map.values():
                stack.append(char)
            # 우괄호를 만난 경우
            elif char in bracket_map.keys():
                # 스택이 비어있거나, 스택의 최상단 괄호와 짝이 맞지 않으면 실패
                if not stack or stack[-1] != bracket_map[char]:
                    return False, f"정치되지 않은 닫는 괄호 '{char}' 발견 (위치: {i}번째 문자)"
                stack.pop()

    # 최종 상태 검사
    if in_quote:
        return False, f"닫히지 않은 따옴표 {in_quote} 존재함"
    if stack:
        return False, f"닫히지 않은 괄호가 남아있음: {', '.join(stack)}"
        
    return True, "정상"


def check_query_file(file_path: str):
    """
    파일명을 파라미터로 받아 파일 안의 쿼리 리스트를 한 줄씩 검증합니다.
    """
    if not os.path.exists(file_path):
        print(f"오류: 파일 '{file_path}'을(를) 찾을 수 없습니다.")
        return

    print(f"[{file_path}] 파일 검증을 시작합니다...\n")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    all_valid = True
    for line_num, line in enumerate(lines, start=1):
        clean_query = line.strip()
        # 빈 줄은 건너뜀
        if not clean_query:
            continue
            
        is_valid, message = validate_query(clean_query)
        
        if is_valid:
            print(f"[Line {line_num:02d}] 성공 - 정상적인 쿼리")
        else:
            print(f"[Line {line_num:02d}] 실패 - {message}")
            print(f"  └─ 문제 쿼리: {clean_query}")
            all_valid = False
            
    print("\n" + "="*40)
    if all_valid:
        print("결과: 모든 쿼리 문장이 정상입니다.")
    else:
        print("결과: 일부 쿼리 문장에 문법적 오류가 발견되었습니다.")


if __name__ == "__main__":
    # 실행 시 파일명을 아규먼트(파라미터)로 받았는지 확인
    if len(sys.argv) < 2:
        print("사용법: python query_validator.py [텍스트파일명]")
        print("예시: python query_validator.py queries.txt")
    else:
        file_name = sys.argv[1]
        check_query_file(file_name)