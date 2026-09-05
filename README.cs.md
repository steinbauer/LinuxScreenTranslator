# Překladač obrazovky pro Linux

Překlad textu na obrazovce pro Linux — to, co dělá Android, když podržíte
tlačítko domů a ťuknete na *Přeložit*. Označíte část obrazovky, text v ní se
rozpozná, **původní nápisy se vymažou, pozadí pod nimi se dopočítá** a na
jejich místo se vysází překlad.

Vzniklo kvůli anglickým memům na X.com, které jde jinak přeložit jen ručním
opisováním.

## Jak to vypadá

Vlevo původní snímek, vpravo výsledek. Nic z toho není naaranžované — každá
dvojice vyšla z nástroje tak, jak je.

**Angličtina → španělština.** Písmo si nechává obtažení a plameny za ním se
dopočítají tam, kde býval text.

| | |
|---|---|
| ![Originál](docs/examples/spider-before.jpg) | ![Překlad](docs/examples/spider-after.jpg) |

**Němčina → francouzština.** Zdrojový jazyk se rozpozná, nenastavuje se.

| | |
|---|---|
| ![Originál](docs/examples/monkey-before.jpg) | ![Překlad](docs/examples/monkey-after.jpg) |

**Angličtina → němčina.** Titulky vypálené do videa, přeložené na místě.

| | |
|---|---|
| ![Originál](docs/examples/subtitles-before.jpg) | ![Překlad](docs/examples/subtitles-after.jpg) |

**Angličtina → japonština.** Jiné písmo potřebuje jinou sadu znaků a text bez
mezer se musí lámat po znacích. Všimni si, že jméno účtu zůstalo nedotčené —
je to vlastní jméno, ne text k překladu.

| | |
|---|---|
| ![Originál](docs/examples/tweet-before.jpg) | ![Překlad](docs/examples/tweet-after.jpg) |

Celá stránka jde stejně dobře jako její roh — snímek celé anglické Wikipedie
se vrátí v ruštině za necelých sedm sekund.

## Jak to funguje

| Krok | Nástroj |
|---|---|
| Záchyt oblasti | XDG Desktop Portal — funguje na Waylandu i X11 |
| Rozpoznání textu | RapidOCR (PP-OCRv6 v ONNX), lokálně na procesoru |
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

### Překlad bez účtu

Jako alternativa je k dispozici offline překlad, který používá modely Argos
Translate přes CTranslate2. Nic neopouští počítač a není potřeba účet, klíč
ani kvóta.

Neinstaluje se automaticky, protože stojí zhruba 140 MB balíků a 65 MB na
jazykový pár:

```bash
.venv/bin/pip install ctranslate2 subword-nmt sentencepiece
```

Pak se v nastavení zvolí „Offline, na tomto počítači“ a stáhne se model pro
daný pár. Rychlost problém není — model se načte za desetinu sekundy a
obrazovka textu se přeloží výrazně pod sekundu.

Kvalita ano. Nejvíc je to znát na slangu: *„bro has mastered the art of
dodging billing“* vyšlo jako *„Bratr ovládl umění vyhýbání se billingu“*,
kdežto DeepL zvládl *„Kámoš je mistr v tom, jak se vyhnout placení účtů“*. U
běžných vět je rozdíl malý a u meme nápisů verzálkami byl někdy i lepší.

## Použití

* `Ctrl+Print`, nebo ikona v liště → *Přeložit oblast…*
* v okně výsledku: podržený mezerník ukáže originál, `Ctrl+C` kopíruje,
  `Ctrl+S` uloží

## Bez grafického rozhraní

```bash
.venv/bin/python -m linux_screen_translator.cli --image snimek.png --out preklad.png
.venv/bin/python -m linux_screen_translator.cli --translator mock   # bez API klíče
```

## Známá omezení

* Inpainting je klasický (Telea). Na jednobarevném a mírně členitém pozadí je
  výsledek nerozeznatelný od originálu, přes složitou fotografii zůstane
  rozmazaná stopa. Ostřejší by byl model LaMa za cenu ~200 MB a sekundy navíc.
* Vícesloupcový text a kurzíva se nerozpoznají.
* Offline překlad nemá vlastní detekci jazyka, takže text už v cílovém jazyce
  pozná jen podle seznamu slov, který zatím pokrývá češtinu, španělštinu,
  němčinu a francouzštinu.

## Licence

Apache License 2.0 — viz [LICENSE](LICENSE).
