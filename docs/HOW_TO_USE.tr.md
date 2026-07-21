# Nasıl Kullanılır — AI Coding Orchestrator ("baton")

Sade, pratik bir rehber. Teknik tasarım için [ARCHITECTURE.md](ARCHITECTURE.md) ve [DECISIONS.md](DECISIONS.md)'a, uygulamalı test komutları için [MANUAL_TESTING.md](MANUAL_TESTING.md)'a bakabilirsin. *(For English: [HOW_TO_USE.md](HOW_TO_USE.md))*

---

## 1. Bu nedir?

Düz İngilizce (veya Türkçe) bir isteği, birden fazla AI aracını otomatik olarak sırayla çalıştırarak bitmiş, gözden geçirilmiş koda dönüştüren tek bir komut:

```bash
ai "Ayarlar ekranına karanlık mod düğmesi ekle"
```

Bu tek satırın arkasında sırayla şunlar olur: bir **Planlayıcı (Planner)** uygulama planı yazar, bir **Kodlayıcı (Coder)** bu planı gerçek projende hayata geçirir, bir **İnceleyici (Reviewer)** sonucu plana göre kontrol eder ve her şey diskte, senin incelemen için saklanır. Bunların her biri farklı bir AI'dır (Codex, Claude Code) — hangisinin ne konuda iyi olduğuna göre seçilmiştir; tek bir model her şeyi yapmaz.

**Bu araç hiçbir kararı kendiliğinden/dinamik olarak vermez.** Aşamaların sırası, kimin neyi yapacağı, okuyabileceğin bir yapılandırma (config) dosyasıyla sabittir. İş akışın hakkında gizli bir "denetleyici" yapay zeka takdir yetkisi kullanmaz.

## 2. Başlamadan önce

Bilgisayarında kurulu ve giriş yapılmış olması gerekenler:
- `claude` (Claude Code)
- `codex` (Codex CLI)
- `agy` (Antigravity CLI)

Üçünü birden kontrol et:
```bash
ai doctor
```
Her satırda `✓ healthy` yazmalı. Biri yazmıyorsa, devam etmeden önce o sağlayıcının girişini/kurulumunu düzelt — orchestrator bozuk bir sağlayıcıyı atlayıp geçmez.

## 3. Kurulum

```bash
git clone <bu-repo>
cd <repo-klasörü>
uv tool install --editable .
```

Bu, `ai` komutunu **her klasörden** çalıştırabileceğin şekilde kurar — sadece bu klasörden değil. Kurulum "editable" (düzenlenebilir) olduğu için, bu kod tabanındaki gelecekteki güncellemeler otomatik olarak geçerli olur — yeniden kurmana gerek yok.

## 4. İlk çalıştırman

```bash
cd projen                    # herhangi bir gerçek proje, tercihen bir git deposu
ai init                      # proje başına bir kez — .ai/config.yaml + .ai/project.md oluşturur
ai "isteğin buraya"
```

`ai init`, projene bakar ve teknoloji yığınını (Flutter, Python, Node vb.) otomatik olarak tespit etmeye çalışır. Ardından `.ai/project.md` dosyasını aç ve kendi konvansiyonların hakkında birkaç dürüst satır ekle — "setState değil Riverpod kullanıyoruz", "testler test/ klasöründe" gibi, bir AI asistanının genelde yanlış yaptığı her şey. Bu dosya her aşamada, her çalıştırmada okunur; buraya yazacağın birkaç iyi satır defalarca işine yarar.

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

**Hiçbir pipeline çalıştırması commit veya push atmaz** — inceleme senin işin. Commit de öyle; ancak sen açıkça `ai publish --commit`/`--push` çalıştırırsan olur (§8.1). Bkz. §9.

## 7. Maliyet/kota rakamını anlamak

Bir çalıştırmadan sonra şuna benzer bir şey görürsün:
```
totals: tokens 400,123/8,500 · measured cost $0.85*
* cost = provider-reported API-equivalent value; on subscription plans it consumes plan quota — no per-run charge
```

