# Nasıl Kullanılır — batonai

*[English](HOW_TO_USE.md) · Türkçe*

Sade, pratik bir rehber. Teknik tasarım için [ARCHITECTURE.md](ARCHITECTURE.md) ve [DECISIONS.md](DECISIONS.md)'a, uygulamalı test komutları için [MANUAL_TESTING.md](MANUAL_TESTING.md)'a bakabilirsin.

---

## 1. Bu nedir?

Düz İngilizce (veya Türkçe) bir isteği, birden fazla AI aracını otomatik olarak sırayla çalıştırarak bitmiş, gözden geçirilmiş koda dönüştüren tek bir komut:

```bash
batonai "Ayarlar ekranına karanlık mod düğmesi ekle"
```

Bu tek satırın arkasında sırayla şunlar olur: bir **Planlayıcı (Planner)** uygulama planı yazar, bir **Kodlayıcı (Coder)** bu planı gerçek projende hayata geçirir, bir **İnceleyici (Reviewer)** sonucu plana göre kontrol eder ve her şey diskte, senin incelemen için saklanır. Bunların her biri farklı bir AI'dır (Codex, Claude Code) — hangisinin ne konuda iyi olduğuna göre seçilmiştir; tek bir model her şeyi yapmaz.

**Bu araç hiçbir kararı kendiliğinden/dinamik olarak vermez.** Aşamaların sırası, kimin neyi yapacağı, okuyabileceğin bir yapılandırma (config) dosyasıyla sabittir. İş akışın hakkında gizli bir "denetleyici" yapay zeka takdir yetkisi kullanmaz.

## 2. Başlamadan önce

Bilgisayarında kurulu ve giriş yapılmış olması gerekenler:
- `claude` (Claude Code) — Coder
- `codex` (Codex CLI) — Planner ve Reviewer

İsteğe bağlı, yalnızca ilgili aşamayı açarsan: `agy` (Antigravity CLI, `--with-designer` için), `opencode` (ücretsiz istemci, `--with-publisher` için), `repowise` (`--health` için).

Hepsini tek seferde kontrol et:
```bash
batonai doctor
```
Zorunlu iki satırda `✓ healthy` yazmalı; biri yazmıyorsa devam etmeden önce o sağlayıcının girişini/kurulumunu düzelt — orchestrator bozuk bir sağlayıcıyı atlayıp geçmez. Aşaması kapalı olan sağlayıcılar *optional* olarak listelenir ve seni asla engellemez.

## 3. Kurulum

```bash
uv tool install batonai      # veya: pipx install batonai
```

