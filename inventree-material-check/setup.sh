#!/bin/bash
set -e

echo "InvenTree başlatılıyor..."
docker compose up -d

echo ""
echo "Kurulum tamamlandı!"
echo "Adres     : http://localhost:8000"
echo "Kullanıcı : admin"
echo "Şifre     : admin1234"
