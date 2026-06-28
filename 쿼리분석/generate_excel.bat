@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ==========================================
echo  소스 프로그램 분석 요약 엑셀 생성 실행 쉘
echo ==========================================
python generate_excel.py
pause