Bu, `batonai` komutunu **her klasörden** çalıştırabileceğin şekilde kurar. Önce [uv](https://docs.astral.sh/uv/) ya da [pipx](https://pipx.pypa.io/) gerekir — ikisi de Python araçlarını kendi yalıtılmış ortamlarına kurar, sistem Python'una dokunmaz. Sonrası için: güncellemek `uv tool upgrade batonai`, kaldırmak `uv tool uninstall batonai`.

**Windows'ta:** Python 3.12+ ve `uv`'yi (ya da `pipx`'i) normal yoldan kur; aynı komut PowerShell veya Windows Terminal'de çalışır, WSL gerekmez. Kullanıcı düzeyi config dosyan `%APPDATA%\batonai\config.yaml` konumundadır. Baton'un kendi yaptığı her şey CI'da Windows üzerinde test ediliyor; sağlayıcı CLI'ları ise üreticilerin kendi programları, bu yüzden önce `batonai doctor` çalıştır. Varsayılan pipeline'daki Claude Code ve Codex, prompt'u stdin üzerinden gönderdiği için güvenli tercihlerdir. İsteğe bağlı Designer (`agy`) ve Publisher (`opencode`) prompt'u komut satırı argümanı olarak geçirir; Windows'ta bu `cmd.exe` tırnaklama kurallarından geçer ve orada denenmedi — `%`, `^` veya `"` içeren bir prompt tuhaf davranırsa sebebi budur.

En yeni, henüz yayınlanmamış kodu mu istiyorsun, ya da baton'un kendisi üzerinde mi çalışacaksın?
```bash
uv tool install git+https://github.com/ozanorfa/baton          # en güncel main
git clone https://github.com/ozanorfa/baton && cd baton && uv tool install --editable .   # geliştirme
```

## 4. İlk çalıştırman

Projene gir ve komutu tek başına yaz:

```bash
cd projen                    # herhangi bir gerçek proje, tercihen bir git deposu
batonai
```

Hepsi bu. Tek başına `batonai`, kısa ve yönlendirmeli bir oturum açar:

```
  baton — AI coding pipeline

  scanning projen/ …
  ✓ providers  all healthy
  ✓ project    Python (pyproject.toml)
  ✓ git        clean
  ⚠ baton      not set up in this folder yet
  ✓ health     code hotspots found (repowise)
       src/core/engine.py — score 2.4/10, max complexity 26, nesting 4

  Set up baton in this folder? [Y/n]
```

AI araçlarının çalışıp çalışmadığını kontrol eder, bunun ne tür bir proje olduğunu anlar, kurulum eksikse tek seferlik kurulumu önerir ve **ancak ondan sonra** ne yapmak istediğini sorar. Aşağıdaki komutların hiçbirini ezberlemen gerekmez — ama yazmayı tercih edersen hepsi hâlâ duruyor (§8).

**Sana ne söylüyor:**
- **providers** — AI CLI'ların kurulu ve giriş yapılmış durumda. Biri değilse oturum burada durur ve hangisi olduğunu söyler; hiçbir şey sorulmaz, hiçbir kota harcanmaz.
- **baton** — bu klasör daha önce kurulmuş mu. Evet dersen `.ai/config.yaml` ve `.ai/project.md` senin için oluşturulur.
- **health** — projedeki en karmaşık/riskli mevcut dosyalar; statik analizle bulunur (AI yok, token yok). Her aşamaya bu dosyalar bildirilir ki oralara dikkatli dokunsunlar. `repowise` aracı kurulu değilse bu satır hiç görünmez — hiçbir şey bozulmaz.

Herhangi bir soruda Ctrl-C ile çıkabilirsin; hiçbir şey oluşturulmaz, hiçbir şey değişmez.

**Sonrasında zamanına değecek tek dosya:** `.ai/project.md` dosyasını aç ve kendi konvansiyonların hakkında birkaç dürüst satır ekle — "setState değil Riverpod kullanıyoruz", "testler test/ klasöründe" gibi, bir AI asistanının genelde yanlış yaptığı her şey. Bu dosya her aşamada, her çalıştırmada okunur; buraya yazacağın birkaç iyi satır defalarca işine yarar.

*(Pipe'lıyor ya da CI'da mı çalıştırıyorsun? Argümansız `batonai`, soru sormak yerine yardım metnini basar — script'ler asla asılı kalmaz.)*

## 5. Çalışırken ne görürsün

```
run: isteğin buraya
planner → designer (off) → coder → reviewer → publisher (off)
  ✓ planner → plan.md in 20s
  ○ designer skipped (disabled)
  ✓ coder → changes.md in 45s
  ✓ reviewer → review.md in 15s
                    run 2026-...
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ stage    ┃ provider ┃ duration ┃ tokens in/out ┃ status ┃
┗━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━━━━━━━┻━━━━━━━━┛
reviewer verdict: APPROVE
run succeeded · artifacts: .ai/runs/<run-id>/artifacts
```

Bir çalıştırma genelde 1-5 dakika sürer ve deponda gerçek dosyalara dokunur — Coder aşaması, doğrudan kendisine sorsaydın nasıl yapacaksa aynı şekilde koda dokunur ve düzenler.

## 6. Çalıştırma bittikten sonra elinde ne kalır

- **Gerçek kod değişiklikleri**, çalışma dizininde commit'lenmemiş halde durur — kendi yaptığın bir değişiklik gibi `git diff` ile incele.
- **`.ai/runs/<run-id>/`** — o çalıştırmayla ilgili her şey:
  - `artifacts/plan.md`, `changes.md`, `review.md` — her aşamanın ürettiği, düz metin olarak
  - `artifacts/diff.patch` — Coder'ın tam olarak neyi değiştirdiği
  - `report.json` — terminaldeki özetin veri hâli
  - `prompts/` — her AI'ya *tam olarak* verilen metin (bir sonuç tuhaf görünürse işine yarar)
  - `logs/` — hata ayıklama için her aşamanın ham çıktısı

**Hiçbir pipeline çalıştırması commit veya push atmaz** — inceleme senin işin. Commit de öyle; ancak sen açıkça `batonai publish --commit`/`--push` çalıştırırsan olur (§8.1). Bkz. §9.

## 7. Maliyet/kota rakamını anlamak

Bir çalıştırmadan sonra şuna benzer bir şey görürsün:
```
totals: tokens 400,123/8,500 · measured cost $0.85*
* cost = provider-reported API-equivalent value; on subscription plans it consumes plan quota — no per-run charge
```

**Abonelik kullanıyorsan** (Claude Pro/Max, ChatGPT Plus) — o dolar rakamı **bir fatura değildir**. Yapılan işin API-eşdeğeri değeridir, bilgi amaçlı gösterilir; gerçekte olan şey, planına dahil kullanım kotanın biraz azalmasıdır — o araçla yapacağın herhangi bir sohbet gibi. Gerçek para sadece token-başına-ödeme yapan API anahtarları kullanıyorsan öder.

Tam bir çalıştırma genelde 0,20–1,50 dolarlık kota-eşdeğeri "maliyet" gösterir — çoğunlukla sabit bir ek yüktür (her AI'nın projeni yeniden tanıması), gerçek işin büyüklüğüyle pek artmaz. Yani bu araç tek satırlık değişiklikler için doğru seçim değildir — küçük şeyler için `batonai ask` kullan (§8).

### Yayıncı (Publisher) ücretsiz bir istemcide çalışır — bir uyarı

Opsiyonel Yayıncı aşaması (ve `batonai ask --role publisher`), bu sığ "diff'ten bir commit mesajı taslağı çıkar" işini ücretli planlarından tamamen uzak tutmak için **opencode** adlı ücretsiz bir komut satırı istemcisine bağlanmıştır. opencode ücretsiz bir *istemcidir*, ama model yine de bir yerden gelir — onu opencode'un kendi `opencode auth` komutuyla bir ücretsiz katmana yönlendirirsin (bir [OpenRouter](https://openrouter.ai) `:free` modeli, bir Google AI Studio ücretsiz-katman anahtarı ya da bir opencode promosyon modeli). Bilmen gereken iki şey:

- Ücretsiz katmanlar **hız-sınırlıdır** ve genellikle **gönderdiğin veriyle model eğitebilirler**. Bir commit mesajı için bu sorun değildir; Yayıncı'nın yalnızca *diff'i ve planı* görmesinin, hiçbir zaman tüm kod tabanına yönlendirilmemesinin — ve kod okuyan aşamaların (Kodlayıcı, İnceleyici) buraya asla yönlendirilmemesinin sebebi budur.
- Ücretsiz katman kullanmak istemiyorsan, Yayıncı'nın sağlayıcısını proje bazında değiştir (ör. `.ai/config.yaml` içinde `roles: {publisher: {provider: codex}}`).

## 8. Günlük kullanılan komutlar

| Komut | Ne yapar |
|---|---|
| `batonai` | **Yönlendirmeli giriş yolu** (§4): projeyi tarar, eksik kurulumu önerir, ne istediğini sorar, çalıştırır. Aşağıdakilerin hepsi — bilmek zorunda kalmadan |
| `batonai "<istek>"` | Tüm pipeline'ı çalıştırır |
| `batonai --with-designer "<istek>"` | Bu çalıştırma için Designer (UI/UX planlama) aşamasını da çalıştırır |
| `batonai --with-tester "<istek>"` | Coder'dan sonra projenin testlerini de çalıştırır (sıfır token) ve sonucu Reviewer'a verir — komutu `providers: {testrunner: {command: "..."}}` ile ver ya da otomatik tespite bırak |
| `batonai --with-publisher "<istek>"` | Bir commit mesajı + PR açıklaması da taslak olarak hazırlar (asla git komutu çalıştırmaz — bkz. §9) |
| `batonai --health "<istek>"` | Her aşamaya, projedeki hangi dosyaların kod-sağlığı açısından riskli (karmaşıklık/iç içe geçme) olduğunu bildirir; böylece oralara dikkatli dokunurlar. `repowise` aracının kurulu olması gerekir; ~4sn ve geçici bir index ekler — varsayılan kapalı (ADR-025) |
| `batonai ask --role coder "<soru>"` | Tek bir AI'ya ucuz, tek seferlik bir çağrı — pipeline yok, artifact yok. Küçük sorular veya minik düzeltmeler için ideal |
| `batonai health` | Baton'un kod-sağlığı açısından riskli saydığı dosyaları gösterir (her aşamaya verilen metnin aynısı). Ücretsiz, run gerektirmez — `repowise` kurulu olmalı |
| `batonai doctor` | Sağlayıcıların kurulu ve giriş yapılmış olduğunu kontrol eder. Kapalı aşamaların sağlayıcıları *optional* görünür, başarısızlık sayılmaz |
| `batonai init` | Bir projede `.ai/`'ı kurar (tekrar çalıştırmak güvenlidir; senin düzenlemelerinin üzerine asla yazmaz). Her sağlayıcı için hangi modeli kullanacağını sorar — Enter, o CLI'ın kendi ayarını korur (ADR-031) |
| `batonai setup` | Hangi AI'ın hangi işi yaptığını (Coder=Claude, Planner=Codex…) ve hangi modeli kullandığını istediğin zaman değiştir. Varsayılan düzen aynı kalır — bu sadece görünür ve değiştirilebilir yapar (ADR-032) |
| `batonai config show` | Geçerli tam yapılandırmayı ve her değerin nereden geldiğini gösterir |
| `batonai runs list` | Bu projedeki geçmiş tüm çalıştırmaları listeler: durum, maliyet, karar |
| `batonai runs show <run-id>` | Bir çalıştırmanın detayını gösterir |
| `batonai resume <run-id>` | Başarısız olan bir çalıştırmayı kaldığı yerden devam ettirir — daha önce başarılı olan aşamalar asla tekrar yapılmaz veya tekrar ödenmez |
| `batonai revise "<düzeltme>"` | **Son** çalıştırma üzerinde sıfırdan başlamadan iterasyon yapar — Coder kendi oturumunu sürdürüp düzeltmeni uygular, sonra Reviewer tekrar bakar (bkz. §8.1) |
| `batonai review` | Mevcut (commit'lenmemiş) değişikliklerini ikinci bir görüş için Reviewer'a gönderir — pipeline yok, hiçbir şeyi değiştirmez. `-m "şuna odaklan"` ile yönlendir |
| `batonai publish` | Taslak commit mesajını gösterir (git yok). `--commit` ile commit'ler, `--push` ile commit + push yapar — git'e dokunan tek komut, o da yalnızca sen isteyince (bkz. §8.1) |

## 8.1 "Düzelt, sonra gönder" akışı

Pipeline bir kez çalışır ve durur — ama ilk seferde her şey nadiren tam istediğin gibi olur. İki komut bu döngüyü kapatır, böylece karşılıklı (sohbet gibi) çalışabilirsin:

```bash
batonai "ayarlar ekranı ekle"            # 1. çalıştır
git diff                            # 2. Coder ne yaptı, incele
batonai revise "başlığı sabitle"         # 3. tam olmadı mı? düzelt — aynı çalışma, sıfırdan başlamaz
                                    #    (Coder kendi işini hatırlar; --from planner ile planı yenile)
batonai publish --push                   # 4. beğendin mi? her şeyi commit'le ve push et (önce onay ister)
```

`batonai revise` **son** çalıştırmayı sürdürür: planı korur ve Coder'dan yeniden koşar; Coder kendi oturumunu sürdürüp düzeltmeni bir sonraki tur gibi ele alır — sonra Reviewer tekrar bakar. İstediğin kadar tekrarla. Memnun kaldığında `batonai publish` commit mesajını taslaklar ve — yalnızca `--commit`/`--push` ile ve sen onayladıktan sonra — gerçekten commit'ler (`git add -A`) ve push'lar.

**O ilk düzeltmenin otomatik olmasını mı istersin?** Çalıştırmaya `--fix-loop` ekle: Reviewer'ın kararı `NEEDS WORK` (bloklayan bir sorun) dönerse, araç **bir** otomatik düzeltme turu atar — `batonai revise`'ın elle yaptığı "Coder'ı bulgularla yeniden koştur"un aynısı — sonra durur. Varsayılan kapalı (o ekstra tur kota harcar); çalıştırma başına `batonai --fix-loop "..."` ile ya da proje başına `.ai/config.yaml`'de `pipeline: {fix_loop: true}` ile aç.

## 9. Bu aracın asla yapmayacağı şeyler (bunu bir kez oku, yeter)

- **Hiçbir pipeline aşaması git çalıştırmaz.** Pipeline kendiliğinden asla commit/push atmaz veya GitHub'a dokunmaz — ne varsayılan olarak, ne bir bayrakla. İsteğe bağlı Publisher aşaması bile sadece *bir metin taslağı yazar*. Git'in çalışmasının **tek** yolu, **senin** `batonai publish --commit`/`--push` yazmandır — sana neyi commit'leyeceğini tam olarak gösteren ve önce onay isteyen ayrı, açık bir komut (§8.1). Sen her seferinde istemeden hiçbir şey geçmişine girmez.
- **Coder aşaması, her seferinde izin sormadan dosyalarını düzenler** (asıl amaç budur — yoksa her değişikliği elle onaylaman gerekirdi). Güvenlik ağı: temiz bir `git status` ile başla (araç temiz değilse uyarır), commit atmadan önce diff'i incele ve Reviewer aşamasının bulgularının seni yönlendirmesine izin ver.
- Bu güven seviyesi belirli bir proje için uygun değilse, bunun yerine `batonai ask` kullan — sadece cevap verir, hiçbir şeyi düzenlemez.

## 10. Projene göre uyarlamak

Aşağıdakilerin hepsi o projenin kendi `.ai/config.yaml` dosyasına yazılır — bu aracın koduna asla dokunmaz.

**İsteğe bağlı aşamaları kalıcı olarak aç** (her seferinde bayrak yazmak yerine):
```yaml
roles:
  designer: {enabled: true}
  publisher: {enabled: true}
```

**Daha küçük/ucuz bir Claude modeli kullan** (daha düşük riskli projeler için):
```yaml
providers:
  claude: {model: haiku}
```

**İstemediğin aşamaları atla** (örneğin inceleme adımı olmadan):
```yaml
pipeline:
  stages: [planner, coder]
```

**Bir işi hangi AI'nın yapacağını değiştir** — her rolün sağlayıcısı bağımsızdır:
```yaml
roles:
  coder: {provider: codex}     # örneğin bu proje için Claude kullanmak istemiyorsan
```

**Coder'ın kendi işini testlerle doğrulamasına izin ver** (varsayılan: kapalı):
```yaml
providers:
  claude: {allow_commands: true}
```
Başsız (headless) Claude Code, aksi söylenmedikçe her kabuk komutunu reddeder; bu ayar olmadan Coder dosya düzenler ama hiçbir şey çalıştıramaz — özetinin *How to verify* bölümünde bunu açıkça söyler. Açıldığında kabuk erişimi verilir **ama** git geçmişi/uzak depo komutları (`git commit/push/reset/checkout/…`, `gh`) açık bir yasak listesiyle engelli kalır — bkz. §9. Codex'in sandbox'ı komutlara zaten izin verir (ve ağı kapatır); Codex coder için bu ayar bir şey değiştirmez.

## 11. Bir şey başarısız olduğunda

Çalıştırma başarısız olan aşamada durur — ondan sonrası hiç çalışmaz, o ana kadar yapılmış olan hiçbir şey kaybolmaz. Nedeni ve önerilen sonraki adımı görürsün:
```
next steps: batonai resume <run-id> · batonai doctor
```
`batonai resume <run-id>` çalıştır; tam olarak kaldığı yerden devam eder ve daha önce başarılı olan her şeyi yeniden kullanır — aynı iş için asla iki kere ödemezsin.

**Çalıştırma sırasında Ctrl-C'ye basmak** o aşamayı durdurur, aynı özeti basar (kesilen aşama ✗ ile ve resume ipucuyla görünür) ve 130 koduyla çıkar. Coder'ın o ana kadar yazdığı dosyalar çalışma ağacında kalır — `git status` ile bak.

**`batonai runs list`'te "unfinished" görünen bir çalıştırma**, baton'un dışarıdan öldürüldüğü (ya da şu anda bu projede başka bir baton'un çalıştığı) anlamına gelir. Başarı değildir; `batonai resume <run-id>` devam ettirir.

**`revise`'da "no workspace changes were detected"** demek, Coder'ın *ikinci* geçişinin, o geçişten hemen önceki ağaca göre hiçbir şey değiştirmediği demektir — önceki değişikliklerin yerinde durur. Ya düzeltme zaten sağlanmıştı (Coder o zaman `CHANGE_STATUS: no_changes_needed` demeliydi) ya da bir izin engeline takıldı; artefakt ve ham loglar hangisi olduğunu söyler.

## 12. İyi sonuç almak için

- `.ai/project.md` dosyasını dürüstçe doldur — hem kalite hem maliyet açısından en yüksek getirisi olan tek dosya budur.
- Her çalıştırmaya temiz bir `git status` ile başla.
- Küçük işler için tüm pipeline yerine `batonai ask` kullan.
- `review.md` dosyasını oku — bazen Coder'ın kendisinin gözden kaçırdığı gerçek hataları yakalar (iki farklı model kullanmanın asıl amacı budur).
- Bir çalıştırmanın planı veya kodu kafa karışık görünüyorsa, o aşamaya tam olarak ne söylendiğini görmek için `.ai/runs/<id>/prompts/` klasörüne bak — genelde nedenini açıklar.
