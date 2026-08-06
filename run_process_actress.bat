@echo off
REM ================================================
REM process: actress pipeline (parallel)
REM actress_review -> weekly_rankings_actress
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process_actress --continue-on-error
