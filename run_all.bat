@echo off
REM ================================================
REM 収集フェーズ → 加工フェーズ の順で実行
REM （gha フェーズ＝週次ランキング・女優 AI レビューは含まない）
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase all --continue-on-error
