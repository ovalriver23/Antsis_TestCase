# InvenTree'nin temel plugin class'ı ve kullanılan mixin'ler
from plugin import InvenTreePlugin
from plugin.mixins import (
    ValidationMixin,  # Build Order kaydedilmeden önce stok kontrolü yapar (error modu)
    SettingsMixin,    # Plugin ayarlarını InvenTree arayüzüne açar
    EventMixin,       # Build Order kaydedildikten sonra note yazar (warning modu)
    UrlsMixin,        # CSV export için özel URL endpoint'i ekler
)
from django.urls import path
from django.http import HttpResponse
import csv
import logging
import math  # math.ceil: gerekli miktarı her zaman yukarı yuvarla, eksik hesaplama

# InvenTree'nin kendi log sistemiyle entegre log kanalı
logger = logging.getLogger("inventree")


class MaterialCheckPlugin(ValidationMixin, SettingsMixin, EventMixin, UrlsMixin, InvenTreePlugin):
    """
    Build Order kaydedilirken BOM'daki malzemelerin
    stok yeterliliğini kontrol eden plugin.
    """

    # Plugin'in temel bilgileri
    NAME        = "MaterialCheckPlugin"
    TITLE       = "Build Order Material Check"
    DESCRIPTION = "Checks material availability when a Build Order is created"
    VERSION     = "1.0.0"
    AUTHOR      = "Tuana Melisa Aksoy"

    # Kullanıcının arayüzden değiştirebileceği ayarlar
    SETTINGS = {
        "CHECK_ENABLED": {
            "name": "Enable Check",
            "description": "Run material check when a Build Order is created",
            "default": True,
            "validator": bool,
        },
        "CHECK_MODE": {
            "name": "Check Mode",
            "description": "Warning: order is created but user is notified. Error: order is blocked",
            "default": "warning",
            "choices": [
                ("warning", "Warning"),
                ("error", "Error"),
            ],
        },
        "ALLOW_NEGATIVE_STOCK": {
            "name": "Allow Negative Stock",
            "description": "Allow stock quantity to go below zero",
            "default": False,
            "validator": bool,
        },
        "USE_ALLOCATED_STOCK": {
            "name": "Consider Allocated Stock",
            "description": "Subtract stock allocated to other orders from available quantity",
            "default": True,
            "validator": bool,
        },
    }

    # ----------------------------------------------------------------------
    # UrlsMixin: özel URL endpoint'leri
    # CSV export için /plugin/materialcheckplugin/export/<build_id>/
    # ----------------------------------------------------------------------
    def setup_urls(self):
        return [
            path("export/<int:build_id>/", self.export_csv, name="export-csv"),
        ]

    def export_csv(self, request, build_id):
        """
        Verilen Build Order için eksik malzeme raporunu CSV dosyası olarak döner.
        Erişim: /plugin/materialcheckplugin/export/<build_id>/
        """
        # Build modeli burada import ediliyor — Django startup sırasında circular import olmaması için
        from build.models import Build

        try:
            build = Build.objects.get(pk=build_id)
        except Build.DoesNotExist:
            return HttpResponse("Build Order bulunamadı", status=404)

        shortages = self._calculate_shortages(build)

        # utf-8-sig: Excel'in Türkçe karakterleri (ş, ı, ğ vb.) doğru okuması için BOM karakteri ekler
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="build_{build_id}_shortages.csv"'

        # delimiter=";": Excel varsayılan olarak ";" bekler, "," ile kolonlar ayrılmaz
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Build Order", "Part", "Required", "Available", "Shortage"])
        for s in shortages:
            writer.writerow([build_id, s["part"], s["required"], s["available"], s["shortage"]])

        return response

    # ----------------------------------------------------------------------
    # Yardımcı method: Build Order için eksik malzemeleri hesaplar
    # Hem validation hem event tarafında kullanılır
    # ----------------------------------------------------------------------
    def _calculate_shortages(self, instance):
        """
        Verilen Build Order için tüm BOM seviyelerini tarar ve eksik parça listesini döner.
        Aynı parça farklı seviyelerde geçerse miktarları toplanır.
        Eksik yoksa boş liste döner.
        """
        # Tüm BOM seviyelerini recursive olarak tara
        # Aynı parça farklı sub-assembly'lerde tekrar geçebileceğinden ham liste olarak al
        raw_items = self._traverse_bom(instance.part, instance.quantity, visited=set())

        # Aynı parçanın birden fazla seviyede geçtiği durumda miktarları topla
        # Örnek: R1 hem ana BOM'da hem sub-assembly BOM'unda geçiyorsa toplam ihtiyaç birleştirilir
        merged = {}
        for item in raw_items:
            name = item["part"]
            if name in merged:
                merged[name]["required"] += item["required"]
            else:
                merged[name] = item.copy()

        # Birleştirme sonrası toplam required değiştiği için shortage'ı yeniden hesapla
        result = []
        for item in merged.values():
            item["shortage"] = max(item["required"] - item["available"], 0)
            if item["shortage"] > 0:
                result.append(item)

        return result

    def _traverse_bom(self, part, quantity, visited):
        """
        BOM ağacını recursive olarak dolaşır.
        - sub_part.assembly == True  → bu parçanın da kendi BOM'u var, içine gir
        - sub_part.assembly == False → hammadde, stok kontrolü yap
        - visited set'i: A→B→A gibi döngüsel BOM tanımlarında sonsuz döngüyü önler
        """
        # Bu parçayı daha önce ziyaret ettik — circular BOM, atla
        if part.pk in visited:
            logger.warning("MaterialCheckPlugin: Circular BOM tespit edildi — Part #%s atlandı.", part.pk)
            return []

        visited.add(part.pk)
        shortages = []

        for bom_item in part.bom_items.all():
            sub_part = bom_item.sub_part
            # Her seviyede miktar çarpılarak aşağı aktarılır
            # Örnek: Ana BOM'da 2 adet Sub-Assembly, Sub-Assembly'de 5 adet R1 → 10 adet R1 gerekli
            required_quantity = bom_item.quantity * quantity

            if sub_part.assembly:
                # Sub-assembly: kendi BOM'unu çözmek için recursive çağrı
                sub_shortages = self._traverse_bom(sub_part, required_quantity, visited)
                shortages.extend(sub_shortages)
            else:
                # Hammadde: stok kontrolü yap
                # math.ceil: 0.5 birim × 3 adet = 1.5 → 2 alınmalı, hiçbir zaman eksik hesaplama yapma
                required = math.ceil(required_quantity)

                if self.get_setting("USE_ALLOCATED_STOCK"):
                    # Başka emirlere ayrılmış stok düşülmüş, gerçek kullanılabilir miktar
                    available = int(sub_part.available_stock)
                else:
                    # Ham stok, ayrılmış stok hesaba katılmaz
                    available = int(sub_part.total_stock)

                # ALLOW_NEGATIVE_STOCK kapalıysa, negatif stoku 0 say
                # Açıksa negatif değer olduğu gibi kalır ve daha büyük eksik hesaplanır
                if not self.get_setting("ALLOW_NEGATIVE_STOCK"):
                    available = max(available, 0)

                shortage = max(required - available, 0)

                if shortage > 0:
                    shortages.append({
                        "part": sub_part.name,
                        "required": required,
                        "available": available,
                        "shortage": shortage,
                    })

        return shortages

    # ----------------------------------------------------------------------
    # Yardımcı method: Build Order notuna raporu yazar veya günceller
    # ----------------------------------------------------------------------

    # Build Order notunda plugin'in yazdığı bloğu bulmak için marker'lar
    # Her güncelleme aynı bloğu bulup yerinde değiştirir — kullanıcının kendi notlarına dokunmaz
    NOTE_START = "--- MATERIAL CHECK START ---"
    NOTE_END   = "--- MATERIAL CHECK END ---"

    def _write_note(self, instance, report):
        """
        Raporu Build Order'ın notes alanına yazar.
        - İlk kez yazılıyorsa mevcut notların sonuna ekler
        - Daha önce yazılmışsa START/END marker'ları arasındaki bloğu günceller
        """
        existing  = instance.notes or ""
        new_block = f"{self.NOTE_START}\n{report}\n{self.NOTE_END}"

        if self.NOTE_START in existing:
            # Önceki raporu marker'larla bul ve yerinde değiştir
            # Bu sayede Build Order her güncellendiğinde rapor birikmez, sadece güncellenir
            start = existing.index(self.NOTE_START)
            end   = existing.index(self.NOTE_END) + len(self.NOTE_END)
            instance.notes = existing[:start] + new_block + existing[end:]
        else:
            # İlk kez yazılıyor — mevcut not varsa araya boşluk koy, yoksa direkt yaz
            separator = "\n\n" if existing.strip() else ""
            instance.notes = existing + separator + new_block

        # update_fields ile sadece notes alanı kaydedilir
        # Böylece başka field'lara bağlı signal'lar gereksiz yere tetiklenmez
        instance.save(update_fields=["notes"])
        logger.info("MaterialCheckPlugin: Build Order #%s notu güncellendi.", instance.pk)

    # ----------------------------------------------------------------------
    # Yardımcı method: Eksik listesini okunabilir bir rapor metnine çevirir
    # ----------------------------------------------------------------------
    def _format_report(self, instance, shortages):
        """Eksik listesini okunabilir bir metne çevirir."""
        lines = [f"Build Order #{instance.pk} — Eksik malzemeler:"]
        for s in shortages:
            lines.append(
                f"  - {s['part']}: lazım {s['required']}, stokta {s['available']}, eksik {s['shortage']}"
            )
        return "\n".join(lines)

    # ----------------------------------------------------------------------
    # ValidationMixin: kayıt edilmeden ÖNCE çalışır, error modunda bloklar
    # ----------------------------------------------------------------------
    def validate_model_instance(self, instance, deltas=None):
        """
        InvenTree her model kaydedilmeden önce bu method'u çağırır.
        Sadece error modunda aktif — eksik malzeme varsa Build Order'ın kaydedilmesini engeller.
        Warning modu buraya girmez, o EventMixin tarafında çalışır.
        """
        # Build modeli burada import ediliyor — Django startup sırasında circular import olmaması için
        from build.models import Build

        # ValidationMixin tüm modeller için tetiklenir — sadece Build Order'larla ilgileniyoruz
        if not isinstance(instance, Build):
            return

        if not self.get_setting("CHECK_ENABLED"):
            return

        # Error modunda: kayıt bloklanır
        # Warning modunda: kayıt geçer, note EventMixin tarafında yazılır
        if self.get_setting("CHECK_MODE") != "error":
            return

        shortages = self._calculate_shortages(instance)
        if not shortages:
            return

        report = self._format_report(instance, shortages)
        logger.warning("MaterialCheckPlugin (BLOCKED):\n%s", report)
        # raise_error → ValidationMixin'in kendi wrapper'ı, Django ValidationError fırlatır
        self.raise_error(report)

    # ----------------------------------------------------------------------
    # EventMixin: kayıt edildikten SONRA çalışır, warning modunda not ekler
    # ----------------------------------------------------------------------

    # process_event'in dinleyeceği event'ler
    # "created" → yeni Build Order oluşturuldu
    # "saved"   → mevcut Build Order güncellendi (miktar değişikliği gibi)
    # Her ikisinde de stok kontrolü tekrarlanır, note güncellenir
    TRACKED_EVENTS = {"build_build.created", "build_build.saved"}

    def process_event(self, event, *args, **kwargs):
        """
        Build Order DB'ye kaydedildikten SONRA tetiklenir.
        Bu noktada instance.pk kesinlikle mevcuttur, Build Order notuna yazılabilir.
        Warning modunda eksikler varsa log'a yazar ve notes alanını günceller.
        """
        if event not in self.TRACKED_EVENTS:
            return

        if not self.get_setting("CHECK_ENABLED"):
            return

        # Error modunda bu kod hiç çalışmaz — order zaten validate_model_instance'da bloklandı
        if self.get_setting("CHECK_MODE") != "warning":
            return

        # Event kwargs içinde Build Order'ın pk'si gelir
        build_id = kwargs.get("id")
        if not build_id:
            return

        from build.models import Build
        try:
            instance = Build.objects.get(pk=build_id)
        except Build.DoesNotExist:
            return

        shortages = self._calculate_shortages(instance)

        if not shortages:
            logger.info("MaterialCheckPlugin: Build Order #%s — tüm malzemeler yeterli.", instance.pk)
            return

        # 1. Log'a yaz — InvenTree admin panelinden takip edilebilir
        report = self._format_report(instance, shortages)
        logger.warning("MaterialCheckPlugin (WARNING):\n%s", report)

        # 2. Build Order notuna yaz — kullanıcı order detay sayfasından görür
        self._write_note(instance, report)