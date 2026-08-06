@echo off
REM BL/TL 収集のみ実行
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe
SET PYTHONUTF8=1
SET PYTHONIOENCODING=utf-8

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --script scripts/collect/bltl.py
