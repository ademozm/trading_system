#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
    echo "Sanal ortam bulunamadı. Önce kurulumu tamamlamalısın."
    echo "README.md dosyasındaki adımları takip et."
    read -p "Devam etmek için Enter'a bas..."
    exit 1
fi
source venv/bin/activate
echo "Uygulama başlatılıyor, tarayıcı birazdan açılacak..."
streamlit run app.py
