# InvenTree'nin temel plugin class'ları ve mixin'leri
from plugin import InvenTreePlugin
from plugin.mixins import ValidationMixin, SettingsMixin, EventMixin, UrlsMixin
from django.urls import path
from django.http import HttpResponse
import csv
import logging
import math

# Bu plugin'e ait log kanalı
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
        Verilen Build Order için eksik malzeme raporunu CSV olarak döner.
        """
        from build.models import Build

        try:
            build = Build.objects.get(pk=build_id)
        except Build.DoesNotExist:
            return HttpResponse("Build Order bulunamadı", status=404)

        shortages = self._calculate_shortages(build)

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="build_{build_id}_shortages.csv"'

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
        # Önce BOM'u tara, her seviyedeki ihtiyaçları topla (aynı parça birden fazla kez gelebilir)
        raw_items = self._traverse_bom(instance.part, instance.quantity, visited=set())

        # Aynı parçaları birleştir — miktarları topla
        merged = {}
        for item in raw_items:
            name = item["part"]
            if name in merged:
                merged[name]["required"] += item["required"]
            else:
                merged[name] = item.copy()

        # Eksikleri yeniden hesapla (required değişti çünkü)
        result = []
        for item in merged.values():
            item["shortage"] = max(item["required"] - item["available"], 0)
            if item["shortage"] > 0:
                result.append(item)

        return result

    def _traverse_bom(self, part, quantity, visited):
        """
        BOM'u recursive olarak tarar.
        - Sub-assembly ise içine girer, miktarı çarparak ilerler
        - Leaf part ise stok kontrolü yapar
        - visited set'i circular BOM döngüsünü önler
        """
        if part.pk in visited:
            logger.warning("MaterialCheckPlugin: Circular BOM tespit edildi — Part #%s atlandı.", part.pk)
            return []

        visited.add(part.pk)
        shortages = []

        for bom_item in part.bom_items.all():
            sub_part = bom_item.sub_part
            required_quantity = bom_item.quantity * quantity

            if sub_part.assembly:
                # Sub-assembly: recursive olarak içine gir
                sub_shortages = self._traverse_bom(sub_part, required_quantity, visited)
                shortages.extend(sub_shortages)
            else:
                # Leaf part: stok kontrolü yap
                required = math.ceil(required_quantity)

                if self.get_setting("USE_ALLOCATED_STOCK"):
                    available = int(sub_part.available_stock)
                else:
                    available = int(sub_part.total_stock)

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

    NOTE_START = "--- MATERIAL CHECK START ---"
    NOTE_END   = "--- MATERIAL CHECK END ---"

    def _write_note(self, instance, report):
        """
        Raporu Build Order notuna yazar.
        Önceki material check bloğu varsa yerinde günceller, yoksa sona ekler.
        """
        existing = instance.notes or ""
        new_block = f"{self.NOTE_START}\n{report}\n{self.NOTE_END}"

        if self.NOTE_START in existing:
            # Önceki raporu bul ve değiştir
            start = existing.index(self.NOTE_START)
            end   = existing.index(self.NOTE_END) + len(self.NOTE_END)
            instance.notes = existing[:start] + new_block + existing[end:]
        else:
            # İlk kez yazılıyor, sona ekle
            separator = "\n\n" if existing.strip() else ""
            instance.notes = existing + separator + new_block

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
        Build Order kaydedilmeden önce çalışır.
        Error modunda eksik varsa kaydı bloklar.
        """
        from build.models import Build

        # Sadece Build Order'ları kontrol et
        if not isinstance(instance, Build):
            return

        if not self.get_setting("CHECK_ENABLED"):
            return

        # Sadece error modunda bloklamak için kontrol yap
        # Warning modu event tarafında çalışır
        if self.get_setting("CHECK_MODE") != "error":
            return

        shortages = self._calculate_shortages(instance)
        if not shortages:
            return

        # Eksik var ve error modu açık — bloklayarak hata fırlat
        report = self._format_report(instance, shortages)
        logger.warning(f"MaterialCheckPlugin (BLOCKED):\n{report}")
        self.raise_error(report)

    # ----------------------------------------------------------------------
    # EventMixin: kayıt edildikten SONRA çalışır, warning modunda not ekler
    # ----------------------------------------------------------------------

    TRACKED_EVENTS = {"build_build.created", "build_build.saved"}

    def process_event(self, event, *args, **kwargs):
        """
        Build Order oluşturulduğunda veya güncellendiğinde çalışır.
        Warning modunda eksikler varsa Build Order notunu yazar/günceller.
        """
        if event not in self.TRACKED_EVENTS:
            return

        if not self.get_setting("CHECK_ENABLED"):
            return

        if self.get_setting("CHECK_MODE") != "warning":
            return

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

        report = self._format_report(instance, shortages)
        logger.warning("MaterialCheckPlugin (WARNING):\n%s", report)
        self._write_note(instance, report)