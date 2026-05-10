# InvenTree'nin temel plugin class'ları ve mixin'leri
from plugin import InvenTreePlugin
from plugin.mixins import ValidationMixin, SettingsMixin

import logging

# Bu plugin'e ait log kanalı
logger = logging.getLogger("inventree")


class MaterialCheckPlugin(ValidationMixin, SettingsMixin, InvenTreePlugin):
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

    def validate_model_instance(self, instance, deltas=None):
        """
        InvenTree her model kaydedilirken bu method'u çağırır.
        Biz sadece Build Order'ları kontrol ediyoruz.
        """

        # Build modelini içeride import et (Django startup'ta sorun çıkarmamak için)
        from build.models import Build

        # Sadece Build Order'ları kontrol et, diğer modelleri yoksay
        if not isinstance(instance, Build):
            return

        # Kontrol kapalıysa hiçbir şey yapma
        if not self.get_setting("CHECK_ENABLED"):
            return

        # Build Order'ın hedef ürünü ve miktarı
        part = instance.part
        build_quantity = instance.quantity

        logger.warning(f"MaterialCheckPlugin: Build Order #{instance.pk} — {part.name} x {build_quantity} kontrol ediliyor...")

        # Bu ürünün BOM'unu oku
        bom_items = part.bom_items.all()

        # Eksik parçaları bu listeye toplayacağız
        shortages = []

        # Her BOM item için stok kontrolü yap
        for bom_item in bom_items:

            # Toplam lazım olan = birim başına miktar × üretim miktarı
            required = int(bom_item.quantity * build_quantity)

            # Kullanılabilir stoku ayara göre hesapla
            if self.get_setting("USE_ALLOCATED_STOCK"):
                # Allocated stock düşülmüş, gerçek kullanılabilir miktar
                available = int(bom_item.sub_part.available_stock)
            else:
                # Ham stok, allocated stock hesaba katılmaz
                available = int(bom_item.sub_part.total_stock)

            # Negatif stoka izin yoksa 0 alt sınır uygula
            if not self.get_setting("ALLOW_NEGATIVE_STOCK"):
                available = max(available, 0)

            # Eksik miktarı hesapla
            shortage = max(required - available, 0)

            # Eksik varsa listeye ekle
            if shortage > 0:
                shortages.append({
                    "part": bom_item.sub_part.name,
                    "required": required,
                    "available": available,
                    "shortage": shortage,
                })

        # Eksik yoksa dur, hiçbir şey yapma
        if not shortages:
            logger.warning(f"MaterialCheckPlugin: Tüm malzemeler yeterli.")
            return

        # Eksik raporu oluştur
        report_lines = [f"Build Order #{instance.pk} — Eksik malzemeler:"]
        for s in shortages:
            report_lines.append(
                f"  - {s['part']}: lazım {s['required']}, stokta {s['available']}, eksik {s['shortage']}"
            )
        report = "\n".join(report_lines)

        logger.warning(f"MaterialCheckPlugin:\n{report}")

        # Ayara göre karar ver
        if self.get_setting("CHECK_MODE") == "error":
            # Hata modu: order kaydedilmez
            self.raise_error(report)
        else:
            # Uyarı modu: order kaydedilir, sadece log yazılır
            # Not: Build Order'a note eklemek için instance.pk lazım
            # instance henüz kaydedilmediği için pk olmayabilir, bu yüzden sadece log yazıyoruz
            pass