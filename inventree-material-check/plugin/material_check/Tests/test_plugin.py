"""
MaterialCheckPlugin için unit testler.

Plugin'in core mantığını (eksik hesaplama) izole olarak test eder.
Mantık burada bağımsız bir fonksiyon olarak yazılmıştır, plugin'deki
versiyonu ile birebir aynıdır.
"""

from unittest.mock import MagicMock


# ----------------------------------------------------------------------
# Test edilen mantık — plugin.py'deki _calculate_shortages'in aynısı
# ----------------------------------------------------------------------

def calculate_shortages(build, use_allocated_stock, allow_negative_stock):
    """Plugin'deki _calculate_shortages mantığının izole versiyonu."""
    shortages = []
    bom_items = build.part.bom_items.all()

    for bom_item in bom_items:
        required = int(bom_item.quantity * build.quantity)

        if use_allocated_stock:
            available = int(bom_item.sub_part.available_stock)
        else:
            available = int(bom_item.sub_part.total_stock)

        if not allow_negative_stock:
            available = max(available, 0)

        shortage = required - available

        if shortage > 0:
            shortages.append({
                "part": bom_item.sub_part.name,
                "required": required,
                "available": available,
                "shortage": shortage,
            })

    return shortages


# ----------------------------------------------------------------------
# Mock üretici fonksiyonlar
# ----------------------------------------------------------------------

def make_bom_item(name, quantity, available_stock, total_stock=None):
    """Sahte bir BOM item üretir."""
    item = MagicMock()
    item.quantity = quantity
    item.sub_part.name = name
    item.sub_part.available_stock = available_stock
    item.sub_part.total_stock = total_stock if total_stock is not None else available_stock
    return item


def make_build(quantity, bom_items):
    """Sahte bir Build Order üretir."""
    build = MagicMock()
    build.quantity = quantity
    build.part.bom_items.all.return_value = bom_items
    return build


# ----------------------------------------------------------------------
# Asıl testler
# ----------------------------------------------------------------------

def test_basic_sanity():
    """En basit test — pytest çalışıyor mu?"""
    assert 1 + 1 == 2


def test_no_shortage_when_stock_sufficient():
    """Yeterli stok varsa eksik liste boş döner."""
    bom = [make_bom_item("R1", quantity=10, available_stock=500)]
    build = make_build(quantity=20, bom_items=bom)

    # 10 × 20 = 200 lazım, stokta 500 → eksik yok
    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=False)
    assert result == []


def test_shortage_detected_when_stock_insufficient():
    """Eksik varsa listede görünür ve miktar doğru hesaplanır."""
    bom = [make_bom_item("C1", quantity=5, available_stock=80)]
    build = make_build(quantity=20, bom_items=bom)

    # 5 × 20 = 100 lazım, stokta 80 → 20 eksik
    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=False)
    assert len(result) == 1
    assert result[0]["part"] == "C1"
    assert result[0]["shortage"] == 20


def test_multiple_shortages():
    """Birden fazla eksik varsa hepsi listede olur."""
    bom = [
        make_bom_item("R1", quantity=10, available_stock=500),   # yeterli
        make_bom_item("C1", quantity=5, available_stock=80),     # eksik
        make_bom_item("MCU1", quantity=1, available_stock=0),    # eksik
    ]
    build = make_build(quantity=20, bom_items=bom)

    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=False)
    assert len(result) == 2
    part_names = [s["part"] for s in result]
    assert "C1" in part_names
    assert "MCU1" in part_names


def test_negative_stock_clamped_to_zero_when_disallowed():
    """ALLOW_NEGATIVE_STOCK=False iken negatif stok 0 sayılır."""
    bom = [make_bom_item("MCU1", quantity=1, available_stock=-10)]
    build = make_build(quantity=5, bom_items=bom)

    # -10 stok 0 sayılır, 5 lazım → 5 eksik
    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=False)
    assert result[0]["available"] == 0
    assert result[0]["shortage"] == 5


def test_negative_stock_counted_when_allowed():
    """ALLOW_NEGATIVE_STOCK=True iken negatif stok hesaba katılır."""
    bom = [make_bom_item("MCU1", quantity=1, available_stock=-10)]
    build = make_build(quantity=5, bom_items=bom)

    # -10 stok olduğu gibi alınır, 5 lazım → 5 - (-10) = 15 eksik
    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=True)
    assert result[0]["available"] == -10
    assert result[0]["shortage"] == 15


def test_use_allocated_stock_branch():
    """USE_ALLOCATED_STOCK=True iken available_stock kullanılır."""
    bom = [make_bom_item("R1", quantity=10, available_stock=30, total_stock=100)]
    build = make_build(quantity=5, bom_items=bom)

    # available_stock kullanılmalı → 30
    # 10 × 5 = 50 lazım, 30 var → 20 eksik
    result = calculate_shortages(build, use_allocated_stock=True, allow_negative_stock=False)
    assert result[0]["shortage"] == 20


def test_use_total_stock_branch():
    """USE_ALLOCATED_STOCK=False iken total_stock kullanılır."""
    bom = [make_bom_item("R1", quantity=10, available_stock=30, total_stock=100)]
    build = make_build(quantity=5, bom_items=bom)

    # total_stock kullanılmalı → 100
    # 10 × 5 = 50 lazım, 100 var → eksik yok
    result = calculate_shortages(build, use_allocated_stock=False, allow_negative_stock=False)
    assert result == []