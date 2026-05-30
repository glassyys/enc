#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ===============================================================
# query_validator.py
#
# 실행예시 (직접 실행):
#   chmod +x query_validator.py          # 최초 1회만
#   ./query_validator.py <텍스트파일_전체경로>
#
# 또는 python3으로 실행:
#   python3 query_validator.py <텍스트파일_전체경로>
#
# 예시:
#   ./query_validator.py /usr/local/data/queries.txt
#   python3 query_validator.py /usr/local/data/queries.txt
#
# 설명:
#   파일 안에 줄 단위로 작성된 쿼리 문장들을 읽어들여
#   괄호('(', '{', '[') 및 따옴표('"', "'", '`')의 쌍이 문법적으로
#   올바르게 닫혀 있는지 검증하는 유틸리티 스크립트입니다.
#
# 구성 내용:
#   1) validate_query: 단일 쿼리 문자열을 파라미터로 받아 이스케이프 처리 및
#      따옴표 내부/외부 상태를 고려하여 괄호 짝을 스택으로 검증합니다.
#   2) check_query_file: 대상 파일을 읽어 각 줄(쿼리)마다 validate_query를
#      호출하여 결과를 표준 출력으로 보여줍니다.
# ===============================================================

import sys
import os
import codecs


def validate_query(query):
    """
    단일 쿼리문장의 괄호 및 따옴표 쌍이 일치하는지 검증합니다.
    """
    stack = []
    # 체크할 괄호 정의 (우괄호: 좌괄호 대응)
    bracket_map = {')': '(', '}': '{', ']': '['}
    # 체크할 따옴표 정의
    quote_chars = set(['"', "'", "`"])

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
                    return False, "정치되지 않은 닫는 괄호 '%s' 발견 (위치: %d번째 문자)" % (char, i)
                stack.pop()

    # 최종 상태 검사
    if in_quote:
        return False, "닫히지 않은 따옴표 '%s' 존재함" % in_quote
    if stack:
        return False, "닫히지 않은 괄호가 남아있음: %s" % (", ".join(stack))

    return True, "정상"


def check_query_file(file_path):
    """
    파일명을 파라미터로 받아 파일 안의 쿼리 리스트를 한 줄씩 검증합니다.
    """
    if not os.path.exists(file_path):
        print("오류: 파일 '%s'을(를) 찾을 수 없습니다." % file_path)
        return

    print("[%s] 파일 검증을 시작합니다...\n" % file_path)

    with codecs.open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    all_valid = True
    for line_num, line in enumerate(lines, start=1):
        clean_query = line.strip()
        # 빈 줄은 건너뜀
        if not clean_query:
            continue

        is_valid, message = validate_query(clean_query)

        if is_valid:
            print("[Line %02d] 성공 - 정상적인 쿼리" % line_num)
        else:
            print("[Line %02d] 실패 - %s" % (line_num, message))
            print("  └─ 문제 쿼리: %s" % clean_query)
            all_valid = False

    print("\n" + "=" * 40)
    if all_valid:
        print("결과: 모든 쿼리 문장이 정상입니다.")
    else:
        print("결과: 일부 쿼리 문장에 문법적 오류가 발견되었습니다.")


if __name__ == "__main__":
    # 실행 시 파일명을 아규먼트(파라미터)로 받았는지 확인
    if len(sys.argv) < 2:
        print("사용법: ./query_validator.py [텍스트파일_전체경로]")
        print("     또는: python3 query_validator.py [텍스트파일_전체경로]")
        print("예시:  ./query_validator.py /usr/local/data/queries.txt")
    else:
        file_name = sys.argv[1]
        check_query_file(file_name)