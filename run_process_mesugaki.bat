@echo off
REM ================================================
REM process: mesugaki pipeline (parallel)
REM update_mesugaki -> ai_review_mesugaki -> weekly_rankings_mesugaki
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process_mesugaki --continue-on-error
