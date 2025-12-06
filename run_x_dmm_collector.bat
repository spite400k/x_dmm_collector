@echo off
REM ================================================
REM タスクスケジューラ用：x_dmm_collector 実行バッチ
REM ================================================

REM Pythonの絶対パスを指定（ここを自分の環境に置き換える）
SET PYTHON_EXE=C:\Users\kazuk\AppData\Local\Programs\Python\Python313\python.exe
REM スクリプトの絶対パス
SET SCRIPT_PATH=c:/Users/kazuk/python/x_dmm_collector/main.py

REM 作業ディレクトリ
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector

REM ログ出力用ファイル
SET LOG_FILE=%WORK_DIR%\\logs\task_run.log

REM ================================================
echo ================================================ >> %LOG_FILE%
echo %DATE% %TIME% - タスク開始 >> %LOG_FILE%
cd /d %WORK_DIR%
"%PYTHON_EXE%" "%SCRIPT_PATH%" >> %LOG_FILE% 2>&1
echo %DATE% %TIME% - タスク終了 >> %LOG_FILE%
echo ================================================ >> %LOG_FILE%
