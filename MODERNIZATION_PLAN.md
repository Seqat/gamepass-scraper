# GamePass-Scraper Modernizasyon Planı

_Tarih: 2026-10-08 · Durum: taslak, uygulanmadı_

## 1. Mevcut durum

Proje 2022'den kalma, tek dosyalık (`scraper.py`, 60 satır) bir öğrenme projesi:
`requests-html` ile gamepasscounter.com sayfasını indiriyor, sabit bir XPath ile
listeyi alıyor ve `games.csv` dosyasına yazıyor.

### Bugün çalışıyor mu? Hayır.

Python 3.13 ile temiz bir venv'de yapılan denemenin sonuçları:

| Adım | Sonuç |
|---|---|
| `pip install -r requirements.txt` | Başarılı (requests-html 0.10.0, pyppeteer 2.0.0, lxml 6.1.3) |
| `python scraper.py` | **Import aşamasında çöküyor:** `ImportError: lxml.html.clean module is now a separate project lxml_html_clean` |
| `lxml_html_clean` eklenince | Import geçiyor. Ağ isteği test ortamının proxy politikası yüzünden engellendi, bu yüzden XPath canlı sitede **doğrulanamadı** |

### Tespit edilen sorunlar

**Bağımlılıklar**
- `requests-html` 2019'dan beri sürüm almadı (son sürüm 0.10.0). Bağımlılığı `pyppeteer` da bakımsız.
- Bu bağımlılık zinciri gereksiz: `render()` hiç çağrılmıyor, yani Chromium/pyppeteer hiç kullanılmıyor.
- `requirements.txt` sürüm sabitlemiyor (yeniden üretilemez kurulum) ve dosya sonunda satır sonu yok.

**Kod (`scraper.py`)**
- CSV `newline=''` olmadan açılıyor. Windows'ta satır aralarına boş satır giriyor.
- `games[0]`: XPath hiçbir şeyle eşleşmezse `IndexError` fırlatıyor.
- `session.get()` için timeout, `raise_for_status()` ya da hata yönetimi yok.
- `text.split('\n')` boş ve boşluk içeren satırları da oyun sayıyor.
- XPath konuma dayalı (`div[2]/div[3]`) olduğu için sitedeki en küçük değişiklikte kırılıyor.
- URL, XPath ve çıktı yolu sabit kodlanmış; CLI argümanı yok. CSV'de başlık satırı yok.
- `GamePass_Scraper` PEP 8'e uymuyor, `session` kapatılmıyor, docstring'ler IDE şablonu olarak kalmış (`_summary_`, `_type_`).
- Test yok.

**Dokümantasyon ve repo**
- README'de "Scrapper" yazım hatası (3 yerde) ve "This script required" dilbilgisi hatası var. "Python 3.6+" iddiası güncel değil (3.6 2021'den beri EOL). Çıktı formatı ve kullanım belgelenmemiş.
- `.gitignore` tüm `*.csv` dosyalarını yok sayıyor. Bu, ileride test fixture'larını da gizler.

## 2. Bugünün bağlamı (2022'den bu yana neler değişti)

**Game Pass tarafı**
- Temmuz 2024: Standard katmanı eklendi (ilk gün çıkan oyunlar dahil değil).
- Ekim 2025: Core → **Essential**, Standard → **Premium** oldu ve Ultimate fiyatı arttı.
- Nisan 2026 (ikincil kaynak): yeni fiyatlar geldi. Yeni Call of Duty oyunları artık çıkış gününde Game Pass'te değil.
- **Sonuç:** "Tek bir oyun listesi" modeli artık yetersiz. Oyunlar platforma (PC, konsol, bulut) ve katmana göre ayrışıyor. Katman adları tekrar değişebilir, bu yüzden kodda sabit kodlanmamalı.

