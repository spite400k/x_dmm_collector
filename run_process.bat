@echo off
REM ================================================
REM 加工フェーズのみ実行（DMM 依存スクリプト）
REM 週次ランキング・女優 AI レビューは gha フェーズへ移行済みのため含まない
REM （.github/workflows/process-gha.yml / SCRIPTS.md 参照）
REM ================================================
SET WORK_DIR=C:\Users\kazuk\python\x_dmm_collector
SET PYTHON_EXE=C:\Users\kazuk\python\x_dmm_collector\venv\Scripts\python.exe

cd /d %WORK_DIR%
"%PYTHON_EXE%" "%WORK_DIR%\run.py" --phase process --continue-on-error
