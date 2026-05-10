# InvenTree'nin temel plugin class'ları ve mixin'leri
from plugin import InvenTreePlugin
from plugin.mixins import ValidationMixin, SettingsMixin, EventMixin

import logging

# Bu plugin'e ait log kanalı
logger = logging.getLogger("inventree")


class MaterialCheckPlugin(ValidationMixin, SettingsMixin, EventMixin, InvenTreePlugin):
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
    # Yardımcı method: Build Order için eksik malzemeleri hesaplar
    # Hem validation hem event tarafında kullanılır
    # ----------------------------------------------------------------------
    def _calculate_shortages(self, instance):
        """
        Verilen Build Order için BOM'u tarar ve eksik parça listesini döner.
        Eksik yoksa boş liste döner.
        """
        shortages = []

        # Bu ürünün BOM'unu oku
        bom_items = instance.part.bom_items.all()

        for bom_item in bom_items:
            # Toplam lazım olan = birim başına miktar × üretim miktarı
            required = int(bom_item.quantity * instance.quantity)

            # Kullanılabilir stoku ayara göre hesapla
            if self.get_setting("USE_ALLOCATED_STOCK"):
                available = int(bom_item.sub_part.available_stock)
            else:
                available = int(bom_item.sub_part.total_stock)

            # Negatif stoka izin yoksa 0 alt sınır uygula
            if not self.get_setting("ALLOW_NEGATIVE_STOCK"):
                available = max(available, 0)

            # Eksik miktarı hesapla
            shortage = required - available

            # Sadece eksik olanları listele
            if shortage > 0:
                shortages.append({
                    "part": bom_item.sub_part.name,
                    "required": required,
                    "available": available,
                    "shortage": shortage,
                })

        return shortages

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
    def process_event(self, event, *args, **kwargs):
        """
        Build Order kaydedildikten sonra çalışır.
        Warning modunda eksikler varsa Build Order'ın notes alanına yazar.
        """
        # Sadece Build Order oluşturma event'i ile ilgileniyoruz
        if event != "build_build.created":
            return

        if not self.get_setting("CHECK_ENABLED"):
            return

        # Sadece warning modunda not yaz
        # Error modu zaten validation tarafında çalıştı, buraya zaten gelmedi (bloklandı)
        if self.get_setting("CHECK_MODE") != "warning":
            return

        # Build Order'ı veritabanından çek (artık kayıtlı, pk var)
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
            logger.info(f"MaterialCheckPlugin: Build Order #{instance.pk} — tüm malzemeler yeterli.")
            return

        # Eksik var, log'a yaz ve notes alanına ekle
        report = self._format_report(instance, shortages)
        logger.warning(f"MaterialCheckPlugin (WARNING):\n{report}")

        # Build Order'ın notes alanına raporu ekle
        existing_notes = instance.notes or ""
        instance.notes = existing_notes + "\n\n---\n" + report
        instance.save(update_fields=["notes"])