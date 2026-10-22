@echo off
cd /d %~dp0
if not exist venv (
    echo Sanal ortam bulunamadi. Once kurulumu tamamlamalisin.
    echo README.md dosyasindaki adimlari takip et.
    pause
    exit /b
)
call venv\Scripts\activate.bat
echo Uygulama baslatiliyor, tarayici birazdan acilacak...
streamlit run app.py
pause
