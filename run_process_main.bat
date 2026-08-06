@echo off
REM ================================================
REM process: main pipeline (parallel)
REM update_items -> ai_review -> weekly_rankings
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process_main --continue-on-error
