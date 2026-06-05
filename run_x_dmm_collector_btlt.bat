@echo off
REM BL/TL 収集のみ実行
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --script scripts/collect/bltl.py
