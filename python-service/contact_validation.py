"""Valida o formato dos contatos; não verifica existência ou titularidade."""

import re

AREA_CODES = set(
    "11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 "
    "41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 "
    "71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split()
)


def validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text in ("", "—"):
        return text
    if not re.fullmatch(r"\+?[\d\s().-]+", text, flags=re.ASCII):
        raise ValueError("Use um telefone, não um nome ou @usuário.")
    digits = re.sub(r"\D", "", text, flags=re.ASCII)
    international = text.startswith("+")
    brazil = not international or digits.startswith("55")
    if international and brazil:
        digits = digits[2:]
    if brazil:
        if digits[:2] not in AREA_CODES:
            raise ValueError("Confira o DDD brasileiro.")
        subscriber = digits[2:]
        valid_format = re.fullmatch(r"(?:9\d{8}|[2-5]\d{7})", subscriber, flags=re.ASCII)
        if not valid_format or len(set(subscriber)) == 1:
            raise ValueError("Use DDD + celular com 9 dígitos, ou telefone fixo com 8 dígitos.")
    elif (
        not re.fullmatch(r"[1-9]\d{7,14}", digits, flags=re.ASCII)
        or len(set(digits)) == 1
    ):
        raise ValueError("Use +código do país e número completo (8 a 15 dígitos).")
    return text


def validate_instagram(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text in ("", "—"):
        return text
    username = text.removeprefix("@")
    if (
        not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username)
        or username.startswith(".")
        or username.endswith(".")
        or ".." in username
        or (username.isdigit() and not text.startswith("@"))
    ):
        raise ValueError("Use o @usuário do Instagram, sem espaços, links ou telefone.")
    return text
