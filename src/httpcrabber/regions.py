"""Chrome language tags and searchable region names."""

import argparse

from rich.table import Table

from httpcrabber.config import CYAN, console

# Tag, native language and region, search aliases in the supported CLI languages.
REGIONS = {
    "en-US": ("English · United States", "USA Америка США Stany Zjednoczone"),
    "en-GB": ("English · United Kingdom", "UK Britain Великобритания Wielka Brytania"),
    "ru-RU": ("Русский · Россия", "Russian Russia Rosja"),
    "pl-PL": ("Polski · Polska", "Polish Poland Польша польский"),
    "de-DE": ("Deutsch · Deutschland", "German Germany Германия Niemcy"),
    "fr-FR": ("Français · France", "French Франция Francja"),
    "es-ES": ("Español · España", "Spanish Spain Испания Hiszpania"),
    "pt-BR": ("Português · Brasil", "Portuguese Brazil Бразилия Brazylia"),
    "pt-PT": ("Português · Portugal", "Portuguese Португалия Portugalia"),
    "it-IT": ("Italiano · Italia", "Italian Italy Италия Włochy"),
    "uk-UA": ("Українська · Україна", "Ukrainian Ukraine Украина Ukraina"),
    "tr-TR": ("Türkçe · Türkiye", "Turkish Turkey Турция Turcja"),
    "ja-JP": ("日本語 · 日本", "Japanese Japan Япония Japonia"),
    "zh-CN": ("简体中文 · 中国", "Chinese China Китай Chiny"),
    "ko-KR": ("한국어 · 대한민국", "Korean South Korea Корея Korea"),
    "nl-NL": ("Nederlands · Nederland", "Dutch Netherlands Нидерланды Holandia"),
}


def locale_tag(value: str) -> str:
    value = value.strip().replace("_", "-").lower()
    for tag in REGIONS:
        if tag.lower() == value or tag.split("-")[0] == value:
            return tag
    raise argparse.ArgumentTypeError("Unknown locale. Run httpcrabber regions to list supported tags.")


def regions_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="httpcrabber regions", description="Search Chrome locales.")
    parser.add_argument("query", nargs="?", default="")
    query = parser.parse_args(argv).query.strip().casefold()
    table = Table("Locale", "Language · Region", header_style=CYAN, box=None)
    for tag, (label, aliases) in REGIONS.items():
        if query in f"{tag} {label} {aliases}".casefold():
            table.add_row(tag, label)
    if not table.row_count:
        console.print("No matching regions.")
        return 1
    console.print(table)
    return 0
