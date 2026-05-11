# Bu plugin'i nasıl tasarladım?

Bu dokümanda ödevdeki 10 maddeyi nasıl ele aldığımı ve her birinde verdiğim kararları anlatıyorum.

---

## 1. Lokal kurulum

Lokal kurulum için **Docker Compose** seçtim. İki sebep:

- **Tekrarlanabilirlik:** Repoyu klonlayan herkes tek komutla aynı ortamı kuruyor. Yerel makineye bağımlılık yok.
- **Production'a yakınlık:** Şu an sade bir compose dosyası ama yapı (db + server + worker servisleri ayrı) production ortamına da uygun. Nginx eklemek tek satırlık iş.

Docker dışı kurulum (manuel Python + PostgreSQL) daha öğretici olurdu ama proje teslim edilebilir bir paket olmalı, kurulum başkasının makinesinde de aynı şekilde çalışmalı.

---

## 2. Plugin geliştirme

Plugin ayrı bir Python paketi olarak `plugin/material_check/` altında geliştirildi. Volume mount ile InvenTree container'ının içine bağlanıyor:

```
./plugin/material_check  →  /home/inventree/plugins/material_check
```

Bu yapının avantajı: plugin kodunu host makinede düzenliyorum, container içine otomatik yansıyor. Geliştirme döngüsü hızlı.

---

## 3. Event yakalama

Bu kısımda iki yaklaşım denedim ve **ikisini birden kullandım**:

| Mekanizma | Ne zaman çalışır | Ne yapabilir |
|-----------|------------------|--------------|
| **ValidationMixin** | Build Order kaydedilmeden ÖNCE | Order'ı bloklayabilir |
| **EventMixin** | Build Order kaydedildikten SONRA | Order'a not ekleyebilir |

İkisini de kullanmamın sebebi şu: tek başına EventMixin order'ı bloklayamaz çünkü zaten kaydedilmiş oluyor. Tek başına ValidationMixin de note ekleyemez çünkü order henüz kaydedilmediği için `pk` (id) yok.

Yani:
- **Error modu** → ValidationMixin (bloklama lazım)
- **Warning modu** → EventMixin (note eklemek lazım)

InvenTree'de Build Order oluşturulduğunda ve güncellendiğinde iki ayrı event fırlatıyor:
- `build_build.created` → yeni order
- `build_build.saved` → güncelleme

Her ikisini de dinleyerek edit durumunda da stok kontrolü yapıyorum. Notes alanındaki raporu akıllıca güncelliyorum — üst üste eklemek yerine marker sistemi ile yerinde değiştiriyorum.

---

## 4. BOM analizi

InvenTree'nin Django ORM yapısı sayesinde BOM bilgisini almak çok temiz:

```python
bom_items = instance.part.bom_items.all()
for bom_item in bom_items:
    sub_part = bom_item.sub_part
    quantity = bom_item.quantity
```

Bu kodu `_calculate_shortages` ve `_traverse_bom` adında iki helper method'a böldüm:

- `_calculate_shortages` — dışarıya açık interface, sonuçları birleştirip döndürür
- `_traverse_bom` — recursive BOM gezme logic'i, içeride kullanılır

Her ikisi de hem validation hem event tarafından çağrılıyor. Kod tekrarı yok.

---

## 5. Stok kontrolü

Ödevde verilen formülü temel aldım:

```python
required = bom_quantity * build_quantity
available = stock_quantity
shortage = required - available
```

Üstüne iki katman ekledim:

**a) Allocated stock kontrolü**

`USE_ALLOCATED_STOCK` ayarı açıksa `available_stock` (ayrılmış stok hariç), kapalıysa `total_stock` kullanılır.

**b) Negatif stok kontrolü**

`ALLOW_NEGATIVE_STOCK` ayarı kapalıysa negatif değerler 0'a yuvarlanır.

**c) Multi-level BOM**

Sadece doğrudan BOM item'larını değil, alt assembly'lerin BOM'larını da recursive olarak tarıyorum. Aynı parça birden fazla seviyede geçiyorsa miktarlar toplanıyor:

```python
def _traverse_bom(self, part, quantity, visited):
    for bom_item in part.bom_items.all():
        if sub_part.assembly:
            # İçine in, miktarı çarp
            self._traverse_bom(sub_part, bom_item.quantity * quantity, visited)
        else:
            # Hammadde, stok kontrolü yap
```

`visited` set'i ile circular BOM döngüsünü önledim (A→B→A gibi sonsuz döngü imkansız).

---

## 6. Kullanıcı bilgilendirme

Ödev 4 farklı yöntem önermişti. Şunları seçtim:

| Yöntem | Kullandım mı | Neden |
|--------|:------------:|-------|
| Validation Error | ✅ | Error modunda mantıklı — order bloklanmalı |
| Build Order Note | ✅ | Warning modunda kullanıcıya kalıcı uyarı |
| Log kaydı | ✅ | Developer için, debug ve audit için lazım |
| UI Notification | ❌ | Karmaşıklığı arttırır, mevcut iki yöntem yeterli |

