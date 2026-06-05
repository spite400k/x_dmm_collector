@echo off
REM ================================================
REM 収集フェーズのみ実行
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase collect --continue-on-error
