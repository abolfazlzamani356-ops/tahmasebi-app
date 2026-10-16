import pytest
from helpers import (
    normalize_persian_text,
    get_persian_word_variants,
    safe_int,
    safe_float
)

@pytest.mark.unit
def test_normalize_empty_and_none():
    assert normalize_persian_text(None) == ""
    assert normalize_persian_text("") == ""
    assert normalize_persian_text("   ") == ""

@pytest.mark.unit
def test_normalize_arabic_yeh():
    # ي should be converted to ی
    assert normalize_persian_text("شيرآلات قهرمان") == "شیرآلات قهرمان"
    assert normalize_persian_text("روشويي كابينتي") == "روشویی کابینتی"

@pytest.mark.unit
def test_normalize_arabic_kaf():
    # ك should be converted to ک
    assert normalize_persian_text("سينك گرانيتي") == "سینک گرانیتی"
    assert normalize_persian_text("كابينت لوكس") == "کابینت لوکس"

@pytest.mark.unit
def test_normalize_alef_maqsura():
    # ى should be converted to ی
    assert normalize_persian_text("موسى") == "موسی"
    assert normalize_persian_text("حتى") == "حتی"

@pytest.mark.unit
def test_normalize_teh_marbuta():
    # ة and ۀ should be converted to ه
    assert normalize_persian_text("مجموعۀ فروشگاه") == "مجموعه فروشگاه"
    assert normalize_persian_text("دستگاه تهويه") == "دستگاه تهویه"

@pytest.mark.unit
def test_normalize_tashkeel_and_harakat_removal():
    # All vowel accents and tashkeel must be removed
    assert normalize_persian_text("شِیرآلاتِ قَهْرَمانْ") == "شیرآلات قهرمان"
    assert normalize_persian_text("طَهْماسِبیّ") == "طهماسبی"

@pytest.mark.unit
def test_normalize_zwnj_and_invisible_chars():
    # Zero width non-joiner \u200c converted to space, and \u200e, \u200f, \ufeff removed
    raw = "روشویی\u200cکابینتی\ufeff مدل\u200e رویال"
    normalized = normalize_persian_text(raw)
    assert "\ufeff" not in normalized
    assert "\u200e" not in normalized
    assert normalized == "روشویی کابینتی مدل رویال"

@pytest.mark.unit
def test_normalize_persian_digits_to_english():
    # ۰۱۲۳۴۵۶۷۸۹ -> 0123456789
    assert normalize_persian_text("کد کالا ۱۲۳۴۵") == "کد کالا 12345"
    assert normalize_persian_text("تلفن ۰۹۱۲۳۴۵۶۷۸۹") == "تلفن 09123456789"

@pytest.mark.unit
def test_normalize_arabic_digits_to_english():
    # ٠١٢٣٤٥٦٧٨٩ -> 0123456789
    assert normalize_persian_text("موديل ١٣٥") == "مودیل 135"

@pytest.mark.unit
def test_normalize_unify_alif():
    # When unify_alif=True, آ, أ, إ -> ا
    assert normalize_persian_text("آس اخوان", unify_alif=True) == "اس اخوان"
    assert normalize_persian_text("أحمد", unify_alif=True) == "احمد"

@pytest.mark.unit
def test_normalize_whitespace_collapsing():
    assert normalize_persian_text("  شیرآلات    قهرمان   مدل   کروم  ") == "شیرآلات قهرمان مدل کروم"

@pytest.mark.unit
def test_word_variants_basic():
    variants = get_persian_word_variants("سینک")
    assert "سینک" in variants
    # Arabic kaf variant should also be generated for robust DB search
    assert any("سينك" in v for v in variants)

@pytest.mark.unit
def test_word_variants_alif_variants():
    variants = get_persian_word_variants("آس")
    assert "آس" in variants
    assert "اس" in variants

@pytest.mark.unit
def test_word_variants_plural_and_suffixes():
    variants = get_persian_word_variants("شیرآلات")
    assert "شیرآلات" in variants
    assert any("شیرآل" in v or "شیرال" in v for v in variants)

@pytest.mark.unit
def test_safe_int_clean_integer():
    assert safe_int(12500) == 12500
    assert safe_int("4500000") == 4500000

@pytest.mark.unit
def test_safe_int_persian_and_arabic_digits():
    assert safe_int("۲۵۰۰۰۰") == 250000
    assert safe_int("٢٥٠٠٠٠") == 250000

@pytest.mark.unit
def test_safe_int_commas_and_spaces():
    assert safe_int("۴,۵۰۰,۰۰۰") == 4500000
    assert safe_int(" ۱, ۲۰۰, ۰۰۰ ") == 1200000

@pytest.mark.unit
def test_safe_int_persian_negative():
    assert safe_int("منفی ۵۰۰۰۰") == -50000
    assert safe_int("-۱۵۰۰۰") == -15000
    assert safe_int("−۲۰۰۰") == -2000

@pytest.mark.unit
def test_safe_int_float_string():
    # Float strings should truncate or parse cleanly without multiplying
    assert safe_int("15000.75") == 15000
    assert safe_int("۲۵۰.۵") == 250

@pytest.mark.unit
def test_safe_int_none_and_empty():
    assert safe_int(None, default=0) == 0
    assert safe_int("", default=0) == 0
    assert safe_int("   ", default=0) == 0
    assert safe_int(None, default=99) == 99

@pytest.mark.unit
def test_safe_int_boolean_and_invalid():
    assert safe_int(True) == 1
    assert safe_int(False) == 0
    assert safe_int("متن_نامعتبر", default=0) == 0

@pytest.mark.unit
def test_safe_float_clean_and_commas():
    assert safe_float("12500.5") == 12500.5
    assert safe_float("۱,۲۵۰.۵") == 1250.5
    assert safe_float("۲۵٫۵") == 25.5

@pytest.mark.unit
def test_safe_float_percentage():
    assert safe_float("18%") == 18.0
    assert safe_float("۱۸٪") == 18.0

@pytest.mark.unit
def test_safe_float_negative():
    assert safe_float("-15.5") == -15.5
    assert safe_float("منفی ۲٫۵") == -2.5

@pytest.mark.unit
def test_safe_float_fallback_and_none():
    assert safe_float(None, default=0.0) == 0.0
    assert safe_float("", default=1.5) == 1.5
    assert safe_float("abc", default=0.0) == 0.0
