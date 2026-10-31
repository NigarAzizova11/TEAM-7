"""Azərbaycan hərfləri üçün axtarış normallaşdırması."""

_FOLD = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "ə": "e",
        "Ə": "e",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ç": "c",
        "Ç": "c",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
    }
)


def fold_az(text: str) -> str:
    """Axtarış üçün normallaşdırma: Azərbaycan hərflərini latın bazasına endirir və kiçik hərfə çevirir.

    Məs. "Əhmədli" -> "ehmedli", "İçərişəhər" -> "iceriseher".
    İstifadəçi "ə" əvəzinə "e" yazsa da nəticə tapılsın deyə həm saxlanan ad, həm sorğu eyni qaydada normallaşır.
    """
    return " ".join(text.translate(_FOLD).lower().split())