**Abonelik kullanıyorsan** (Claude Pro/Max, ChatGPT Plus) — o dolar rakamı **bir fatura değildir**. Yapılan işin API-eşdeğeri değeridir, bilgi amaçlı gösterilir; gerçekte olan şey, planına dahil kullanım kotanın biraz azalmasıdır — o araçla yapacağın herhangi bir sohbet gibi. Gerçek para sadece token-başına-ödeme yapan API anahtarları kullanıyorsan öder.

Tam bir çalıştırma genelde 0,20–1,50 dolarlık kota-eşdeğeri "maliyet" gösterir — çoğunlukla sabit bir ek yüktür (her AI'nın projeni yeniden tanıması), gerçek işin büyüklüğüyle pek artmaz. Yani bu araç tek satırlık değişiklikler için doğru seçim değildir — küçük şeyler için `ai ask` kullan (§8).

### Yayıncı (Publisher) ücretsiz bir istemcide çalışır — bir uyarı

Opsiyonel Yayıncı aşaması (ve `ai ask --role publisher`), bu sığ "diff'ten bir commit mesajı taslağı çıkar" işini ücretli planlarından tamamen uzak tutmak için **opencode** adlı ücretsiz bir komut satırı istemcisine bağlanmıştır. opencode ücretsiz bir *istemcidir*, ama model yine de bir yerden gelir — onu opencode'un kendi `opencode auth` komutuyla bir ücretsiz katmana yönlendirirsin (bir [OpenRouter](https://openrouter.ai) `:free` modeli, bir Google AI Studio ücretsiz-katman anahtarı ya da bir opencode promosyon modeli). Bilmen gereken iki şey:

- Ücretsiz katmanlar **hız-sınırlıdır** ve genellikle **gönderdiğin veriyle model eğitebilirler**. Bir commit mesajı için bu sorun değildir; Yayıncı'nın yalnızca *diff'i ve planı* görmesinin, hiçbir zaman tüm kod tabanına yönlendirilmemesinin — ve kod okuyan aşamaların (Kodlayıcı, İnceleyici) buraya asla yönlendirilmemesinin sebebi budur.
- Ücretsiz katman kullanmak istemiyorsan, Yayıncı'nın sağlayıcısını proje bazında değiştir (ör. `.ai/config.yaml` içinde `roles: {publisher: {provider: codex}}`).

## 8. Günlük kullanılan komutlar

| Komut | Ne yapar |
|---|---|
| `ai "<istek>"` | Tüm pipeline'ı çalıştırır |
| `ai --with-designer "<istek>"` | Bu çalıştırma için Designer (UI/UX planlama) aşamasını da çalıştırır |
| `ai --with-publisher "<istek>"` | Bir commit mesajı + PR açıklaması da taslak olarak hazırlar (asla git komutu çalıştırmaz — bkz. §9) |
| `ai ask --role coder "<soru>"` | Tek bir AI'ya ucuz, tek seferlik bir çağrı — pipeline yok, artifact yok. Küçük sorular veya minik düzeltmeler için ideal |
| `ai doctor` | Tüm sağlayıcıların kurulu ve giriş yapılmış olduğunu kontrol eder |
| `ai init` | Bir projede `.ai/`'ı kurar (tekrar çalıştırmak güvenlidir; senin düzenlemelerinin üzerine asla yazmaz) |
| `ai config show` | Geçerli tam yapılandırmayı ve her değerin nereden geldiğini gösterir |
| `ai runs list` | Bu projedeki geçmiş tüm çalıştırmaları listeler: durum, maliyet, karar |
| `ai runs show <run-id>` | Bir çalıştırmanın detayını gösterir |
| `ai resume <run-id>` | Başarısız olan bir çalıştırmayı kaldığı yerden devam ettirir — daha önce başarılı olan aşamalar asla tekrar yapılmaz veya tekrar ödenmez |
| `ai revise "<düzeltme>"` | **Son** çalıştırma üzerinde sıfırdan başlamadan iterasyon yapar — Coder kendi oturumunu sürdürüp düzeltmeni uygular, sonra Reviewer tekrar bakar (bkz. §8.1) |
| `ai review` | Mevcut (commit'lenmemiş) değişikliklerini ikinci bir görüş için Reviewer'a gönderir — pipeline yok, hiçbir şeyi değiştirmez. `-m "şuna odaklan"` ile yönlendir |
| `ai publish` | Taslak commit mesajını gösterir (git yok). `--commit` ile commit'ler, `--push` ile commit + push yapar — git'e dokunan tek komut, o da yalnızca sen isteyince (bkz. §8.1) |

## 8.1 "Düzelt, sonra gönder" akışı

Pipeline bir kez çalışır ve durur — ama ilk seferde her şey nadiren tam istediğin gibi olur. İki komut bu döngüyü kapatır, böylece karşılıklı (sohbet gibi) çalışabilirsin:

```bash
ai "ayarlar ekranı ekle"            # 1. çalıştır
git diff                            # 2. Coder ne yaptı, incele
ai revise "başlığı sabitle"         # 3. tam olmadı mı? düzelt — aynı çalışma, sıfırdan başlamaz
                                    #    (Coder kendi işini hatırlar; --from planner ile planı yenile)
ai publish --push                   # 4. beğendin mi? her şeyi commit'le ve push et (önce onay ister)
```

`ai revise` **son** çalıştırmayı sürdürür: planı korur ve Coder'dan yeniden koşar; Coder kendi oturumunu sürdürüp düzeltmeni bir sonraki tur gibi ele alır — sonra Reviewer tekrar bakar. İstediğin kadar tekrarla. Memnun kaldığında `ai publish` commit mesajını taslaklar ve — yalnızca `--commit`/`--push` ile ve sen onayladıktan sonra — gerçekten commit'ler (`git add -A`) ve push'lar.

## 9. Bu aracın asla yapmayacağı şeyler (bunu bir kez oku, yeter)

- **Hiçbir pipeline aşaması git çalıştırmaz.** Pipeline kendiliğinden asla commit/push atmaz veya GitHub'a dokunmaz — ne varsayılan olarak, ne bir bayrakla. İsteğe bağlı Publisher aşaması bile sadece *bir metin taslağı yazar*. Git'in çalışmasının **tek** yolu, **senin** `ai publish --commit`/`--push` yazmandır — sana neyi commit'leyeceğini tam olarak gösteren ve önce onay isteyen ayrı, açık bir komut (§8.1). Sen her seferinde istemeden hiçbir şey geçmişine girmez.
- **Coder aşaması, her seferinde izin sormadan dosyalarını düzenler** (asıl amaç budur — yoksa her değişikliği elle onaylaman gerekirdi). Güvenlik ağı: temiz bir `git status` ile başla (araç temiz değilse uyarır), commit atmadan önce diff'i incele ve Reviewer aşamasının bulgularının seni yönlendirmesine izin ver.
- Bu güven seviyesi belirli bir proje için uygun değilse, bunun yerine `ai ask` kullan — sadece cevap verir, hiçbir şeyi düzenlemez.

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

## 11. Bir şey başarısız olduğunda

Çalıştırma başarısız olan aşamada durur — ondan sonrası hiç çalışmaz, o ana kadar yapılmış olan hiçbir şey kaybolmaz. Nedeni ve önerilen sonraki adımı görürsün:
```
next steps: ai resume <run-id> · ai doctor
```
`ai resume <run-id>` çalıştır; tam olarak kaldığı yerden devam eder ve daha önce başarılı olan her şeyi yeniden kullanır — aynı iş için asla iki kere ödemezsin.

## 12. İyi sonuç almak için

- `.ai/project.md` dosyasını dürüstçe doldur — hem kalite hem maliyet açısından en yüksek getirisi olan tek dosya budur.
- Her çalıştırmaya temiz bir `git status` ile başla.
- Küçük işler için tüm pipeline yerine `ai ask` kullan.
- `review.md` dosyasını oku — bazen Coder'ın kendisinin gözden kaçırdığı gerçek hataları yakalar (iki farklı model kullanmanın asıl amacı budur).
- Bir çalıştırmanın planı veya kodu kafa karışık görünüyorsa, o aşamaya tam olarak ne söylendiğini görmek için `.ai/runs/<id>/prompts/` klasörüne bak — genelde nedenini açıklar.
