
# **Ödev: InvenTree Build Order Material Check Plugin**

## Amaç

InvenTree üzerinde yeni bir **Build Order** oluşturulduğunda, ilgili ürünün **BOM (Bill of Materials)** yapısı analiz edilerek gerekli malzemelerin stok yeterliliği otomatik kontrol edilmelidir.

Eğer stokta bulunmayan veya eksik olan malzemeler varsa kullanıcı bilgilendirilmelidir.

---

## Senaryo

Örneğin:

Bir ürün için BOM:

| Parça | Gereken |
| ----- | ------: |
| R1    |      10 |
| C1    |       5 |
| MCU1  |       1 |

Build Order Quantity = 20

Toplam ihtiyaç:

* R1 → 200
* C1 → 100
* MCU1 → 20

Stok:

* R1 → 500 ✅
* C1 → 80 ❌
* MCU1 → 0 ❌

Beklenen sonuç:

Eksik parçalar kullanıcıya raporlanmalıdır.

---

# Beklenenler

### 1. Lokal kurulum

Lokal ortamda InvenTree kurulumu yapılmalı.

---

### 2. Plugin geliştirme

Plugin ayrı bir Python paketi olarak geliştirilmeli.

---

### 3. Event yakalama

Plugin, yeni Build Order oluşturulduğu anda otomatik tetiklenmeli.

---

### 4. BOM analizi

Build Order’a bağlı ürünün BOM bilgisi okunmalı.

---

### 5. Stok kontrolü

Her BOM item için aşağıdaki hesaplama yapılmalı:

```python
required = bom_quantity * build_quantity
available = stock_quantity
shortage = required - available
```

Eksik veya bulunmayan parçalar tespit edilmeli.

---

### 6. Kullanıcı bilgilendirme

Eksik malzemeler kullanıcıya gösterilmeli.

Gösterim yöntemi adayın tercihine bırakılmıştır. Örneğin:

* Validation error
* UI notification
* Log kaydı
* Build order note/comment

---

### 7. Plugin ayarları

Plugin içerisinde aşağıdaki ayarlar tanımlanmalı:

* Kontrol aktif/pasif
* Warning veya Error modu
* Negatif stok kontrolü
* Allocated stock dahil/haric

---

### 8. Kod kalitesi

Kod okunabilir, düzenli ve yorumlanabilir olmalı.

---

### 9. Dokümantasyon

README dosyasında aşağıdakiler açıklanmalı:

* Kurulum
* Plugin aktivasyonu
* Kullanım senaryosu
* Test adımları

---

### 10. Test verisi

Plugin’in çalışmasını gösterecek örnek:

* Part
* BOM
* Stock
* Build Order

demo verisi hazırlanmalı.

---

# Bonus Puan

Aşağıdakiler zorunlu değildir ancak artı puan sağlar:

* Unit test
* Docker ile hızlı kurulum
* Eksik malzemeler için CSV export
* Multi-level BOM desteği
* Satın alma önerisi oluşturma
* Ekran görüntüsü veya kısa demo video

---

# Teslim Formatı

Adaylardan aşağıdakiler beklenmektedir:

* Git repository linki (örn. GitLab veya GitHub)
* README.md
* Kurulum adımları
* Kullanım açıklaması
* Varsa demo video / ekran görüntüsü
* Kısa teknik açıklama:
  **“Bu plugin’i nasıl tasarladım?”**