Notes alanına yazarken akıllı bir güncelleme sistemi kurdum. Marker'lar (`--- MATERIAL CHECK START ---` / `--- MATERIAL CHECK END ---`) ile rapor bloğunu işaretledim. Order her güncellendiğinde rapor **yerinde güncelleniyor**, üst üste eklenmiyor. Kullanıcının kendi notları korunuyor.

Default mod **Warning** çünkü:
- Bloklama agresif, planlama yapan kullanıcı için engelleyici olur
- Kullanıcı isterse Error'a geçer

---

## 7. Plugin ayarları

Ödevde 4 ayar isteniyordu, hepsini ekledim:

| Ayar | Default | Mantığım |
|------|---------|----------|
| **Enable Check** | Aktif | Plugin kurulduktan sonra hemen çalışsın |
| **Check Mode** | Warning | Az engelleyici, planlamaya açık |
| **Allow Negative Stock** | Kapalı | Daha güvenli varsayılan |
| **Consider Allocated Stock** | Açık | Daha gerçekçi hesaplama |

Default değerleri seçerken "kullanıcı kuruyor, hiçbir şeye dokunmuyor — en mantıklı senaryo ne olur?" diye düşündüm.

---

## 8. Kod kalitesi

Okunabilirlik için yaptığım bazı tercihler:

**Helper method'ları ayrıştırdım:**
- `_calculate_shortages` — dışarıya açık interface
- `_traverse_bom` — recursive BOM gezme
- `_format_report` — rapor metni oluşturma
- `_write_note` — notes alanına akıllıca yazma

Her method tek bir iş yapıyor. `_` prefix'i Python'da "bu method içeride kullanılıyor" konvansiyonu — Java'daki `private` gibi.

**`update_fields=["notes"]`** — notes alanını güncellerken sonsuz döngü riskini bilerek önledim. `save()` çağırınca validation tetiklenir, validation tekrar `save()` çağırır, sonsuz döngü. Sadece `notes` alanını belirterek bunu kestim.

---

## 9. Dokümantasyon

Dokümantasyonu **iki dosyaya böldüm**:

- **README.md** → Kullanıcı için. Kurulum, aktif etme, ayarlar, test verisi.
- **DESIGN.md** (bu dosya) → Değerlendiren kişi için. Tasarım kararları ve neden öyle yapıldığı.

İki dosyayı ayırmamın sebebi: kullanıcı README'ye girdiğinde "ben bunu nasıl kurarım?" cevabını hızlı görsün, tasarım detaylarına boğulmasın.

---

## 10. Test verisi

Demo için ödevdeki örneği birebir oluşturdum:

- **Parts:** R1, C1, MCU1 (hammaddeler), PCB Board (assembly)
- **Stock:** R1=500, C1=80, MCU1=0
- **BOM (PCB Board):** R1×10, C1×5, MCU1×1
- **Build Order:** PCB Board × 20

Multi-level BOM testi için ikinci bir senaryo da ekledim:

- **Microcontroller** → assembly, içinde Power Module var
- **Power Module** → assembly, içinde Capacitor ve Voltage Regulator var
- Bu yapıda plugin 3 seviye derinliğe inerek tüm hammaddeleri tespit ediyor

Her iki senaryo da README'de detaylıca anlatılıyor.

---

## Bonus özellikler

Ödevde belirtilen bonus özelliklerden hangilerini yaptım:

| Bonus | Yaptım mı | Not |
|-------|:---------:|-----|
| Docker ile hızlı kurulum | ✅ | Ana kurulum yöntemi olarak seçtim |
| Unit test | ✅ | 8 test, mock tabanlı, pytest ile |
| Multi-level BOM | ✅ | Recursive traversal, circular koruma dahil |
| CSV export | ✅ | UrlsMixin ile custom endpoint, Excel uyumlu |
| Satın alma önerisi | ❌ | Ana özellik için scope'u dar tuttum |
| Ekran görüntüsü/video | — | Teslimle eklenecek |

---

## Karşılaştığım zorluklar

**Event ismi yanlışıydı** — Başta `build_buildorder_created` diye uydurulmuş bir event ismini kullandım. InvenTree böyle bir event fırlatmıyordu. Kaynak koda bakarak doğru ismi buldum: `build_build.created`.

**Log seviyeleri** — `logger.info()` hiç görünmüyordu. InvenTree log seviyesi WARNING'e ayarlı, info (20) altında kalıyordu. Çözüm: `logger.warning()` kullanmak.

**Note ekleme zamanlaması** — ValidationMixin save'den önce çalışıyor, yeni order'ın `pk`'sı yok. EventMixin'i ekleyerek post-save note yazmayı çözdüm.

**Global event ve URL ayarları kapalıydı** — InvenTree'de plugin event ve URL sistemleri varsayılan olarak kapalı. İkisini de manuel açmak gerekiyor, README'ye yazdım.

**CSV export auth sorunu** — Plugin URL'lerine tarayıcıdan erişince 401 alıyordum. InvenTree'nin oturum cookie'si ile erişince düzeldi. URL'lerin authentication gerektirdiğini README'de belirttim.