**Veri kaynağı**
- HTML kazımak yerine, xbox.com'un kendi kullandığı açık (belgelenmemiş) JSON uç noktaları daha sağlam bir yol:
  1. `https://catalog.gamepass.com/sigls/v2?id=<SIGL_ID>&language=en-us&market=US` liste başına ürün ID'lerini döndürüyor (PC, konsol, bulut, EA Play, yeni eklenen, yakında ayrılacak…).
  2. `https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds=<id,id,...>&market=US&languages=en-us` ID'leri başlık, geliştirici, yayıncı, çıkış tarihi ve görsellerle zenginleştiriyor. Kimlik doğrulama gerektirmiyor. Alan eşleşmeleri [xbox-webapi](https://github.com/OpenXbox/xbox-webapi-python) kaynak kodundan doğrulandı: `LocalizedProperties[0].ProductTitle/DeveloperName/PublisherName/Images`, `MarketProperties[0].OriginalReleaseDate`, `Properties.Categories`.
- ⚠️ **Doğrulanmadı:** SIGL ID'lerinin güncel geçerliliği, `bigIds` için toplu sorgu limiti ve gamepasscounter.com'un güncel yapısı. Araştırmanın yapıldığı ortam bu alan adlarına erişemedi.

**Python ekosistemi (Ekim 2026)**
- Python 3.9 EOL, 3.10 bu ay EOL oluyor, 3.14 güncel kararlı sürüm, 3.15 çıkmak üzere. **Hedef: `requires-python >= 3.11`, CI'da 3.11–3.14 testi.**
- Önerilen yığın: `httpx` 0.28 (HTTP), `pytest` 9 + `respx` (HTTP mock), `ruff` (lint ve format), `pyright` (tip denetimi), `uv` + `pyproject.toml` (paketleme), stdlib `argparse` (CLI). HTML kazıma yedek olarak kalırsa `selectolax` ya da `beautifulsoup4` kullanılabilir. JS render gerekirse `pyppeteer` yerine `playwright`.

## 3. Yol haritası

### Faz 0 — Doğrulama (yarım gün, internet erişimi olan bir makinede)
- [ ] SIGL ID'lerini tek tek `curl` ile çek: durum kodu, kayıt sayısı, JSON yapısı. Aday ID'ler: PC `fdd9e2a7-0fee-49f6-ad69-4354098401ff`, konsol `f6f1f99f-9b49-4ccd-b3bf-4d9767a77f5e`, bulut `29a81209-df6f-41fd-a528-2ae6b91f719c`, EA Play `b8900d09-a491-44cc-916e-32b5acae621b`. Doğrusu, xbox.com Game Pass sayfasının DevTools → Network sekmesinden alınabilir.
- [ ] displaycatalog'u 2–3 ID ile dene ve toplu sorgu limitini bul (20'den başlayıp artır).
- [ ] gamepasscounter.com'un hâlâ yayında olup olmadığını ve listenin bir JSON/XHR çağrısından gelip gelmediğini kontrol et.
- [ ] Gerçek yanıtları `tests/fixtures/` altına kaydet. Testlerde bunlar kullanılacak.
- **Karar noktası:** birincil kaynak Microsoft kataloğu mu olacak, gamepasscounter mı? (Öneri: Microsoft kataloğu.)

### Faz 1 — Acil onarım: tek dosyada çalışır hale getir (≈1 saat)
Mevcut yapıyı bozmadan "bugün çalışan" bir sürüm çıkarıp etiketlemek (`v0.2.0`) için:
- [ ] `requests-html` yerine `httpx` (veya `requests`) + `selectolax`/`lxml` kullan.
- [ ] Timeout, `raise_for_status()`, boş sonuç kontrolü ve anlamlı hata mesajları ekle.
- [ ] CSV'yi `newline=''` ile aç, başlık satırı ekle, boş satırları filtrele.
- [ ] PEP 8 isimlendirmeye geç ve docstring'leri düzelt.
- [ ] `requirements.txt` içinde sürümleri sabitle.

### Faz 2 — Veri kaynağını Microsoft kataloğuna taşı (≈1 gün)
- [ ] `sources/catalog.py`: SIGL → ID listesi, displaycatalog → toplu zenginleştirme (batch, retry/backoff, nazik `User-Agent`).
- [ ] `models.py`: `@dataclass Game(product_id, title, developer, publisher, release_date, categories, image_url, lists: set[str])`. Bir oyun birden fazla listede (PC, konsol, bulut…) olabilir; bu durum tek kayıtta birleştirilir.
- [ ] Liste tanımları (`pc`, `console`, `cloud`, `ea-play`, `recently-added`, `leaving-soon`) tek bir yapılandırma sözlüğünde dursun. ID'ler değiştiğinde tek yerden güncellenebilsin.
- [ ] `market` ve `language` parametreleri desteklensin (örn. `TR`/`tr-tr`).
- [ ] gamepasscounter kazıyıcısı `sources/gamepasscounter.py` altında isteğe bağlı yedek olarak kalsın, ya da Faz 0'da site ölü çıkarsa tamamen kaldırılsın.

