@echo off
REM ================================================
REM タスクスケジューラ用：x_dmm_collector 実行バッチ
REM ================================================

REM Pythonの絶対パスを指定（ここを自分の環境に置き換える）
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe
REM スクリプトの絶対パス
SET SCRIPT_PATH=c:/Users/kazuk/python/x_dmm_collector/main.py
REM スクリプトの絶対パス
SET SCRIPT_PATH2=c:/Users/kazuk/python/x_dmm_collector/main_mesugaki.py
REM スクリプトの絶対パス
SET SCRIPT_PATH3=c:/Users/kazuk/python/x_dmm_collector/main_bltl.py
REM 作業ディレクトリ
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector

REM ログ出力用ファイル
SET LOG_FILE=%WORK_DIR%\\logs\task_run.log
SET LOG_FILE2=%WORK_DIR%\\logs\task_run_mesugaki.log
SET LOG_FILE3=%WORK_DIR%\\logs\task_run_bltl.log


REM ================================================
echo ================================================ >> %LOG_FILE%
cd /d %WORK_DIR%
echo %DATE% %TIME% - タスク開始 >> %LOG_FILE%
"%PYTHON_EXE%" "%SCRIPT_PATH%" >> %LOG_FILE% 2>&1
echo %DATE% %TIME% - タスク終了 >> %LOG_FILE%
echo ================================================ >> %LOG_FILE%
echo ================================================ >> %LOG_FILE2%
echo %DATE% %TIME% - タスク開始 >> %LOG_FILE2%
"%PYTHON_EXE%" "%SCRIPT_PATH2%" >> %LOG_FILE2% 2>&1
echo %DATE% %TIME% - タスク終了 >> %LOG_FILE2%
echo ================================================ >> %LOG_FILE2%
echo ================================================ >> %LOG_FILE3%
echo %DATE% %TIME% - タスク開始 >> %LOG_FILE3%
"%PYTHON_EXE%" "%SCRIPT_PATH3%" >> %LOG_FILE3% 2>&1
echo %DATE% %TIME% - タスク終了 >> %LOG_FILE3%
echo ================================================ >> %LOG_FILE3%