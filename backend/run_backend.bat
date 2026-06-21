@echo off
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist .env (
  copy .env.example .env
  echo EDIT backend\.env and add your OPENAI_API_KEY
)
python main.py
pause
