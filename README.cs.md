# Překladač obrazovky pro Linux

Překlad textu na obrazovce pro Linux — to, co dělá Android, když podržíte
tlačítko domů a ťuknete na *Přeložit*. Označíte část obrazovky, text v ní se
rozpozná, **původní nápisy se vymažou, pozadí pod nimi se dopočítá** a na
jejich místo se vysází překlad.

Vzniklo kvůli anglickým memům na X.com, které jde jinak přeložit jen ručním
opisováním.

## Jak to funguje

| Krok | Nástroj |
|---|---|
| Záchyt oblasti | XDG Desktop Portal — funguje na Waylandu i X11 |
| Rozpoznání textu | RapidOCR (PaddleOCR v ONNX), lokálně na procesoru |
| Překlad | DeepL API |
| Vymazání originálu | OpenCV inpainting (Telea) |
| Sazba překladu | Pillow, dodrží velikost, natočení i zarovnání originálu |

Průchod trvá zhruba **1 sekundu** na výřez a 4 sekundy na celou 4K obrazovku.
Ven jde jen rozpoznaný text — OCR běží u vás.

Text, který už je v cílovém jazyce, se přeskakuje, takže na české stránce se
přeloží jen anglické kousky.

## Instalace

```bash
./install.sh
```

Nepotřebuje `sudo`. Založí virtuální prostředí, spouštěč v nabídce aplikací,
ikonu v liště spouštěnou s relací a zkratku `Ctrl+Print`.

Systémové závislosti (na Ubuntu bývají už přítomné):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
                 gir1.2-ayatanaappindicator3-0.1
```

## Nastavení

Otevře se z ikony v liště, nebo příkazem:

```bash
.venv/bin/python main.py --settings
```

Zadává se tu cílový jazyk a **DeepL API klíč** (zdarma na
<https://www.deepl.com/pro-api>, bezplatný tarif dává 500 000 znaků měsíčně).
Klíč se ukládá do klíčenky systému, ne do konfiguračního souboru.

## Použití

* `Ctrl+Print`, nebo ikona v liště → *Přeložit oblast…*
* v okně výsledku: podržený mezerník ukáže originál, `Ctrl+C` kopíruje,
  `Ctrl+S` uloží

## Bez grafického rozhraní

```bash
.venv/bin/python -m translatorscreener.cli --image snimek.png --out preklad.png
.venv/bin/python -m translatorscreener.cli --translator mock   # bez API klíče
```

## Známá omezení

* OCR model je anglicko-čínský a **nečte diakritiku** („Hlavní stránka“ přečte
  jako „Hlavni stranka“). Při překladu *do* těchto jazyků to nevadí, protože
  takový text se stejně přeskakuje, ale opačný směr funguje špatně.
* Inpainting je klasický (Telea). Na jednobarevném a mírně členitém pozadí je
  výsledek nerozeznatelný od originálu, přes složitou fotografii zůstane
  rozmazaná stopa. Ostřejší by byl model LaMa za cenu ~200 MB a sekundy navíc.
* Vícesloupcový text a kurzíva se nerozpoznají.

## Licence

Apache License 2.0 — viz [LICENSE](LICENSE).
