# InvenTree Stok Kontrol Eklentisi

## İçindekiler

- [Bu ne işe yarar?](#bu-ne-işe-yarar)
- [Nasıl çalışır?](#nasıl-çalışır)
- [Kurulum](#kurulum)
- [Eklentiyi aktif etme](#eklentiyi-aktif-etme)
- [Ayarlar](#ayarlar)
- [Test verisi ve demo](#test-verisi-ve-demo)
- [CSV Export](#csv-export)
- [Unit testleri çalıştırma](#unit-testleri-çalıştırma)
- [Tasarım kararları](#tasarım-kararları)

---

## Bu ne işe yarar?

Bir üretim emri (Build Order) oluşturduğunda veya güncellendiğinde, bu eklenti otomatik olarak şunu sorar:

> "Bu ürünü üretmek için gereken tüm malzemeler stokta var mı?"

E�er eksik malzeme varsa seni hemen uyarır — ya bir hata göstererek order'ı bloklar, ya da order'ı oluşturup eksik listesini Build Order'ın notlarına ekler.

**Multi-level BOM desteği** sayesinde sadece doğrudan malzemeleri değil, alt assembly'lerin içindeki malzemeleri de kontrol eder.

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
Sen bir üretim emri kaydeder veya güncellersin
        │
        ├──── ÖNCE: ValidationMixin tetiklenir
        │         │
        │         ├── Mod: Error → eksik varsa BLOKLA, kaydetme
        │         └── Mod: Warning → bir şey yapma, devam et
        │
        ▼
   InvenTree order'ı kaydeder
        │
        └──── SONRA: EventMixin tetiklenir
                  │  (build_build.created veya build_build.saved)
                  │
                  ├── Mod: Error → zaten bloklandı, buraya gelmez
                  └── Mod: Warning → eksik varsa Notes alanına yaz/güncelle
```

### Multi-level BOM desteği

Plugin sadece doğrudan BOM item'larını değil, alt assembly'lerin BOM'larını da recursive olarak tarar:

```
PCB Board
├── R1                (doğrudan kontrol edilir)
├── C1                (doğrudan kontrol edilir)
└── Microcontroller   (assembly → içine inilir)
    └── Power Module  (assembly → içine inilir)
        ├── Capacitor         (kontrol edilir)
        └── Voltage Regulator (kontrol edilir)
```

Aynı parça birden fazla seviyede geçiyorsa miktarlar **toplanır**.

### Eksik hesaplama formülü

Her leaf (hammadde) BOM item için:

```
required     = bom miktarı × üretim miktarı  (tüm seviyelerde çarpılarak)
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
git clone https://github.com/ovalriver23/Antsis_TestCase.git
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

### 2. InvenTree'nin global ayarlarını aç (önemli!)

Warning modu ve CSV export için iki global ayarın açık olması gerekir.

- **Admin Center → Plugins** üst kısmındaki ayarlarda şunları aç:
  - **Enable Event Integration** → Warning modunun çalışması için
  - **Enable URL Integration** → CSV export endpoint'inin çalışması için

> Bu ayarları açmazsan **Warning modu** ve **CSV export** çalışmaz. Error modu yine çalışır çünkü o validation üzerinden gider.

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

### Senaryo 1 — Tek seviye BOM

**Parçalar:**

| Parça | Description | Assembly | Stok |
|-------|-------------|:--------:|-----:|
| R1 | Resistor 10 ohm | Kapalı | 500 |
| C1 | Capacitor 10uF | Kapalı | 80 |
| MCU1 | Microcontroller | Kapalı | 0 |
| PCB Board | Üretilen kart | **Açık** | — |

**PCB Board BOM:**

| Component | Quantity |
|-----------|---------:|
| R1 | 10 |
| C1 | 5 |
| MCU1 | 1 |

**Build Order:** PCB Board × 20

**Beklenen sonuç:**
```
Build Order #X — Eksik malzemeler:
  - C1: lazım 100, stokta 80, eksik 20
  - MCU1: lazım 20, stokta 0, eksik 20
```

---

### Senaryo 2 — Multi-level BOM

**Parçalar:**

| Parça | Description | Assembly | Stok |
|-------|-------------|:--------:|-----:|
| Capacitor | 100uF Capacitor | Kapalı | 50 |
| Voltage Regulator | 5V Regulator | Kapalı | 10 |
| Power Module | Modüler güç birimi | **Açık** | 0 |
| Microcontroller | MCU with power | **Açık** | 0 |

**Power Module BOM:**

| Component | Quantity |
|-----------|---------:|
| Capacitor | 10 |
| Voltage Regulator | 1 |

**Microcontroller BOM:**

| Component | Quantity |
|-----------|---------:|
| Power Module | 1 |

**Build Order:** PCB Board × 20 (MCU1 yerine Microcontroller kullanılırsa)

**Beklenen sonuç:** Plugin MCU'nun içindeki Power Module'e, oradan da Capacitor ve Voltage Regulator'a iner. Eksik miktarları tüm seviyeleri hesaba katarak raporlar.

---

### Modların test edilmesi

**Warning modu (default):**
- Order kaydedilir
- Order detay sayfasında **Notes** sekmesinde eksik raporu görünür
- Order tekrar güncellenirse rapor **yerinde güncellenir** (üst üste eklenmez)

**Error modu:**
- Plugin ayarlarından **Check Mode → Error** yap
- Build Order kaydetmeye çalış
- Ekranda kırmızı **Form Error** kutusu çıkar, order kaydedilmez

---

## CSV Export

Herhangi bir Build Order için eksik malzeme raporunu CSV olarak indirebilirsin.

### Kullanım

Tarayıcıda şu URL'e git (build_id yerine order numarasını yaz):

```
http://localhost:8000/plugin/materialcheckplugin/export/<build_id>/
```

Örnek:

```
http://localhost:8000/plugin/materialcheckplugin/export/2/
```

### CSV İçeriği

```
Build Order;Part;Required;Available;Shortage
2;C1;100;80;20
2;MCU1;20;0;20
```

> **Not:** CSV export'un çalışması için **Enable URL Integration** ayarının açık olması gerekir.

---

## Unit testleri çalıştırma

Plugin'in core mantığını test eden 8 unit test bulunmaktadır. Testler `plugin/material_check/tests/test_plugin.py` dosyasındadır.

### Pytest kurulumu (sadece ilk seferinde)

```bash
docker compose exec server pip install pytest pytest-django --break-system-packages
```

### Testleri çalıştırma

```bash
docker compose exec -w /home/inventree/plugins/material_check/tests server pytest test_plugin.py -v
```

### Beklenen çıktı

```
test_plugin.py::test_basic_sanity PASSED
test_plugin.py::test_no_shortage_when_stock_sufficient PASSED
test_plugin.py::test_shortage_detected_when_stock_insufficient PASSED
test_plugin.py::test_multiple_shortages PASSED
test_plugin.py::test_negative_stock_clamped_to_zero_when_disallowed PASSED
test_plugin.py::test_negative_stock_counted_when_allowed PASSED
test_plugin.py::test_use_allocated_stock_branch PASSED
test_plugin.py::test_use_total_stock_branch PASSED

8 passed in 0.02s
```

### Test edilen senaryolar

| Test | Ne kontrol eder |
|------|-----------------|
| `test_no_shortage_when_stock_sufficient` | Yeterli stok varsa boş liste döner |
| `test_shortage_detected_when_stock_insufficient` | Eksik miktarı doğru hesaplanır |
| `test_multiple_shortages` | Birden fazla eksik tespit edilebilir |
| `test_negative_stock_clamped_to_zero_when_disallowed` | ALLOW_NEGATIVE_STOCK=False iken negatif stok 0 sayılır |
| `test_negative_stock_counted_when_allowed` | ALLOW_NEGATIVE_STOCK=True iken negatif stok hesaba katılır |
| `test_use_allocated_stock_branch` | USE_ALLOCATED_STOCK=True doğru branch'e gider |
| `test_use_total_stock_branch` | USE_ALLOCATED_STOCK=False doğru branch'e gider |

---

## Tasarım kararları

Bu plugin'i nasıl tasarladığım, hangi kararları neden aldığım ve karşılaştığım zorluklar hakkında detaylı açıklamalar için [DESIGN.md](DESIGN.md) dosyasına bakabilirsin.

Özetle:
- **İki mixin yaklaşımı** (ValidationMixin + EventMixin) çünkü ne tek başına yeterli değil
- **Warning/Error modu** çünkü farklı kullanıcıların farklı ihtiyaçları var
- **Notes alanı** çünkü ek UI karmaşıklığı yaratmadan kullanıcıya ulaşır
- **Multi-level BOM** çünkü gerçek üretim senaryolarında assembly içinde assembly olabilir
- **Helper method ayrımı** çünkü test edilebilir ve okunabilir kod için