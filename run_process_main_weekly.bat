@echo off
REM ================================================
REM process: main weekly catalog refresh
REM update_items --mode weekly (items outside recent release window)
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe
SET PYTHONUTF8=1
SET PYTHONIOENCODING=utf-8

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process_main_weekly --continue-on-error
