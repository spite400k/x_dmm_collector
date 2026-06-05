@echo off
REM ================================================
REM 加工フェーズのみ実行
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process --continue-on-error
