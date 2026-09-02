from httpcrabber.config import settings
from httpcrabber.i18n import LANGUAGES, STRINGS, t


def test_all_languages_have_identical_keys():
    keysets = {lang: set(STRINGS[lang]) for lang in LANGUAGES}
    ref = keysets["en"]
    for lang, keys in keysets.items():
        assert keys == ref, f"{lang}: missing {ref - keys}, extra {keys - ref}"


def test_no_empty_strings():
    for lang in LANGUAGES:
        for key, value in STRINGS[lang].items():
            assert value.strip(), f"{lang}.{key} is empty"


def test_placeholders_match_across_languages():
    import re

    for key in STRINGS["en"]:
        expected = set(re.findall(r"{(\w+)}", STRINGS["en"][key]))
        for lang in LANGUAGES:
            assert set(re.findall(r"{(\w+)}", STRINGS[lang][key])) == expected, f"{lang}.{key}"


def test_t_formats_and_switches_language():
    settings.lang = "en"
    assert t("chrome_skip", port=8080).endswith("127.0.0.1:8080")
    settings.lang = "ru"
    assert "8080" in t("chrome_skip", port=8080)
    assert t("no_such_key") == "no_such_key"
