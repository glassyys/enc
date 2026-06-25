@echo off
chcp 65001 > nul
echo ===================================================
echo [Git 초기화 및 오류 해결 스크립트]
echo ===================================================
echo.
echo 1. 백그라운드에서 멈춰있는 Git 프로세스를 종료합니다...
taskkill /f /im git.exe 2>nul
echo.
echo 2. Git 인덱스 락(.git\index.lock) 파일이 있으면 삭제합니다...
if exist ".git\index.lock" (
    del ".git\index.lock"
    echo [완료] .git\index.lock 파일을 삭제했습니다.
) else (
    echo [정보] index.lock 파일이 존재하지 않습니다.
)
echo.
echo 3. 터미널에서 수동으로 git status를 실행해 봅니다...
git status
echo.
echo ===================================================
echo 작업이 완료되었습니다. VS Code의 소스 제어 창을 확인해보세요.
echo 만약 여전히 도넛 모양이 돌고 있다면 VS Code를 재시작해 주세요.
echo ===================================================
pause