### Faz 3 — Paket yapısı ve CLI (≈yarım gün)
```
pyproject.toml          # uv, ruff, pyright, pytest yapılandırması
src/gamepass_scraper/
    __init__.py
    __main__.py         # python -m gamepass_scraper
    cli.py              # argparse
    models.py
    export.py           # csv / json / (ops.) markdown
    sources/catalog.py
tests/
    fixtures/*.json
    test_catalog.py
    test_export.py
```
- [ ] Örnek CLI kullanımı: `gamepass-scraper --list pc --market US --lang en-us --format csv -o games.csv`
- [ ] `--format json` ve `--quiet` seçenekleri, ayrıca `logging` tabanlı çıktı (`print` yerine).
- [ ] Eski `python scraper.py` komutu ince bir sarmalayıcı olarak çalışmaya devam etsin (geriye dönük uyumluluk).

### Faz 4 — Kalite ve CI (≈yarım gün)
- [ ] `ruff check` + `ruff format`, `pyright` ve `pytest` testleri (respx ile, ağ olmadan, fixture'lardan).
- [ ] GitHub Actions: `astral-sh/setup-uv` ile Python 3.11–3.14 matrisinde lint, tip denetimi ve test. Action sürümleri tag/SHA ile sabitlensin.
- [ ] Dependabot (pip + github-actions).

### Faz 5 — Cilalama (≈yarım gün)
- [ ] README'yi baştan yaz: amaç, kurulum (`uv tool install .` / `pip install .`), kullanım örnekleri, çıktı örneği, katman notları ve **"resmi olmayan uç noktalar, uyarı vermeden değişebilir"** notu.
- [ ] Yazım hatalarını düzelt ("Scrapper" → "Scraper").
- [ ] `.gitignore`'u sadeleştir (`*.csv` yerine `/games.csv`, `/output/`).
- [ ] `CHANGELOG.md` ekle, `v1.0.0` etiketini at, LICENSE yılını `2022–2026` yap.

### Faz 6 — İsteğe bağlı, "günümüze uygun" özellikler
- [ ] **Günlük anlık görüntü ve fark raporu:** zamanlanmış bir GitHub Action listeyi çeksin, `data/` altına JSON olarak commit'lesin ve eklenen/çıkan oyunları raporlasın. Projenin en çok değer katacak özelliği bu.
- [ ] Katman/plan bilgisi ve "ilk gün" (day-one) işareti, eğer katalog verisi bunu sağlıyorsa.
- [ ] Basit statik site (GitHub Pages) veya RSS çıktısı.

## 4. Riskler

| Risk | Önlem |
|---|---|
| Microsoft uç noktaları belgelenmemiş, değişebilir | ID'leri tek yerde tut, fixture testleri ekle, zamanlanmış CI kırılınca haberdar et |
| Rate limit / engelleme | Toplu sorgu, backoff, düşük frekans (günde bir) |
| Kullanım koşulları | README'de eğitim amaçlı ve resmi olmayan bir araç olduğunu belirt, ticari kullanım önerme |
| Katman adlarının yeniden değişmesi | Katmanları veri olarak modelle, enum olarak sabit kodlama |

## 5. Kullanıcının vermesi gereken kararlar

1. **Kapsam:** Proje küçük bir öğrenme betiği olarak mı kalsın (Faz 1 + 5 yeterli), yoksa paketlenmiş bir CLI aracına mı dönüşsün (Faz 0–5)?
2. **Veri kaynağı:** Microsoft kataloğu (önerilen) mu, gamepasscounter kazıma mı, yoksa ikisi birden mi?
3. **README dili:** İngilizce (mevcut) mi, Türkçe mi, iki dilli mi?
4. **Faz 6:** Günlük anlık görüntü ve fark raporu isteniyor mu?
