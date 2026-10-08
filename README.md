# gamepass-scraper

[![CI](https://github.com/seqat/gamepass-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/seqat/gamepass-scraper/actions/workflows/ci.yml)

**English** | [Türkçe](#türkçe)

A command-line tool that exports the Xbox Game Pass game lists (PC, console, cloud, EA Play) to CSV or JSON.

It started in 2022 as a learning project by Sedat Ali Zevit to explore the basics of web scraping with Python, and it still carries that spirit: small, readable, and built to be learned from.

> **Disclaimer.** This is an unofficial tool, not affiliated with Microsoft or Xbox. It uses public but undocumented Microsoft catalog endpoints, which can change without notice. It is intended for educational and personal use. It comes with no warranty.

## Features

- Exports one or more Game Pass lists in a single run, and merges games that appear in several lists into one row.
- Reads game data from Microsoft's Game Pass catalog, with [gamepasscounter.com](https://gamepasscounter.com/) as a fallback for the PC list.
- Lets you choose the market (region) and language of the returned data.
- Writes CSV (default) or JSON, to a file or to stdout.
- Uses timeouts and retries with backoff for transient network errors.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (recommended), or `pip`

## Installation

Install the CLI as a standalone tool with uv:

```bash
uv tool install git+https://github.com/seqat/gamepass-scraper
```

Or clone the repository and install it with pip:

```bash
git clone https://github.com/seqat/gamepass-scraper.git
cd gamepass-scraper
pip install .
```

> `requirements.txt` has been removed. Dependencies are declared in `pyproject.toml`, and `uv.lock` pins them.

For development, see [Development](#development).

## Usage

By default, the tool exports the PC list to `games.csv`:

```bash
gamepass-scraper
```

More examples:

```bash
# Console and cloud lists, written to a custom file
gamepass-scraper --list console --list cloud -o console-cloud.csv

# Every known list as JSON, printed to stdout
gamepass-scraper --list all --format json -o -

# Turkish market and language
gamepass-scraper --market TR --language tr-tr

# Use the gamepasscounter.com fallback source directly (PC list only)
gamepass-scraper --source gamepasscounter

# Pass a SIGL list ID that is not in the built-in list table
gamepass-scraper --sigl-id 00000000-0000-0000-0000-000000000000 -o custom.csv

# Run with python -m instead of the console script
python -m gamepass_scraper --list pc
```

The legacy entry point still works as a thin wrapper around the same CLI:

```bash
python scraper.py
```

### CLI options

```
gamepass-scraper [--list {pc,console,cloud,ea-play,all}]... [--sigl-id ID]...
                 [--market US] [--language en-us]
                 [--source {auto,microsoft,gamepasscounter}]
                 [--format {csv,json}] [-o/--output PATH]
                 [--timeout 20] [--batch-size 20] [-q|--quiet] [-v|--verbose] [--version]
```

| Option | Default | Description |
|---|---|---|
| `--list {pc,console,cloud,ea-play,all}` | `pc` | List to export. Repeatable. `all` expands to every built-in list. The default applies only when neither `--list` nor `--sigl-id` is given. |
| `--sigl-id ID` | none | Extra Microsoft SIGL list ID. Repeatable. Each one is stored under the list name `sigl:<id>`. |
| `--market MARKET` | `US` | Market (region) code, such as `US` or `TR`. Converted to uppercase. |
| `--language LANG` | `en-us` | Language tag, such as `en-us` or `tr-tr`. Converted to lowercase. |
| `--source {auto,microsoft,gamepasscounter}` | `auto` | Data source. See [Data sources](#data-sources). |
| `--format {csv,json}` | `csv` | Output format. |
| `-o`, `--output PATH` | `games.csv` or `games.json`, depending on `--format` | Output file path. Use `-` for stdout. Parent directories are created as needed. |
| `--timeout SECONDS` | `20` | HTTP request timeout, in seconds. |
| `--batch-size N` | `20` | Number of product IDs requested per Microsoft catalog call. |
| `-q`, `--quiet` | off | Show warnings and errors only. |
| `-v`, `--verbose` | off | Show debug output. |
| `--version` | | Print the version and exit. |

**Exit codes:** `0` on success, `1` on a scraping or data-source error, `2` on invalid command-line usage, and `130` when interrupted with Ctrl+C.

Logs are written to stderr, so they do not mix with data written to stdout (`-o -`).

### Output columns

CSV output starts with a header row. The columns are:

| Column | Description |
|---|---|
| `product_id` | Microsoft Store product ID, such as `9NBLGGH4R315`. May be empty for games from the fallback source. |
| `title` | Game title. |
| `developer` | Developer name. |
| `publisher` | Publisher name. |
| `release_date` | Original release date in `YYYY-MM-DD` format. Empty when unknown. |
| `categories` | Store categories, joined with `; `. |
| `image_url` | URL of the preferred box or poster image. |
| `lists` | Lists the game belongs to, such as `console; pc`, joined with `; `. |
| `source` | Where the record came from: `microsoft` or `gamepasscounter`. |

In JSON output, the same fields are used as keys. `categories` and `lists` are arrays, and `release_date` is an ISO date string.

## Data sources

### Primary: Microsoft Game Pass catalog

1. **Lists.** For each list, the tool calls the SIGL endpoint (`catalog.gamepass.com/sigls/v2`) to get the product IDs in that list.
2. **Details.** The tool calls the Microsoft Store catalog (`displaycatalog.mp.microsoft.com`) in batches to get the title, developer, publisher, release date, categories, and image for each ID.

Each product ID is fetched once, even if it belongs to several lists.

> **Note:** The SIGL list IDs in `src/gamepass_scraper/lists.py` and the displaycatalog batch limit are community-documented. They have not been verified against the live service in every release, and they may need updating. If a list stops returning games, find its current ID (for example, in the browser's developer tools on the Game Pass page) and pass it with `--sigl-id`. If batch requests fail, lower `--batch-size`.

### Fallback: gamepasscounter.com

The fallback scrapes the game list from [gamepasscounter.com](https://gamepasscounter.com/). It supports only the PC list and provides titles only, so most columns will be empty.

### How `--source auto` works

`auto` is the default. The tool first tries Microsoft. If that fails, it falls back to gamepasscounter.com, but **only** when the requested lists are exactly `pc` and no `--sigl-id` was given. In every other case, the Microsoft error is reported and the run stops with exit code `1`.

## Development

The project uses [uv](https://docs.astral.sh/uv/) for environments and dependencies, and Python 3.11 or newer.

```bash
uv sync                    # create .venv and install runtime and dev dependencies
uv run ruff check .        # lint
uv run ruff format --check .
uv run pyright             # type check
uv run pytest              # tests (network calls are mocked with respx and recorded fixtures)
```

The package lives in `src/gamepass_scraper/`, and tests are in `tests/`. Continuous integration runs these checks from `.github/workflows/ci.yml`.

## License

Released under the [MIT License](LICENSE). Copyright (c) 2022-2026 Sedat Ali Zevit.

---

## Türkçe

[English](#gamepass-scraper) | **Türkçe**

Xbox Game Pass oyun listelerini (PC, konsol, bulut, EA Play) CSV ya da JSON olarak dışa aktaran bir komut satırı aracı.

Proje 2022'de Sedat Ali Zevit'in Python ile web kazımayı öğrenmek için başlattığı küçük bir öğrenme projesi olarak doğdu. Bu ruh hâlâ geçerli: küçük, okunabilir ve öğrenmeye açık kalmayı hedefliyor.

> **Uyarı.** Bu resmi olmayan bir araçtır ve Microsoft ya da Xbox ile bir bağlantısı yoktur. Belgelenmemiş ama herkese açık olan Microsoft katalog uç noktalarını kullanır; bu uç noktalar haber verilmeden değişebilir. Eğitim ve kişisel kullanım içindir. Herhangi bir garanti vermez.

## Özellikler

- Tek çalıştırmada bir ya da birden fazla listeyi dışa aktarır; birden fazla listede yer alan oyunları tek satırda birleştirir.
- Oyun verilerini Microsoft'un Game Pass kataloğundan alır. PC listesi için [gamepasscounter.com](https://gamepasscounter.com/) yedek kaynak olarak çalışır.
- Verinin alınacağı pazarı (bölgeyi) ve dili seçmenize olanak tanır.
- CSV (varsayılan) ya da JSON çıktısını dosyaya ya da standart çıktıya yazar.
- Geçici ağ hatalarında zaman aşımı ve artan bekleme süreleriyle yeniden deneme uygular.

## Gereksinimler

- Python 3.11 veya üzeri
- [uv](https://docs.astral.sh/uv/) (önerilir) ya da `pip`

## Kurulum

uv ile komut satırı aracını bağımsız bir araç olarak kurun:

```bash
uv tool install git+https://github.com/seqat/gamepass-scraper
```

Ya da depoyu klonlayıp pip ile kurun:

```bash
git clone https://github.com/seqat/gamepass-scraper.git
cd gamepass-scraper
pip install .
```

> `requirements.txt` kaldırıldı. Bağımlılıklar `pyproject.toml` içinde tanımlanır, sürümleri ise `uv.lock` dosyası sabitler.

Geliştirme ortamı için [Geliştirme](#geliştirme) bölümüne bakın.

## Kullanım

Varsayılan olarak araç PC listesini `games.csv` dosyasına aktarır:

```bash
gamepass-scraper
```

Daha fazla örnek:

```bash
# Konsol ve bulut listeleri, özel bir dosyaya
gamepass-scraper --list console --list cloud -o console-cloud.csv

# Bilinen tüm listeler, JSON olarak standart çıktıya
gamepass-scraper --list all --format json -o -

# Türkiye pazarı ve Türkçe dil
gamepass-scraper --market TR --language tr-tr

# Doğrudan gamepasscounter.com yedek kaynağını kullan (yalnızca PC listesi)
gamepass-scraper --source gamepasscounter

# Yerleşik tabloda bulunmayan bir SIGL liste kimliğini kullan
gamepass-scraper --sigl-id 00000000-0000-0000-0000-000000000000 -o custom.csv

# Konsol komutu yerine python -m ile çalıştır
python -m gamepass_scraper --list pc
```

Eski giriş noktası da çalışmaya devam eder. Aynı komut satırı arayüzüne ince bir sarmalayıcıdır:

```bash
python scraper.py
```

### Komut satırı seçenekleri

```
gamepass-scraper [--list {pc,console,cloud,ea-play,all}]... [--sigl-id ID]...
                 [--market US] [--language en-us]
                 [--source {auto,microsoft,gamepasscounter}]
                 [--format {csv,json}] [-o/--output PATH]
                 [--timeout 20] [--batch-size 20] [-q|--quiet] [-v|--verbose] [--version]
```

| Seçenek | Varsayılan | Açıklama |
|---|---|---|
| `--list {pc,console,cloud,ea-play,all}` | `pc` | Dışa aktarılacak liste. Birden fazla kez verilebilir. `all`, yerleşik tüm listeleri kapsar. Varsayılan yalnızca ne `--list` ne de `--sigl-id` verildiğinde uygulanır. |
| `--sigl-id ID` | yok | Ek bir Microsoft SIGL liste kimliği. Birden fazla kez verilebilir. Her biri `sigl:<id>` adıyla kaydedilir. |
| `--market MARKET` | `US` | `US` veya `TR` gibi pazar (bölge) kodu. Büyük harfe çevrilir. |
| `--language LANG` | `en-us` | `en-us` veya `tr-tr` gibi dil etiketi. Küçük harfe çevrilir. |
| `--source {auto,microsoft,gamepasscounter}` | `auto` | Veri kaynağı. Ayrıntılar için [Veri kaynakları](#veri-kaynakları) bölümüne bakın. |
| `--format {csv,json}` | `csv` | Çıktı biçimi. |
| `-o`, `--output PATH` | `--format` değerine göre `games.csv` ya da `games.json` | Çıktı dosyasının yolu. Standart çıktı için `-` kullanın. Gerekli üst klasörler oluşturulur. |
| `--timeout SANİYE` | `20` | HTTP istekleri için zaman aşımı, saniye cinsinden. |
| `--batch-size N` | `20` | Microsoft kataloğuna tek çağrıda istenen ürün kimliği sayısı. |
| `-q`, `--quiet` | kapalı | Yalnızca uyarı ve hataları gösterir. |
| `-v`, `--verbose` | kapalı | Hata ayıklama çıktısını gösterir. |
| `--version` | | Sürümü yazdırır ve çıkar. |

**Çıkış kodları:** Başarıda `0`, kazıma ya da veri kaynağı hatasında `1`, geçersiz komut satırı kullanımında `2`, Ctrl+C ile kesildiğinde `130`.

Günlük (log) mesajları standart hataya (stderr) yazılır. Böylece `-o -` ile standart çıktıya yazılan veriyle karışmazlar.

### Çıktı sütunları

CSV çıktısı bir başlık satırıyla başlar. Sütunlar şunlardır:

| Sütun | Açıklama |
|---|---|
| `product_id` | Microsoft Store ürün kimliği, örneğin `9NBLGGH4R315`. Yedek kaynaktan gelen kayıtlarda boş olabilir. |
| `title` | Oyunun adı. |
| `developer` | Geliştirici adı. |
| `publisher` | Yayıncı adı. |
| `release_date` | Orijinal çıkış tarihi, `YYYY-MM-DD` biçiminde (yıl-ay-gün). Bilinmiyorsa boştur. |
| `categories` | Mağaza kategorileri, `; ` ile birleştirilmiş. |
| `image_url` | Tercih edilen kutu ya da poster görselinin adresi. |
| `lists` | Oyunun ait olduğu listeler, örneğin `console; pc`. `; ` ile birleştirilmiş. |
| `source` | Kaydın kaynağı: `microsoft` ya da `gamepasscounter`. |

JSON çıktısında aynı alanlar anahtar olarak kullanılır. `categories` ve `lists` dizi, `release_date` ise ISO tarih metnidir.

## Veri kaynakları

### Birincil kaynak: Microsoft Game Pass kataloğu

1. **Listeler.** Her liste için araç, SIGL uç noktasından (`catalog.gamepass.com/sigls/v2`) o listedeki ürün kimliklerini alır.
2. **Ayrıntılar.** Ürün kimlikleri, Microsoft Store kataloğundan (`displaycatalog.mp.microsoft.com`) gruplar hâlinde sorgulanır. Her oyun için başlık, geliştirici, yayıncı, çıkış tarihi, kategoriler ve görsel alınır.

Bir ürün kimliği birden fazla listede olsa bile yalnızca bir kez sorgulanır.

> **Not:** `src/gamepass_scraper/lists.py` içindeki SIGL liste kimlikleri ve displaycatalog toplu sorgu sınırı topluluk tarafından belgelenmiştir. Her sürümde canlı serviste doğrulanmamıştır ve güncellenmesi gerekebilir. Bir liste oyun döndürmeyi bırakırsa, güncel kimliği bulun (örneğin Game Pass sayfasının tarayıcı geliştirici araçlarından) ve `--sigl-id` ile verin. Toplu istekler başarısız olursa `--batch-size` değerini düşürün.

### Yedek kaynak: gamepasscounter.com

Yedek kaynak, oyun listesini [gamepasscounter.com](https://gamepasscounter.com/) sitesinden kazır. Yalnızca PC listesini destekler ve yalnızca başlık verir; bu nedenle çoğu sütun boş kalır.

### `--source auto` nasıl çalışır?

`auto` varsayılan seçenektir. Araç önce Microsoft'u dener. Bu başarısız olursa gamepasscounter.com kaynağına geçer, ama **yalnızca** istenen listeler tam olarak `pc` ise ve `--sigl-id` verilmemişse. Diğer durumlarda Microsoft hatası bildirilir ve çalışma `1` çıkış koduyla sonlanır.

## Geliştirme

Proje, ortam ve bağımlılık yönetimi için [uv](https://docs.astral.sh/uv/) kullanır. Python 3.11 veya üzeri gerekir.

```bash
uv sync                    # .venv oluşturur, çalışma ve geliştirme bağımlılıklarını kurar
uv run ruff check .        # kod denetimi (lint)
uv run ruff format --check .
uv run pyright             # tip denetimi
uv run pytest              # testler (ağ çağrıları respx ve kayıtlı örneklerle taklit edilir)
```

Paket `src/gamepass_scraper/` altında, testler `tests/` altındadır. Sürekli entegrasyon bu denetimleri `.github/workflows/ci.yml` dosyasından çalıştırır.

## Lisans

[MIT Lisansı](LICENSE) altında yayımlanmıştır. Telif hakkı (c) 2022-2026 Sedat Ali Zevit.
