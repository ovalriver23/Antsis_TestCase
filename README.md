# InvenTree Stok Kontrol Eklentisi

## İçindekiler

- [Bu ne işe yarar?](#bu-ne-işe-yarar)
- [Nasıl çalışır?](#nasıl-çalışır)
- [Kurulum](#kurulum)
- [Eklentiyi aktif etme](#eklentiyi-aktif-etme)
- [Ayarlar](#ayarlar)
- [Test verisi ve demo](#test-verisi-ve-demo)
- [Tasarım kararları](#tasarım-kararları) *(yakında)*

---

## Bu ne işe yarar?

Bir üretim emri (Build Order) oluşturduğunda, bu eklenti otomatik olarak şunu sorar:

> "Bu ürünü üretmek için gereken tüm malzemeler stokta var mı?"

Eğer eksik malzeme varsa seni hemen uyarır — ya bir hata göstererek order'ı bloklar, ya da order'ı oluşturup eksik listesini Build Order'ın notlarına ekler.

### Neden lazım?

Diyelim ki 20 adet PCB kartı üretmek istiyorsun. Üretim başladıktan sonra bir malzemenin stokta olmadığını fark edersen iş işten geçmiş olur. Bu eklenti, üretim emri kaydedildiği an seni uyarır.

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

Plugin iki ayrı InvenTree mekanizmasını birden kullanır:

- **ValidationMixin** → Build Order kaydedilmeden ÖNCE çalışır. Error modunda eksik varsa order'ı bloklar.
- **EventMixin** → Build Order kaydedildikten SONRA çalışır. Warning modunda Build Order'ın notes alanına eksik raporu yazar.

### Genel akış

```
Sen bir üretim emri kaydedersin
        │
        ├──── ÖNCE: ValidationMixin tetiklenir
        │         │
        │         ├── Mod: Error → eksik varsa BLOKLA, kaydetme
        │         └── Mod: Warning → bir şey yapma, devam et
        │
        ▼
   InvenTree order'ı kaydeder
        │
        └──── SONRA: EventMixin tetiklenir (build_build.created event'i)
                  │
                  ├── Mod: Error → zaten bloklandı, buraya gelmez
                  └── Mod: Warning → eksik varsa Notes alanına yaz
```

### Eksik hesaplama formülü

Her BOM item için:

```
required     = bom miktarı × üretim miktarı
available    = (USE_ALLOCATED_STOCK açıksa) stok - ayrılmış stok
               (USE_ALLOCATED_STOCK kapalıysa) toplam stok
available    = (ALLOW_NEGATIVE_STOCK kapalıysa) max(available, 0)
shortage     = required - available
```

`shortage > 0` olanlar eksik listesine girer.

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

İlk kurulumda bir kez çalıştırılması gerekir.

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

## Eklentiyi aktif etme

Plugin sistem üzerinde otomatik tanınır ama varsayılan olarak **pasif** durumdadır. Aktif etmek için 3 adımı tamamlaman gerekir.

### 1. Plugin'i aktif et

- **Admin Center → Plugins** sayfasına git
- Listeden **MaterialCheckPlugin** satırını bul, üstüne tıkla
- Açılan panelde **Active** toggle'ını aç

### 2. InvenTree'nin event sistemini aç (önemli!)

Warning modunun çalışması için InvenTree'nin global event entegrasyonu açık olmalı. Bu varsayılan olarak kapalıdır.

- **Admin Center → Plugins** üst kısmındaki ayarlarda
- **Enable Event Integration** toggle'ını aç

> Bu ayarı açmazsan, **Warning modu çalışmaz** (eksik raporu Notes alanına yazılmaz). Error modu yine çalışır çünkü o validation üzerinden gider.

### 3. Servisleri yeniden başlat

```bash
docker compose restart server worker
```

Artık plugin Build Order kaydedildiğinde otomatik devreye girer.

---

## Ayarlar

Plugin detay sayfasında **Plugin Settings** bölümünde 4 ayar bulunur:

| Ayar | Tip | Default | Ne yapar? |
|------|-----|---------|-----------|
| **Enable Check** | Açık/Kapalı | Açık | Plugin'in çalışıp çalışmayacağını kontrol eder. Kapalıysa stok kontrolü hiç yapılmaz. |
| **Check Mode** | Seçim | Warning | Eksik malzeme bulununca ne olacağını belirler. **Warning:** order kaydedilir, eksikler Notes alanına yazılır. **Error:** order kaydedilmez, ekrana hata mesajı çıkar. |
| **Allow Negative Stock** | Açık/Kapalı | Kapalı | Stok miktarının 0'ın altına düşmesine izin verilip verilmeyeceği. Açıkken negatif stok olduğu gibi hesaba katılır (örn: stok -5 ve lazım 100 ise eksik 105 hesaplanır). Kapalıyken negatif değerler 0 olarak kabul edilir. |
| **Consider Allocated Stock** | Açık/Kapalı | Açık | Başka Build Order'lara ayrılmış (allocated) stoğun hesaba katılıp katılmayacağı. Açıkken kullanılabilir stok = toplam stok - ayrılmış stok. |

---

## Test verisi ve demo

Plugin'in çalışmasını test etmek için aşağıdaki demo verisini hazırlayabilirsin.

### 1. Parçaları oluştur

**Parts** sayfasından `+` ile yeni parçalar ekle:

| Parça | Description | Assembly | Stok |
|-------|-------------|:--------:|-----:|
| R1 | Resistor 10 ohm | Kapalı | 500 |
| C1 | Capacitor 10uF | Kapalı | 80 |
| MCU1 | Microcontroller | Kapalı | 0 |
| PCB Board | Üretilen kart | **Açık** | — |

> **Not:** PCB Board'un Assembly toggle'ını AÇMAYI unutma. Aksi halde BOM ekleyemezsin.

### 2. PCB Board için BOM oluştur

PCB Board → **Bill of Materials** sekmesi → `+` butonu ile şunları ekle:

| Component | Quantity |
|-----------|---------:|
| R1 | 10 |
| C1 | 5 |
| MCU1 | 1 |

### 3. Build Order oluştur

**Manufacturing → Build Orders → +** ile:
- Part: PCB Board
- Quantity: 20

### 4. Beklenen sonuçlar

**Warning modunda** (default):
- Order kaydedilir
- Order detay sayfasında **Notes** sekmesinde şu rapor görünür:

```
Build Order #X — Eksik malzemeler:
  - C1: lazım 100, stokta 80, eksik 20
  - MCU1: lazım 20, stokta 0, eksik 20
```

**Error modunda**:
- Plugin ayarlarından **Check Mode → Error** yap
- Build Order kaydetmeye çalış
- Ekranda kırmızı bir Form Error kutusu çıkar:

```
Build Order #X — Eksik malzemeler:
  - C1: lazım 100, stokta 80, eksik 20
  - MCU1: lazım 20, stokta 0, eksik 20
```

- Order **kaydedilmez**

---

*Tasarım kararları bölümü ilerledikçe doldurulacak.*