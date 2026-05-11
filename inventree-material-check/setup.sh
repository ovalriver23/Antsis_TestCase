#!/bin/bash
set -e

echo "InvenTree kurulumu başlıyor..."

echo "[1/3] Servisler başlatılıyor (migrate + admin kurulumu dahil)..."
docker compose up -d

echo "[2/3] Setup tamamlanması bekleniyor..."
docker compose wait setup

echo "[3/3] Server ve worker yeniden başlatılıyor..."
docker compose restart server worker

echo ""
echo "Kurulum tamamlandı!"
echo "Adres : http://localhost:8000"
echo "Kullanıcı : admin"
echo "Şifre    : admin1234"
