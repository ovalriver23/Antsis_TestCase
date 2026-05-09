# InvenTree Stok Kontrol Eklentisi

## İçindekiler

- [Bu ne işe yarar?](#bu-ne-işe-yarar)
- [Nasıl çalışır?](#nasıl-çalışır)
- [Kurulum](#kurulum)
- [Eklentiyi aktif etme](#eklentiyi-aktif-etme) *(yakında)*
- [Ayarlar](#ayarlar) *(yakında)*
- [Test verisi ve demo](#test-verisi-ve-demo) *(yakında)*
- [Tasarım kararları](#tasarım-kararları) *(yakında)*

---

## Bu ne işe yarar?

Bir üretim emri (Build Order) oluşturduğunda, bu eklenti otomatik olarak şunu sorar:

> "Bu ürünü üretmek için gereken tüm malzemeler stokta var mı?"

E�er eksik malzeme varsa seni hemen uyarır.

### Neden lazım?

Diyelim ki 20 adet PCB kartı üretmek istiyorsun. Üretim başladıktan sonra bir malzemenin stokta olmadığını fark edersen iş işten geçmiş olur. Bu eklenti, üretim emri oluşturulur oluşturulmaz seni uyarır.

### Örnek senaryo

**Üretim emri:** 20 adet PCB Kartı üret

| Parça | Birim başına | Toplam lazım | Stokta var | Durum |
|-------|:------------:|:------------:|:----------:|:-----:|
| R1    | 10           | 200          | 500        | ✅ Yeterli |
| C1    | 5            | 100          | 80         | ❌ 20 adet eksik |
| MCU1  | 1            | 20           | 0          | ❌ 20 adet eksik |

Eklenti hemen devreye girer ve **C1 ile MCU1'in yetersiz olduğunu** sana bildirir.

---

## Nasıl çalışır?

### Genel akış

```
Sen bir üretim emri oluşturursun
        │
        ▼
InvenTree "yeni üretim emri oluşturuldu" olayını tetikler
        │
        ▼
Eklenti devreye girer
        │
        ▼
Ürünün BOM'unu okur (hangi malzemeden kaç tane lazım)
        │
        ▼
Her malzeme için hesaplama yapar:
    lazım olan     = bom miktarı × üretim miktarı
    kullanılabilir = stok miktarı - başka emirlere ayrılan miktar
    eksik          = lazım olan - kullanılabilir
        │
        ▼
Eksik var mı?
    ├── HAYIR → Hiçbir şey yapmaz
    └── EVET  → Ayara bakar
                ├── Uyarı modu → Üretim emrine not ekler + log yazar
                └── Hata modu  → Üretim emrini oluşturmayı engeller
```

### Tasarım kararları

| Ayar | Default | Değiştirilebilir | Açıklama |
|------|---------|:----------------:|----------|
| Kontrol aktif/pasif | Aktif | ✅ | Eklentiyi tamamen kapatıp açabilirsin |
| Kontrol modu | Uyarı | ✅ | Uyarı: order oluşur ama bilgilendirilirsin. Hata: order oluşmaz |
| Negatif stok | İzin verilmez | ✅ | Stok miktarı 0'ın altına düşemez |
| Ayrılmış stok | Hesaba katılır | ✅ | Başka emirlere ayrılan malzeme kullanılabilir stoktan düşülür |
| UI bildirimi | Yok | — | Gerekirse sonradan eklenebilir |

---

## Kurulum

### Gereksinimler

- Docker
- Docker Compose

### Adımlar

**1. Repoyu klonla**

```bash
git clone https://github.com/kullanici/inventree-material-check.git
cd inventree-material-check
```

**2. `.env` dosyasını oluştur**

```bash
# Veritabanı ayarları
INVENTREE_DB_ENGINE=postgresql
INVENTREE_DB_NAME=inventree_db
INVENTREE_DB_USER=inventreeuser
INVENTREE_DB_PASSWORD=inventreepass
INVENTREE_DB_HOST=inventree-db
INVENTREE_DB_PORT=5432

# InvenTree genel ayarları
INVENTREE_EXT_VOLUME=/home/inventree/data
INVENTREE_SITE_URL=http://localhost:8000
INVENTREE_WEB_PORT=8000
INVENTREE_PLUGINS_ENABLED=True
INVENTREE_PLUGIN_DIR=/home/inventree/plugins

# Admin kullanıcısı
INVENTREE_ADMIN_USER=admin
INVENTREE_ADMIN_PASSWORD=admin1234
INVENTREE_ADMIN_EMAIL=admin@local.com
```

**3. Servisleri başlat**

```bash
docker compose up -d
```

**4. Veritabanını hazırla**

İlk kurulumda bir kez çalıştırılması gerekir. Bu komut veritabanı tablolarını oluşturur ve admin kullanıcısını tanımlar.

```bash
docker compose run --rm server invoke update
```

**5. Servisleri yeniden başlat**

```bash
docker compose down
docker compose up -d
```

**6. Tarayıcıdan aç**

```
http://localhost:8000
```

Admin bilgileriyle giriş yap:
- Kullanıcı adı: `admin`
- Şifre: `admin1234`

---

*Aşağıdaki bölümler ilerledikçe doldurulacak.*