# Kripto Spot Piyasalarında Otonom Portföy Yönetimi: Hibrit Yapay Zeka Yaklaşımlarının Teorik Temelleri

## 1. GİRİŞ

Kripto para piyasaları, geleneksel finansal piyasalardan farklı özellikleriyle yatırımcılar için hem büyük fırsatlar hem de önemli riskler sunmaktadır. 7/24 kesintisiz işlem gören bu piyasalar, yüksek volatilite, likidite değişkenliği ve hızlı trend değişimleri gibi benzersiz dinamiklere sahiptir. Bu karmaşık ve belirsiz ortamda optimal portföy yönetimi, insan yeteneklerinin ötesinde karmaşık hesaplamalar ve sürekli piyasa takibi gerektirmektedir.

Son yıllarda yapay zeka (AI) teknolojilerinin finansal piyasalara entegrasyonu, özellikle kripto para işlemlerinde devrim niteliğinde gelişmelere yol açmıştır. 2025 yılı itibariyle, AI sistemleri küresel ticaret hacminin %89'unu kontrol etmekte ve özellikle kripto piyasalarında insan yöneticilere göre önemli üstünlükler sergilemektedir. Ancak tek başına yapay zeka yaklaşımlarının sınırlamaları, farklı AI teknolojilerinin güçlü yönlerini birleştiren hibrit sistemlerin geliştirilmesini zorunlu kılmıştır.

Bu araştırma yazısı, kripto spot piyasalarında otonom portföy yönetimi için kullanılan hibrit yapay zeka yaklaşımlarının teorik temellerini kapsamlı bir şekilde incelemektedir. Yazı, kripto piyasa kavramlarından başlayarak, ensemble yöntemler, derin öğrenme-takviye öğrenmesi kombinasyonları, genetik algoritmalar-sinir ağları entegrasyonları ve teknik analiz-makine öğrenmesi birleşimlerini detaylı olarak ele almaktadır.

---

## 2. KRİPTO SPOT PİYASALARI: TEMEL KAVRAMLAR VE ÖZELLİKLER

### 2.1. Kripto Spot Piyasası Tanımı

Kripto spot piyasası, kripto para birimlerinin anlık teslimat ve ödeme karşılığında alınıp satıldığı piyasadır. Türev piyasalarından (vadeli işlemler, opsiyonlar) farklı olarak, spot piyasada işlemler gerçek zamanlı olarak gerçekleşir ve alıcı, satın aldığı varlığın doğrudan mülkiyetini elde eder.

**Spot Piyasanın Temel Özellikleri:**
- **Anlık İşlem Gerçekleşmesi:** Alım-satım emirleri eşleştiğinde işlem hemen tamamlanır
- **Fiziksel (Dijital) Teslimat:** Satın alınan kripto varlıklar alıcının cüzdanına transfer edilir
- **Kaldıraç Kullanımı Yok (Genelde):** Spot işlemlerde borçlanma olmadan kendi sermayenizle işlem yapılır
- **7/24 İşlem Sürekliliği:** Geleneksel borsaların aksine kesintisiz işlem görür

### 2.2. Kripto Piyasalarının Benzersiz Dinamikleri

Kripto piyasaları, geleneksel finansal piyasalardan farklı özellikler göstermektedir:

#### 2.2.1. Yüksek Volatilite

Kripto varlıklar, geleneksel varlıklara göre çok daha yüksek fiyat dalgalanmaları gösterir. Bitcoin gibi olgun kripto paraların günlük volatilitesi %5-10 aralığında olabilirken, altcoin'ler %20-50'yi aşan dalgalanmalar yaşayabilir. Bu volatilite hem yüksek getiri potansiyeli hem de önemli risk anlamına gelir.

**Volatilite Nedenleri:**
- Düşük piyasa kapitalizasyonu (geleneksel piyasalara göre)
- Spekülatif işlem hacmi
- Regulasyon belirsizlikleri
- Piyasa manipülasyonu riskleri
- Haber ve sosyal medya etkisi

#### 2.2.2. Likidite Özellikleri

Likidite, bir varlığın fiyatını önemli ölçüde etkilemeden ne kadar hızlı alınıp satılabileceğini gösterir. Kripto piyasalarında likidite, varlıklar ve borsalar arasında büyük farklılıklar gösterir:

- **Yüksek Likidite:** Bitcoin, Ethereum gibi büyük piyasa değerli varlıklar
- **Düşük Likidite:** Küçük piyasa değerli altcoin'ler
- **Borsa Bazlı Farklılıklar:** Aynı varlık farklı borsalarda farklı likidite seviyelerine sahip olabilir

#### 2.2.3. Piyasa Mikroyapısı

Kripto piyasalarının mikroyapısı, fiyat oluşumu ve işlem maliyetleri açısından önemlidir:

- **Emir Defteri Derinliği:** Farklı fiyat seviyelerindeki emir miktarları
- **Spread (Alış-Satış Farkı):** İşlem maliyetinin göstergesi
- **İşlem Ücretleri:** Borsa komisyonları ve blockchain ağ ücretleri
- **Slippage (Kayma):** Büyük emirlerin fiyat üzerindeki etkisi

### 2.3. Kripto Varlık Sınıflandırmaları

Portföy yönetimi açısından kripto varlıklar farklı kategorilere ayrılabilir:

#### 2.3.1. Piyasa Değerine Göre

- **Large Cap (Büyük Piyasa Değeri):** Bitcoin, Ethereum
- **Mid Cap (Orta Piyasa Değeri):** BNB, Cardano, Solana
- **Small Cap (Küçük Piyasa Değeri):** Yeni projeler ve niche altcoin'ler

#### 2.3.2. Fonksiyonlarına Göre

- **Store of Value (Değer Saklama):** Bitcoin
- **Smart Contract Platformları:** Ethereum, Solana, Cardano
- **Stablecoin'ler:** USDT, USDC, DAI (düşük volatilite, hedge amaçlı)
- **DeFi Token'ları:** Uniswap, Aave, Compound
- **Layer-2 Çözümleri:** Polygon, Arbitrum, Optimism

#### 2.3.3. Risk Profiline Göre

- **Düşük Risk:** Bitcoin, Ethereum, stablecoin'ler
- **Orta Risk:** Kurulu projeler (BNB, Cardano)
- **Yüksek Risk:** Yeni projeler, meme coin'ler

---

## 3. OTONOM PORTFÖY YÖNETİMİ: TEORİK ÇERÇEVE

### 3.1. Portföy Yönetimi Tanımı ve Hedefleri

Portföy yönetimi, yatırımcının finansal hedeflerine ulaşmak için varlıkların seçimi, ağırlıklandırılması ve sürekli olarak yeniden dengelenmesi sürecidir. Modern portföy teorisi, Harry Markowitz'in (1952) çalışmasına dayanarak risk-getiri optimizasyonunu temel alır.

**Portföy Yönetiminin Temel Hedefleri:**

1. **Getiri Maksimizasyonu:** Belirli bir risk seviyesinde en yüksek getiriyi elde etmek
2. **Risk Minimizasyonu:** Belirli bir getiri hedefi için riski minimize etmek
3. **Diversifikasyon:** Sistematik olmayan riski azaltmak için varlıkları çeşitlendirmek
4. **Likidite Yönetimi:** Gerektiğinde pozisyonları hızlıca kapatabilmek
5. **İşlem Maliyeti Optimizasyonu:** Ücret ve slippage'ı minimize etmek

### 3.2. Geleneksel vs Kripto Portföy Yönetimi

| Özellik | Geleneksel Piyasalar | Kripto Piyasalar |
|---------|---------------------|------------------|
| **İşlem Saatleri** | 9:30-16:00 (işlem günleri) | 7/24 kesintisiz |
| **Volatilite** | Düşük-Orta (%1-3 günlük) | Çok Yüksek (%5-50 günlük) |
| **Piyasa Olgunluğu** | Yüksek | Gelişmekte |
| **Regulasyon** | Sıkı düzenleme | Belirsiz/değişken |
| **Likidite** | Genelde yüksek | Varlığa göre değişken |
| **Bilgi Asimetrisi** | Düşük | Yüksek |
| **Karar Süresi** | Saatler/günler | Dakikalar/saniyeler |

### 3.3. Otonom Portföy Yönetimi Kavramı

Otonom portföy yönetimi, insan müdahalesine minimum düzeyde ihtiyaç duyarak, algoritmik sistemlerin portföy kararlarını otomatik olarak alıp uygulaması anlamına gelir.

**Otonom Sistemlerin Temel Bileşenleri:**

1. **Veri Toplama ve İşleme Modülü**
   - Fiyat verisi toplama (OHLCV - Open, High, Low, Close, Volume)
   - On-chain verileri (blockchain metrikleri)
   - Sosyal medya sentiment analizi
   - Makro ekonomik göstergeler

2. **Karar Alma Mekanizması**
   - Tahmin modelleri
   - Risk değerlendirmesi
   - Pozisyon boyutlandırma
   - Rebalancing stratejileri

3. **Yürütme Modülü**
   - Emir yönetimi
   - Borsa API entegrasyonu
   - Slippage optimizasyonu
   - İşlem maliyeti kontrolü

4. **İzleme ve Değerlendirme**
   - Performans metrikleri
   - Risk metrikleri
   - Model performans takibi

### 3.4. Performans Değerlendirme Metrikleri

Portföy yönetimi sistemlerinin değerlendirilmesinde kullanılan temel metrikler:

#### 3.4.1. Getiri Metrikleri

**Toplam Getiri (Total Return):**
```
Toplam Getiri = (Bitiş Değeri - Başlangıç Değeri) / Başlangıç Değeri × 100
```

**Yıllık Getiri (Annualized Return):**
```
Yıllık Getiri = (1 + Toplam Getiri)^(365/Gün Sayısı) - 1
```

#### 3.4.2. Risk-Ayarlı Getiri Metrikleri

**Sharpe Oranı:**
```
Sharpe Oranı = (Portföy Getirisi - Risksiz Getiri) / Portföy Standart Sapması
```
Sharpe oranı, birim risk başına ne kadar getiri elde edildiğini gösterir. Yüksek Sharpe oranı, daha iyi risk-ayarlı performans anlamına gelir.

**Sortino Oranı:**
```
Sortino Oranı = (Portföy Getirisi - Hedef Getiri) / Aşağı Yönlü Sapma
```
Sortino oranı, sadece olumsuz volatiliteyi (aşağı yönlü riski) dikkate alır.

**Calmar Oranı:**
```
Calmar Oranı = Yıllık Getiri / Maksimum Drawdown
```

#### 3.4.3. Risk Metrikleri

**Maksimum Drawdown (MDD):**
En yüksek noktadan en düşük noktaya kadar olan maksimum düşüş yüzdesi.

**Value at Risk (VaR):**
Belirli bir güven aralığında (%95 veya %99) belirli bir zaman diliminde (1 gün, 1 hafta) maksimum beklenen kayıp.

**Conditional Value at Risk (CVaR):**
VaR eşiğini aşan kayıpların ortalama değeri.

**Volatilite (Standart Sapma):**
Getirilerin dağılımının bir ölçüsü, yüksek volatilite yüksek risk anlamına gelir.

---

## 4. HİBRİT YAPAY ZEKA YAKLAŞIMLARI

### 4.1. Hibrit Yaklaşımların Gerekçesi

Tek başına kullanılan yapay zeka yöntemlerinin çeşitli sınırlamaları bulunmaktadır:

- **Makine Öğrenmesi Modelleri:** Sabit piyasa koşullarını varsayar, regime değişimlerine adapte olmakta zorlanır
- **Derin Öğrenme:** Çok fazla veri gerektirir, aşırı öğrenme (overfitting) riski yüksektir
- **Takviye Öğrenmesi:** Eğitim süresi uzundur, ödül fonksiyonu tasarımı zordur
- **Genetik Algoritmalar:** Yavaş yakınsama, lokal optimumlara takılma riski

Hibrit yaklaşımlar, farklı yöntemlerin güçlü yönlerini birleştirerek bu sınırlamaları aşmayı hedefler. Örneğin:
- Ensemble yöntemler, birden fazla modelin tahminlerini birleştirerek daha güvenilir sonuçlar üretir
- Derin öğrenme + takviye öğrenmesi, karmaşık durum uzaylarında optimal kararlar almayı sağlar
- Teknik analiz + makine öğrenmesi, piyasa dinamiklerini hem kural tabanlı hem de veri odaklı yaklaşımlarla değerlendirir

---

## 5. ENSEMBLE YÖNTEMLERİ

Ensemble öğrenme, birden fazla modelin tahminlerini birleştirerek tek bir modelden daha güçlü ve güvenilir sonuçlar elde etmeyi amaçlayan bir makine öğrenmesi tekniğidir. Kripto portföy yönetiminde ensemble yöntemler, piyasanın yüksek volatilitesi ve belirsizliği nedeniyle özellikle etkilidir.

### 5.1. Bagging (Bootstrap Aggregating)

#### 5.1.1. Temel Prensip

Bagging, Leo Breiman tarafından 1996'da geliştirilmiş bir ensemble tekniğidir. Temel fikir, veri setinin farklı alt örneklerinde (bootstrap örnekleri) aynı tipte modeller eğitmek ve tahminleri birleştirmektir.

**Bagging Algoritması:**

1. **Bootstrap Örnekleme:** Orijinal N büyüklüğündeki veri setinden, yerine koyarak (replacement) N büyüklüğünde m adet alt örnek oluştur
2. **Model Eğitimi:** Her alt örnek üzerinde bağımsız olarak bir model eğit (paralel eğitim mümkün)
3. **Tahmin Birleştirme:**
   - Regresyon: Tüm modellerin tahminlerinin ortalaması
   - Sınıflandırma: Çoğunluk oylaması (majority voting)

**Matematiksel Formülasyon:**

Bagging tahmini:
```
ŷ_bagging = (1/m) × Σ(i=1 to m) f_i(x)
```
Burada f_i(x), i'inci bootstrap örneği üzerinde eğitilmiş modelin tahminidir.

#### 5.1.2. Random Forest: Bagging'in En Popüler Uygulaması

Random Forest, birden fazla karar ağacının bagging ile birleştirilmesiyle oluşan güçlü bir ensemble modelidir.

**Random Forest'in Özellikleri:**

1. **Veri Seviyesinde Rastgelelik:** Her ağaç, bootstrap örneği üzerinde eğitilir
2. **Özellik Seviyesinde Rastgelelik:** Her düğümde, sadece rastgele seçilmiş bir özellik alt kümesi kullanılır
3. **Paralel Eğitim:** Ağaçlar birbirinden bağımsız eğitilebilir

**Kripto Portföy Yönetiminde Kullanımı:**

Random Forest, kripto piyasalarında şu amaçlarla kullanılabilir:
- **Fiyat Yönü Tahmini:** Bir kripto varlığın fiyatının artacağı veya azalacağı tahmini
- **Volatilite Tahmini:** Gelecekteki volatilite seviyesinin belirlenmesi
- **Grafik Patern Tanıma:** Teknik analiz paternlerinin (baş-omuz, üçgen, vb.) otomatik tespiti
- **Portföy Ağırlık Optimizasyonu:** Hangi varlıkların portföyde ne kadar ağırlıkta olacağına karar verme

**Avantajları:**
- Overfitting'e karşı dirençli
- Özellik önemliliğini ölçebilir (feature importance)
- Eksik veri ile çalışabilir
- Hem regresyon hem sınıflandırma için kullanılabilir

**Dezavantajları:**
- Yorumlanabilirlik düşük (black-box model)
- Eğitim ve tahmin süresi uzun olabilir
- Bellek kullanımı yüksek

#### 5.1.3. Kripto Trading'de Bagging Performansı

Yapılan araştırmalar, bagging yöntemlerinin kripto piyasalarında etkili olduğunu göstermektedir:

- 2025 yılı araştırmasında, ensemble learning yöntemleri kullanılarak yapılan grafik patern tanıma, geleneksel yöntemlere göre %18 daha yüksek doğruluk oranı elde etmiştir
- Random Forest modelleri, kripto piyasalarındaki gürültüyü filtreleyerek gerçek paternleri belirleme konusunda başarılı olmuştur
- Portföy yönetiminde bagging kullanan sistemler, drawdown'u %15-20 oranında azaltmıştır

### 5.2. Boosting

#### 5.2.1. Temel Prensip

Boosting, zayıf öğrenicilerin (weak learners) sıralı olarak eğitildiği ve her yeni modelin önceki modellerin hatalarını düzeltmeye odaklandığı bir ensemble tekniğidir. Bagging'den farklı olarak modeller paralel değil, sıralı olarak eğitilir.

**Boosting'in Temel Mantığı:**

1. İlk model tüm veri seti üzerinde eğitilir
2. Modelin yanlış tahmin ettiği örneklere daha fazla ağırlık verilir
3. Yeni model, ağırlıklandırılmış veri seti üzerinde eğitilir
4. Bu süreç belirlenen iterasyon sayısı kadar tekrarlanır
5. Son tahmin, tüm modellerin ağırlıklı toplamıdır

**Matematiksel Formülasyon:**

Boosting tahmini:
```
F(x) = Σ(m=1 to M) α_m × f_m(x)
```
Burada α_m, m'inci modelin ağırlığı ve f_m(x) tahmindir.

#### 5.2.2. Gradient Boosting

Gradient Boosting, her yeni modelin bir önceki modelin rezidüellerini (hatalarını) tahmin etmeye çalıştığı bir boosting türüdür.

**Gradient Boosting Algoritması:**

1. İlk tahminle başla: F_0(x) = argmin_γ Σ L(y_i, γ)
2. Her m = 1'den M'e kadar:
   a. Rezidüelleri hesapla: r_im = -[∂L(y_i, F(x_i))/∂F(x_i)]
   b. Rezidüeller üzerinde bir model eğit: h_m
   c. Adım uzunluğunu optimize et: ρ_m
   d. Modeli güncelle: F_m(x) = F_{m-1}(x) + ρ_m × h_m(x)

**XGBoost (Extreme Gradient Boosting):**

XGBoost, gradient boosting'in optimize edilmiş ve ölçeklenebilir bir versiyonudur. Kripto trading'de en yaygın kullanılan boosting algoritmasıdır.

**XGBoost'un Özellikleri:**
- Regularization (L1 ve L2) ile overfitting'i önler
- Paralel işlem desteği ile hızlı eğitim
- Eksik veri ile çalışabilme
- Tree pruning (budama) ile model optimizasyonu
- Built-in cross-validation

**Kripto Piyasalarında Kullanımı:**

Araştırmalarda XGBoost'un kripto tahminlerinde önemli başarılar elde ettiği görülmüştür:
- Trend reversal (trend dönüşü) tahmininde ARIMA modellerine göre %23.7 daha düşük hata oranı
- EUR/USD forex çiftinde %62 kazanma oranı (Chen et al., 2019)
- Bitcoin patern tespitinde kullanılan SVM tabanlı sistemler, 2022'de %22 yıllık getiri sağlamıştır

**LightGBM (Light Gradient Boosting Machine):**

Microsoft tarafından geliştirilen LightGBM, büyük veri setlerinde XGBoost'tan daha hızlı çalışır.

**LightGBM'in Avantajları:**
- Leaf-wise (yaprak bazlı) ağaç büyütme ile daha iyi doğruluk
- Histogram-based algorithm ile hızlı eğitim
- Düşük bellek kullanımı
- Kategorik özellikler için native destek

#### 5.2.3. AdaBoost (Adaptive Boosting)

AdaBoost, ilk boosting algoritmalarından biridir ve sınıflandırma problemlerinde etkilidir.

**AdaBoost Algoritması:**

1. Tüm örneklere eşit ağırlık ver: w_i = 1/N
2. Her m = 1'den M'e kadar:
   a. Ağırlıklı veri seti üzerinde model eğit
   b. Ağırlıklı hata oranını hesapla: ε_m
   c. Model ağırlığını hesapla: α_m = 0.5 × ln((1-ε_m)/ε_m)
   d. Örnek ağırlıklarını güncelle (yanlış sınıflandırılanlara daha fazla ağırlık)

**Kripto Trading'de Kullanımı:**
- Buy/Sell/Hold sinyali üretimi
- Overbought/Oversold koşullarının tespiti
- Trend değişikliği sinyalleri

### 5.3. Stacking (Stacked Generalization)

#### 5.3.1. Temel Prensip

Stacking, farklı tipte modellerin (heterogeneous models) tahminlerini bir meta-model (üst seviye model) kullanarak birleştiren gelişmiş bir ensemble tekniğidir.

**Stacking Mimarisi:**

```
[Veri Seti]
    ↓
[Base Modeller: Model 1, Model 2, ..., Model N]
    ↓
[Base Model Tahminleri]
    ↓
[Meta-Model]
    ↓
[Final Tahmin]
```

**Stacking Algoritması:**

1. **Base Model Eğitimi:**
   - Veri setini K fold'a böl (cross-validation için)
   - Her base modeli K-1 fold üzerinde eğit, 1 fold üzerinde tahmin yap
   - Tüm fold'lar için tekrarla, böylece her örnek için base model tahminleri elde et

2. **Meta-Model Eğitimi:**
   - Base model tahminlerini yeni özellikler olarak kullan
   - Orijinal hedef değişken ile meta-modeli eğit

3. **Tahmin Aşaması:**
   - Yeni veri üzerinde tüm base modeller tahmin yapar
   - Base model tahminleri meta-modele girdi olarak verilir
   - Meta-model final tahmini üretir

#### 5.3.2. Kripto Portföy Yönetiminde Stacking

**Base Model Kombinasyonları:**

Kripto trading'de başarılı stacking setups:

1. **Çeşitli Makine Öğrenmesi Modelleri:**
   - Random Forest (trend yakalama)
   - XGBoost (karmaşık ilişkiler)
   - SVM (non-linear pattern recognition)
   - Logistic Regression (basit linear ilişkiler)

2. **Time-Series ve Geleneksel ML Karışımı:**
   - LSTM (zaman serisi özellikleri)
   - GRU (kısa-orta vade trendler)
   - Random Forest (teknik göstergeler)
   - Gradient Boosting (makro faktörler)

3. **Meta-Model Seçimi:**
   - Linear Regression: Basit ve yorumlanabilir
   - Neural Network: Karmaşık ilişkileri yakalayabilir
   - XGBoost: Güçlü performans, overfitting riski yönetilebilir

**Performans Sonuçları:**

Araştırmalar, stacking'in kripto piyasalarında üstün performans sergilediğini göstermektedir:

- 2025 yılı çalışmasında, Stacking modeli %81.80 doğruluk, %81.49 F1-score ve %88.43 AUC-ROC ile en iyi performansı sergilemiştir
- Geleneksel yöntemler olan Naive Bayes ve Decision Tree'lere göre önemli üstünlük sağlamıştır
- Weng et al. (2018) araştırmasında, stacked ensemble yaklaşımı, standalone modellere göre %5.2 daha yüksek hisse senedi fiyat tahmin doğruluğu elde etmiştir

#### 5.3.3. Stacking'in Avantaj ve Dezavantajları

**Avantajları:**
- En yüksek tahmin doğruluğu
- Farklı model tiplerinin güçlü yönlerini birleştirir
- Variance ve bias'ı aynı anda azaltabilir
- Overfitting riskini düzgün cross-validation ile yönetebilir

**Dezavantajları:**
- Hesaplama maliyeti yüksek (iki aşamalı eğitim)
- Karmaşıklık nedeniyle yorumlanabilirlik düşük
- Eğitim süresi uzun
- Hyperparameter tuning daha zor

### 5.4. Ensemble Yöntemlerinin Karşılaştırması

| Özellik | Bagging | Boosting | Stacking |
|---------|---------|----------|----------|
| **Eğitim Şekli** | Paralel | Sıralı | İki aşamalı |
| **Model Tipi** | Homojen | Homojen | Heterojen |
| **Hedef** | Variance azaltma | Bias azaltma | Her ikisini de azaltma |
| **Hız** | Hızlı (paralel) | Yavaş (sıralı) | En yavaş |
| **Overfitting Riski** | Düşük | Orta-Yüksek | Orta |
| **Doğruluk** | İyi | Çok iyi | En iyi |
| **Kullanım Kolaylığı** | Kolay | Orta | Zor |
| **Kripto Trading'de Önerilen Durum** | Volatilite tahmini | Trend tahmini | Karmaşık portföy optimizasyonu |

---

## 6. DERİN ÖĞRENME + TAKVİYE ÖĞRENMESİ (DEEP REINFORCEMENT LEARNING)

Deep Reinforcement Learning (DRL), derin öğrenmenin özellik çıkarma gücünü takviye öğrenmesinin sıralı karar alma yeteneği ile birleştirir. Kripto portföy yönetimi gibi karmaşık, dinamik ve belirsiz ortamlarda son derece etkilidir.

### 6.1. Takviye Öğrenmesi (Reinforcement Learning) Temelleri

#### 6.1.1. Temel Kavramlar

Takviye öğrenmesi, bir ajanın (agent) bir çevre (environment) ile etkileşime girerek, ödülleri maksimize edecek şekilde optimal politika (policy) öğrenmesidir.

**Temel Bileşenler:**

1. **Agent (Ajan):** Karar veren varlık (trading bot)
2. **Environment (Çevre):** Ajanın içinde bulunduğu ortam (kripto piyasası)
3. **State (Durum) - s:** Çevrenin mevcut durumu (fiyatlar, göstergeler, portföy durumu)
4. **Action (Aksiyon) - a:** Ajanın alabileceği kararlar (al, sat, tut, pozisyon boyutu)
5. **Reward (Ödül) - r:** Aksiyonun sonucunda alınan geri bildirim (kar/zarar)
6. **Policy (Politika) - π:** Durumdan aksiyona mapping fonksiyonu
7. **Value Function - V(s):** Bir durumun beklenen toplam ödülü
8. **Q-Function - Q(s,a):** Bir durum-aksiyon çiftinin beklenen toplam ödülü

#### 6.1.2. Markov Decision Process (MDP)

RL problemleri genellikle MDP olarak modellenir:

**MDP Tanımı:** < S, A, P, R, γ >
- S: Durum uzayı
- A: Aksiyon uzayı
- P: Geçiş olasılığı fonksiyonu P(s'|s,a)
- R: Ödül fonksiyonu R(s,a,s')
- γ: Discount factor (gelecek ödüllerinin değer kaybı)

**Bellman Denklemi:**
```
V(s) = max_a [ R(s,a) + γ × Σ P(s'|s,a) × V(s') ]
Q(s,a) = R(s,a) + γ × Σ P(s'|s,a) × max_a' Q(s',a')
```

### 6.2. Değer Tabanlı Yöntemler: Deep Q-Network (DQN)

#### 6.2.1. Q-Learning

Q-Learning, model-free, off-policy bir RL algoritmasıdır. Optimal aksiyon-değer fonksiyonunu (Q-function) öğrenir.

**Q-Learning Güncelleme Kuralı:**
```
Q(s,a) ← Q(s,a) + α × [r + γ × max_a' Q(s',a') - Q(s,a)]
```

Burada:
- α: Öğrenme oranı (learning rate)
- r: Alınan ödül
- γ: Discount factor
- s': Yeni durum

#### 6.2.2. Deep Q-Network (DQN)

DQN, Q-learning'i derin sinir ağları ile birleştirir. Yüksek boyutlu durum uzaylarında (örneğin görsel veriler veya çok sayıda teknik gösterge) Q-fonksiyonunu yaklaşık olarak temsil eder.

**DQN Mimarisi:**

```
[Durum (State): Fiyat, Göstergeler, Portföy]
    ↓
[Sinir Ağı (Deep Neural Network)]
    ↓
[Q-Değerleri: Her aksiyon için]
    ↓
[Aksiyon Seçimi: ε-greedy veya max Q]
```

**DQN'in Yenilikleri:**

1. **Experience Replay:**
   - Geçmiş deneyimleri (s, a, r, s') bir hafızada sakla
   - Eğitim için rastgele mini-batch'ler çek
   - Bu, veri korelasyonunu kırar ve eğitimi stabilize eder

2. **Target Network:**
   - İki ağ kullanır: Q-network ve Target Q-network
   - Target network, Q-network'ten daha yavaş güncellenir
   - Bu, öğrenme hedefinin stabilize olmasını sağlar

**DQN Loss Fonksiyonu:**
```
L(θ) = E[(r + γ × max_a' Q(s',a';θ^-) - Q(s,a;θ))^2]
```
Burada θ, Q-network parametreleri ve θ^-, target network parametreleridir.

#### 6.2.3. DQN Varyantları

**Double DQN (DDQN):**
- DQN'in overestimation problemini çözer
- Aksiyon seçimi ve değerlendirme için farklı ağlar kullanır
```
Q_target = r + γ × Q(s', argmax_a' Q(s',a';θ); θ^-)
```

**Dueling DQN:**
- Q-değerini iki bileşene ayırır:
  - V(s): Durum değeri
  - A(s,a): Advantage fonksiyonu (aksiyonun avantajı)
```
Q(s,a) = V(s) + (A(s,a) - mean_a' A(s,a'))
```

#### 6.2.4. Kripto Trading'de DQN Uygulamaları

**Durum Uzayı (State Space):**
Kripto trading'de durum, şu bilgileri içerebilir:
- Fiyat verileri: OHLCV (son N günlük)
- Teknik göstergeler: RSI, MACD, Bollinger Bands, EMA, vb.
- On-chain metrikler: İşlem hacmi, active addresses, hash rate
- Portföy durumu: Mevcut pozisyonlar, nakit miktarı
- Makro göstergeler: BTC dominance, market cap, fear & greed index

**Aksiyon Uzayı (Action Space):**
- **Discrete Actions:** Buy, Sell, Hold
- **Continuous Actions:** Pozisyon büyüklüğü (-1 ile +1 arası, -1 full short, +1 full long)
- **Multi-discrete:** Her varlık için ayrı aksiyon

**Ödül Fonksiyonu (Reward Function):**

Farklı ödül fonksiyonları kullanılabilir:

1. **Basit Kar/Zarar:**
   ```
   r_t = (portföy_değeri_t - portföy_değeri_{t-1}) / portföy_değeri_{t-1}
   ```

2. **Sharpe Ratio:**
   ```
   r_t = (getiri_t - risksiz_oran) / volatilite_t
   ```

3. **Risk-Ayarlı Getiri:**
   ```
   r_t = getiri_t - λ × risk_t
   ```
   Burada λ, risk ceza katsayısıdır.

4. **İşlem Maliyeti Dahil:**
   ```
   r_t = getiri_t - trading_fee - slippage
   ```

**DQN Kripto Trading Performansı:**

Araştırmalar, DQN'in kripto piyasalarında etkili olduğunu göstermektedir:

- 2024 yılı araştırmasında, DQN modeli 6 kripto para birimi üzerinde test edilmiş ve $1000 başlangıç sermayesi ile $740 ROI (%12.3 ortalama ROI) elde etmiştir
- BinanceCoin için %63.98 ROI başarısı
- DDQN, özellikle Ethereum piyasasında iyi performans göstermiştir
- 2022 yılı araştırmasında, DD-DQN tabanlı Bitcoin trading sistemi, Sharpe ratio ve profit reward fonksiyonları ile değerlendirilmiş ve karlı sonuçlar vermiştir

### 6.3. Politika Tabanlı Yöntemler

#### 6.3.1. Policy Gradient Yöntemleri

Değer tabanlı yöntemlerin aksine, politika tabanlı yöntemler doğrudan optimal politikayı öğrenir.

**Policy Gradient Teoremi:**
```
∇_θ J(θ) = E[∇_θ log π(a|s;θ) × Q(s,a)]
```

Burada:
- J(θ): Politika performans metriği
- π(a|s;θ): Parametrize edilmiş politika
- θ: Politika ağı parametreleri

#### 6.3.2. Actor-Critic Yöntemleri

Actor-Critic, politika ve değer fonksiyonunu birlikte öğrenir:
- **Actor:** Politika fonksiyonunu öğrenir (aksiyonları seçer)
- **Critic:** Değer fonksiyonunu öğrenir (aksiyonları değerlendirir)

**Advantage Actor-Critic (A2C):**

A2C, advantage fonksiyonunu kullanarak politika gradientini hesaplar:
```
A(s,a) = Q(s,a) - V(s)
Policy gradient: ∇_θ J(θ) = E[∇_θ log π(a|s;θ) × A(s,a)]
```

**Asynchronous Advantage Actor-Critic (A3C):**

A3C, birden fazla agent'ı paralel olarak farklı environment kopyalarında çalıştırır ve gradient güncellemelerini asenkron olarak birleştirir.

**A3C'nin Avantajları:**
- Paralel eğitim ile hızlı öğrenme
- Experience replay'e gerek yok (asenkron yapı korelasyonu kırar)
- Multiple cryptocurrency pair'ler üzerinde eş zamanlı trading
- Cross-exchange arbitrage

**Kripto Trading'de A3C Kullanımı:**

A3C, kripto piyasalarında şu alanlarda kullanılmaktadır:
- Birden fazla kripto çiftinde eş zamanlı işlem yapma
- Farklı exchange'lerde aynı anda fiyat farkı arbitrajı
- Multi-asset portföy yönetimi

2025 araştırmasında, A3C sistemi birden fazla varlıkta paralel deneyim biriktirerek ve gradient güncellemelerini asenkron olarak paylaşarak daha hızlı yakınsama sağlamıştır.

#### 6.3.3. Proximal Policy Optimization (PPO)

PPO, OpenAI tarafından geliştirilmiş, stabil ve etkili bir politika optimizasyon algoritmasıdır.

**PPO'nun Ana Fikri:**

Politika güncellemelerini sınırlandırarak, öğrenme sürecini stabilize eder. Çok büyük politika değişiklikleri, performansın aniden düşmesine neden olabilir.

**PPO Objective Function:**
```
L_CLIP(θ) = E[ min(r_t(θ) × A_t, clip(r_t(θ), 1-ε, 1+ε) × A_t) ]
```

Burada:
- r_t(θ) = π_θ(a_t|s_t) / π_θ_old(a_t|s_t): Olasılık oranı
- ε: Clipping parametresi (genelde 0.1-0.2)
- A_t: Advantage estimatörü

**PPO'nun Avantajları:**
- Stabil öğrenme
- Hyperparameter tuning'e daha az hassas
- Hem discrete hem continuous action space'lerde çalışır
- Sample efficiency açısından iyi

**Kripto Trading'de PPO:**

PPO, kripto portföy yönetiminde en popüler algoritmalardandır:

- 2024 yılı araştırmasında, PPO kullanılan bir sistem 3 yıllık test periyodunda %48 kümülatif getiri elde etmiş, equal-weighted portföyü %21 ve mean-variance optimized portföyü %14 geride bırakmıştır
- Sharpe oranı 1.78 ile risk-ayarlı getiri konusunda üstün performans
- FinRL framework'ünde PPO, volatil piyasa koşullarında geleneksel ve heuristic tabanlı allocation stratejilerini aşmıştır
- Candlestick image'ları ile birlikte kullanıldığında, temporal ve spatial bilgileri yakalayarak daha iyi sonuçlar vermiştir

#### 6.3.4. Soft Actor-Critic (SAC)

SAC, maximum entropy RL framework'ünü kullanan off-policy bir algoritmadir. Hem sample efficiency hem de stability açısından üstündür.

**SAC'ın Temel Prensibi:**

Sadece ödülü maksimize etmek yerine, ödülü maksimize ederken aynı zamanda politikanın entropisini (rastgeleliğini) de maksimize eder:
```
J(π) = E[ Σ_t (r_t + α × H(π(·|s_t))) ]
```

Burada H(π) politikanın entropisidir.

**SAC'ın Avantajları:**
- Exploration-exploitation dengesini otomatik olarak yönetir
- Robust ve stabil öğrenme
- Sample efficiency yüksek (off-policy)
- Continuous action space'lerde mükemmel

**Kripto Portföy Yönetiminde SAC:**

SAC, özellikle continuous action space gerektiren portföy yönetimi problemlerinde etkilidir:
- Multi-asset continuous weight allocation
- Entropy bonus sayesinde aşırı aggressive trading'den kaçınma
- Off-policy olması sayesinde historical data'dan verimli öğrenme

### 6.4. DRL Algoritmalarının Karşılaştırması

| Algoritma | Tip | Policy | Action Space | Sample Efficiency | Stability | Kripto Trading İçin |
|-----------|-----|--------|--------------|-------------------|-----------|---------------------|
| **DQN** | Value-based | Off-policy | Discrete | Orta | Orta | Basit buy/sell/hold stratejileri |
| **DDQN** | Value-based | Off-policy | Discrete | Orta | Yüksek | DQN'den daha stabil |
| **A2C** | Actor-Critic | On-policy | Her ikisi | Düşük | Orta | Multi-market trading |
| **A3C** | Actor-Critic | On-policy | Her ikisi | Orta | Orta | Paralel environment'ler |
| **PPO** | Actor-Critic | On-policy | Her ikisi | Orta | Yüksek | **En popüler, genel amaçlı** |
| **SAC** | Actor-Critic | Off-policy | Continuous | Yüksek | Yüksek | **Portföy weight allocation** |
| **TD3** | Actor-Critic | Off-policy | Continuous | Yüksek | Yüksek | Continuous action trading |

### 6.5. DRL'de Önemli Konular

#### 6.5.1. Exploration vs Exploitation

**ε-Greedy Exploration (DQN için):**
- ε olasılıkla rastgele aksiyon seç (exploration)
- (1-ε) olasılıkla en iyi aksiyonu seç (exploitation)
- ε başlangıçta yüksek (örn. 1.0), zamanla azalır (örn. 0.01'e)

**Entropy Regularization (PPO, SAC için):**
- Politikanın entropisini ödül fonksiyonuna ekle
- Aşırı deterministik politikalardan kaçın

#### 6.5.2. Reward Shaping

Kripto trading'de ödül fonksiyonu tasarımı kritiktir:

**İyi Ödül Fonksiyonu Özellikleri:**
1. Sparse olmama: Her step'te bilgi vermeli
2. Aligned with goal: Gerçek hedefle uyumlu olmalı
3. Stationary: Zaman içinde çok değişmemeli
4. Scalable: Farklı piyasa koşullarında çalışmalı

**Örnek Composite Reward:**
```
r_t = w1 × profit_t + w2 × sharpe_t - w3 × drawdown_t - w4 × transaction_cost_t
```

#### 6.5.3. Overfitting ve Generalization

**Overfitting Riskleri:**
- Historical data'ya aşırı uyum
- Regime changes'e adapte olamama
- Live trading'de düşük performans

**Önleme Stratejileri:**
1. **Regularization:** L1/L2 regularization, dropout
2. **Early Stopping:** Validation loss artarken eğitimi durdur
3. **Ensemble DRL:** Birden fazla agent'ın kararlarını birleştir
4. **Online Learning:** Model'i sürekli yeni data ile güncelle
5. **Walk-Forward Validation:** Zaman serisi cross-validation

---

## 7. GENETİK ALGORİTMALAR + SİNİR AĞLARI (NEUROEVOLUTION)

Neuroevolution, sinir ağlarının yapısını (topology) ve ağırlıklarını evrimsel algoritmalarla optimize etme yaklaşımıdır. Kripto portföy yönetiminde, hem trading stratejisi parametrelerini hem de model mimarisini aynı anda optimize edebilir.

### 7.1. Genetik Algoritmalar (GA) Temelleri

#### 7.1.1. Temel Kavramlar

Genetik algoritmalar, doğal seçilim ve genetik ilkelerini taklit eden optimizasyon algoritmalardır.

**GA Bileşenleri:**

1. **Chromosome (Kromozom):** Çözüm adayı (örn. trading stratejisi parametreleri)
2. **Gene (Gen):** Kromozomun bir bileşeni (örn. bir parametre değeri)
3. **Population (Popülasyon):** Kromozom kümesi
4. **Fitness Function:** Kromozomun kalitesini değerlendiren fonksiyon
5. **Selection:** En iyi kromozomları seçme
6. **Crossover:** İki kromozomu birleştirerek yeni kromozom oluşturma
7. **Mutation:** Kromozomda rastgele değişiklik yapma

#### 7.1.2. Genetik Algoritma Süreci

**1. Initialization (Başlatma):**
```
Rastgele N adet kromozom oluştur
```

**2. Evaluation (Değerlendirme):**
```
Her kromozomun fitness değerini hesapla
```

**3. Selection (Seçim):**
Farklı seçim yöntemleri:
- **Roulette Wheel:** Fitness oranında seçme şansı
- **Tournament Selection:** Rastgele k kromozom seç, en iyisini al
- **Rank Selection:** Fitness'a göre sırala, sıraya göre seç

**4. Crossover (Çaprazlama):**
```
Parent 1: [a, b, c, d, e]
Parent 2: [f, g, h, i, j]
         ↓ (single-point crossover at position 2)
Child 1:  [a, b, h, i, j]
Child 2:  [f, g, c, d, e]
```

Crossover tipleri:
- Single-point crossover
- Two-point crossover
- Uniform crossover

**5. Mutation (Mutasyon):**
```
Chromosome: [a, b, c, d, e]
           ↓ (mutate position 3 with probability p_m)
Mutated:    [a, b, c', d, e]
```

**6. Replacement:**
```
Yeni nesli oluştur (yeni kromozomlar + seçilen en iyiler)
```

**7. Termination:**
```
Maksimum nesil sayısına ulaşıldı mı veya fitness kriteri karşılandı mı?
Evet → Dur
Hayır → 2. adıma dön
```

### 7.2. Kripto Trading'de Genetik Algoritma Uygulamaları

#### 7.2.1. Trading Stratejisi Parametre Optimizasyonu

**Problem Tanımı:**

Bir trading stratejisinin parametrelerini optimize etme. Örneğin, dual RSI crossover stratejisi:

**Parametreler:**
- RSI_fast period (örn. 5-20 arası)
- RSI_slow period (örn. 20-50 arası)
- Overbought threshold (örn. 60-80 arası)
- Oversold threshold (örn. 20-40 arası)
- Moving average filter periyodu
- Stop-loss %
- Take-profit %

**Kromozom Gösterimi:**
```
[RSI_fast, RSI_slow, OB_threshold, OS_threshold, MA_period, SL%, TP%]
Örnek: [14, 30, 70, 30, 50, 5, 15]
```

**Fitness Fonksiyonu:**
```
fitness = w1 × total_return + w2 × sharpe_ratio - w3 × max_drawdown - w4 × num_trades
```

#### 7.2.2. Crypto Genetic Algorithm Agent (CGA-Agent)

2025 yılında yapılan araştırma, genetik algoritmaları intelligent multi-agent coordination ile birleştiren CGA-Agent framework'ünü geliştirmiştir.

**CGA-Agent Özellikleri:**

1. **Real-time Market Intelligence Integration:**
   - Piyasa mikroyapı bilgilerini gerçek zamanlı entegre eder
   - Volatilite, trend strength, liquidity metriklerini kullanır

2. **Adaptive Performance Feedback:**
   - Stratejinin performans metriklerini evrim sürecine dahil eder
   - Market regime'lerine göre adaptif optimizasyon

3. **Dynamic Parameter Space:**
   - Statik parametre uzayı yerine, piyasa koşullarına göre değişen dinamik uzay

**CGA-Agent Performansı:**

Üç major kripto para üzerinde test edilmiştir:
- **BTC:** %29 total return artışı
- **ETH:** %550 total return artışı
- **BNB:** %169 total return artışı
- Sharpe ve Sortino ratio'larında önemli iyileşmeler

### 7.3. Neuroevolution: Sinir Ağlarını Evrimleştirme

Neuroevolution, sinir ağlarının hem ağırlıklarını hem de yapısını genetik algoritmalarla optimize eder.

#### 7.3.1. Neuroevolution Tipleri

**1. Conventional Neuroevolution:**
- Sadece ağırlıkları optimize eder (topology sabit)
- Daha basit ve hızlı

**2. TWEANN (Topology and Weight Evolving ANN):**
- Hem topology hem weights optimize edilir
- NEAT, HyperNEAT gibi algoritmalar

#### 7.3.2. NEAT (NeuroEvolution of Augmenting Topologies)

NEAT, Kenneth Stanley ve Risto Miikkulainen tarafından 2002'de geliştirilmiş, en popüler neuroevolution algoritmalarından biridir.

**NEAT'in Yenilikleri:**

1. **Başlangıçta Minimal Yapı:**
   - Sadece input ve output neuronları ile başla
   - Evrim sürecinde yavaşça karmaşıklaştır

2. **Historical Markings (Innovation Numbers):**
   - Her yeni gen (connection/neuron) bir innovation number alır
   - Crossover sırasında matching gene'leri bulmayı kolaylaştırır

3. **Speciation (Türleşme):**
   - Benzer topology'lere sahip kromozomları aynı species'te grupla
   - Her species kendi içinde evolve olur
   - Bu, yeni yapıların erken ölümünü önler

**NEAT Mutation Operatörleri:**

1. **Add Connection:**
   - İki neuron arasına yeni bağlantı ekle
   
2. **Add Node:**
   - Mevcut bir bağlantıyı kes
   - Araya yeni bir neuron ekle
   - İki yeni bağlantı oluştur (giriş → yeni neuron → çıkış)

3. **Mutate Weights:**
   - Mevcut ağırlıkları perturbe et

**NEAT Crossover:**

```
Parent 1: [1-2-3-4-5]    (innovation numbers)
Parent 2: [1-2-4-5-6-7]

Child:    [1-2-3-4-5-6]  (matching ve disjoint gene'leri birleştir)
```

#### 7.3.3. Kripto Portföy Yönetiminde NEAT

**Uygulama Alanları:**

1. **Trading Signal Generation:**
   - Input: Fiyat verileri, teknik göstergeler
   - Hidden layers: NEAT tarafından evolve edilir
   - Output: Buy/Sell/Hold sinyali

2. **Portfolio Weight Optimization:**
   - Input: Varlık getiri tahminleri, risk metrikleri
   - Output: Her varlık için ağırlık (toplamı 1)

3. **Risk Management:**
   - Input: Portföy durumu, piyasa volatilitesi
   - Output: Pozisyon boyutu, stop-loss seviyeleri

**NEAT'in Avantajları:**
- Gradient'e ihtiyaç yok (gradient-free)
- Local optimum'a takılma riski düşük
- Karmaşık non-linear ilişkileri keşfedebilir
- Minimal network'ten başlayarak gereksiz karmaşıklıktan kaçınır

**NEAT'in Dezavantajları:**
- Eğitim süresi uzun olabilir
- Yüksek boyutlu problemlerde zorluk
- Hyperparameter tuning gerektirir

### 7.4. Differential Evolution (DE)

Differential Evolution, continuous optimization problemleri için etkili bir evrimsel algoritmadır.

**DE Algoritması:**

1. **Initialization:**
   ```
   Rastgele N adet vektör oluştur
   ```

2. **Mutation:**
   ```
   Üç rastgele vektör seç: x_r1, x_r2, x_r3
   Mutant oluştur: v_i = x_r1 + F × (x_r2 - x_r3)
   ```
   Burada F, mutation factor'dür (genelde 0.5-1.0)

3. **Crossover:**
   ```
   Trial vector: u_i,j = { v_i,j if rand() < CR or j = j_rand
                          { x_i,j otherwise
   ```
   Burada CR, crossover probability'dir

4. **Selection:**
   ```
   x_i,next = { u_i if f(u_i) < f(x_i)
              { x_i otherwise
   ```

**Kripto Portföy Optimizasyonunda DE:**

2022 araştırmasında, Differential Evolution algoritması GARCH C-Vine copula modeli ile birlikte kullanılarak 8 kripto para birimi portföyü optimize edilmiştir:

- K-means clustering ile varlıklar gruplandırılmış
- DE ile optimal allocation stratejisi belirlenmiş
- Conditional Value-at-Risk (CVaR) minimize edilmiş
- Stablecoin'ler (True-USD) diğer varlıklarla negatif korelasyon göstermiş
- Türbülanslı piyasalarda safe haven olarak işlev görmüş

### 7.5. Hibrit GA + Neural Network Yaklaşımları

#### 7.5.1. GA ile Neural Network Weight Optimization

Gradient descent yerine GA kullanarak sinir ağı ağırlıklarını optimize etme:

**Avantajları:**
- Gradient hesaplamaya gerek yok
- Non-differentiable activation function'lar kullanılabilir
- Local minima'ya takılma riski düşük

**Dezavantajları:**
- Büyük ağlar için çok yavaş
- Sample efficiency düşük
- Milyon parametreli modern deep learning için uygun değil

**Optimal Kullanım:**
- Küçük-orta ölçekli ağlar (< 10,000 parametre)
- Non-differentiable fitness function'lar
- Gradient tabanlı yöntemlerin başarısız olduğu problemler

#### 7.5.2. GA ile Hyperparameter Optimization

Neural network'ün hyperparameter'lerini GA ile optimize etme:

**Optimize Edilebilecek Hyperparameter'ler:**
- Layer sayısı
- Her layer'daki neuron sayısı
- Learning rate
- Batch size
- Dropout rate
- Activation functions
- Optimizer tipi

**Kromozom Gösterimi:**
```
[num_layers, neurons_layer1, neurons_layer2, ..., lr, batch_size, dropout]
Örnek: [3, 128, 64, 32, 0.001, 64, 0.2]
```

Bu yaklaşım, AutoML ve Neural Architecture Search (NAS) ile ilişkilidir.

### 7.6. Ensemble GA + ML/DL

Genetik algoritmaları farklı makine öğrenmesi ve derin öğrenme modelleriyle birleştirme:

**Yaklaşım 1: GA-Based Feature Selection + ML Model**
```
GA → Optimal feature subset seç → Train ML model (RF, XGBoost) → Evaluate
```

**Yaklaşım 2: GA-Based Trading Strategy + DL Prediction**
```
DL Model → Fiyat tahmini yap → GA → Optimal trade parametreleri → Backtest
```

**Yaklaşım 3: Multi-Objective GA + Ensemble Models**
```
Birden fazla ML/DL modelini eğit
GA ile optimal model kombinasyonunu ve ağırlıklarını bul
Çok amaçlı optimizasyon: [Maximize return, Minimize risk, Minimize drawdown]
```

---

## 8. MAKİNE ÖĞRENMESİ + TEKNİK ANALİZ KOMBİNASYONU

Teknik analiz, geçmiş fiyat ve hacim verilerini kullanarak gelecekteki fiyat hareketlerini tahmin etmeyi amaçlayan bir yöntemdir. Makine öğrenmesi ile birleştirildiğinde, hem domain knowledge hem de data-driven yaklaşımların avantajları elde edilir.

### 8.1. Teknik Analiz Temelleri

#### 8.1.1. Temel Prensipler

**1. Piyasa Her Şeyi İndirir:**
Tüm bilgi (ekonomik, politik, psikolojik) fiyata yansır.

**2. Fiyatlar Trendlerde Hareket Eder:**
Fiyatlar rastgele değil, trend (yükseliş, düşüş, yatay) içinde hareket eder.

**3. Tarih Tekerrür Eder:**
Piyasa davranışları tekrar eder, geçmiş paternler gelecekte de görülebilir.

#### 8.1.2. Teknik Gösterge Kategorileri

**1. Trend Göstergeleri:**
Piyasanın yönünü belirler.

**2. Momentum Göstergeleri (Oscillators):**
Fiyat hareketinin hızını ve gücünü ölçer.

**3. Volatilite Göstergeleri:**
Fiyat dalgalanmasının büyüklüğünü gösterir.

**4. Hacim Göstergeleri:**
İşlem hacmini analiz eder, trend gücünü doğrular.

### 8.2. Popüler Teknik Göstergeler

#### 8.2.1. Moving Averages (Hareketli Ortalamalar)

**Simple Moving Average (SMA):**
```
SMA_n = (P_1 + P_2 + ... + P_n) / n
```

**Exponential Moving Average (EMA):**
```
EMA_t = α × P_t + (1-α) × EMA_{t-1}
```
Burada α = 2/(n+1), smoothing factor'dür.

**Kullanım:**
- **Trend Belirleme:** Fiyat > MA → Uptrend, Fiyat < MA → Downtrend
- **Golden Cross:** Kısa vadeli MA (örn. 50-gün), uzun vadeli MA'yı (örn. 200-gün) yukarı keser → Bullish sinyal
- **Death Cross:** Kısa vadeli MA, uzun vadeli MA'yı aşağı keser → Bearish sinyal

**Kripto Trading'de:**
- 50-day ve 200-day EMA yaygın kullanılır
- Bitcoin için 21-week MA önemli destek/direnç seviyesi

#### 8.2.2. Relative Strength Index (RSI)

RSI, momentum göstergesidir ve fiyatın aşırı alım/satım bölgelerini tespit eder.

**Formül:**
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss (genelde 14 periyot)
```

**Yorumlama:**
- **RSI > 70:** Overbought (aşırı alım), potansiyel satış sinyali
- **RSI < 30:** Oversold (aşırı satım), potansiyel alış sinyali
- **RSI = 50:** Nötr momentum
- **Divergence:**
  - Bullish Divergence: Fiyat düşerken RSI yükselir → Reversal sinyali
  - Bearish Divergence: Fiyat yükselirken RSI düşer → Reversal sinyali

**Kripto Piyasalarında RSI:**
- Bitcoin için 14-period RSI standart
- Altcoin'ler için daha kısa periyotlar (7-10) kullanılabilir
- 2026 araştırmalarında RSI + MACD kombinasyonu %77 win rate elde etmiştir

#### 8.2.3. MACD (Moving Average Convergence Divergence)

MACD, trend ve momentum'u birleştirir.

**Bileşenleri:**

1. **MACD Line:**
   ```
   MACD = EMA_12 - EMA_26
   ```

2. **Signal Line:**
   ```
   Signal = EMA_9(MACD)
   ```

3. **Histogram:**
   ```
   Histogram = MACD - Signal
   ```

**Sinyal Üretimi:**

- **Bullish Crossover:** MACD line, signal line'ı yukarı keser
- **Bearish Crossover:** MACD line, signal line'ı aşağı keser
- **Zero-line Crossover:** 
  - MACD > 0: Bullish momentum
  - MACD < 0: Bearish momentum
- **Divergence:** RSI gibi, fiyat ve MACD arasındaki uyumsuzluk reversal sinyali verir

**Kripto Trading'de MACD:**
- 1-hour ve 4-hour chart'larda etkili
- Histogram büyüklüğü, momentum gücünü gösterir
- MACD + RSI kombinasyonu false signal'leri azaltır

#### 8.2.4. Bollinger Bands

Bollinger Bands, volatiliteyi ölçer ve potansiyel breakout/reversal noktalarını belirler.

**Formül:**
```
Middle Band = SMA_20
Upper Band = SMA_20 + (2 × Std_Dev)
Lower Band = SMA_20 - (2 × Std_Dev)
```

**Yorumlama:**

- **Fiyat Upper Band'e Dokunuyor:** Overbought, potansiyel reversal/konsolidasyon
- **Fiyat Lower Band'e Dokunuyor:** Oversold, potansiyel bounce
- **Bollinger Squeeze:** Bandlar daralıyor → Düşük volatilite, breakout bekleniyor
- **Bollinger Expansion:** Bandlar genişliyor → Yüksek volatilite, güçlü trend

**Kripto Volatilite Analizi:**

Kripto piyasaları yüksek volatilite gösterdiği için Bollinger Bands özellikle etkilidir:
- Squeeze periyotları, büyük fiyat hareketlerinin öncüsüdür
- Strong trend'lerde fiyat, bandların kenarında "ride" edebilir
- Mean-reversion stratejileri için kullanılır

#### 8.2.5. Diğer Önemli Göstergeler

**Stochastic Oscillator:**
Mevcut fiyatı, belirli bir periyottaki high-low aralığına göre karşılaştırır.

**ATR (Average True Range):**
Volatilite ölçer, stop-loss seviyelerini belirlemede kullanılır.

**Ichimoku Cloud:**
Destek/direnç, trend yönü ve momentum bilgisi verir.

**Fibonacci Retracement:**
Potansiyel destek/direnç seviyelerini belirler (23.6%, 38.2%, 50%, 61.8%, 78.6%).

### 8.3. Makine Öğrenmesi + Teknik Analiz Entegrasyonu

#### 8.3.1. Feature Engineering: Teknik Göstergeler as Features

**Yaklaşım:**
Teknik göstergeleri makine öğrenmesi modelinin input feature'ları olarak kullanma.

**Feature Set Örneği:**

```python
features = [
    # Fiyat verileri (normalized)
    'open', 'high', 'low', 'close', 'volume',
    
    # Moving Averages
    'SMA_10', 'SMA_20', 'SMA_50', 'SMA_200',
    'EMA_12', 'EMA_26',
    
    # Momentum Indicators
    'RSI_14', 'RSI_7',
    'MACD', 'MACD_signal', 'MACD_histogram',
    'Stochastic_K', 'Stochastic_D',
    
    # Volatility Indicators
    'BB_upper', 'BB_middle', 'BB_lower',
    'BB_width', 'ATR_14',
    
    # Volume Indicators
    'OBV', 'Volume_MA_20',
    
    # Price Transformations
    'returns', 'log_returns',
    'price_change_pct',
    
    # Lagged Features
    'close_lag1', 'close_lag2', 'volume_lag1'
]
```

**Target Variable:**

```python
# Classification (Direction Prediction)
target = 'price_direction'  # 1: up, 0: down

# Regression (Price Prediction)
target = 'next_day_return'  # Continuous value

# Multi-class (Detailed Signal)
target = 'signal'  # 0: Strong Sell, 1: Sell, 2: Hold, 3: Buy, 4: Strong Buy
```

#### 8.3.2. Model Seçimi

**Popüler ML Modelleri:**

1. **Random Forest:**
   - Feature importance çıkarabilir (hangi gösterge daha önemli?)
   - Non-linear ilişkileri yakalar
   - Overfitting'e dirençli

2. **XGBoost/LightGBM:**
   - Yüksek doğruluk
   - Feature engineering'den sonra en iyi sonuçları verir
   - Hızlı eğitim ve tahmin

3. **Support Vector Machine (SVM):**
   - Non-linear decision boundary
   - Küçük-orta ölçekli veri setlerinde etkili

4. **Neural Networks:**
   - Çok karmaşık pattern'leri öğrenebilir
   - Daha fazla veri gerektirir
   - LSTM/GRU: Zaman serisi için uygun

#### 8.3.3. Hibrit Stratejiler

**Strateji 1: Technical Indicator Confirmation + ML Prediction**

```
1. ML model ile fiyat yönünü tahmin et
2. Teknik göstergelerle doğrula:
   - RSI overbought/oversold?
   - MACD crossover var mı?
   - Bollinger Bands sinyali veriyor mu?
3. Hem ML hem teknik göstergeler align olduysa trade yap
```

Bu yaklaşım false signal'leri azaltır.

**Strateji 2: Multi-Indicator Confirmation Strategy**

2026 araştırmalarında kullanılan strateji:

```
Buy Signal:
- RSI < 30 (oversold)
- Fiyat, lower Bollinger Band'in altında
- MACD pozitif crossover

Sell Signal:
- RSI > 70 (overbought)
- Fiyat, upper Bollinger Band'in üstünde
- MACD negatif crossover
```

Bu multi-indicator confirmation yaklaşımı, signal güvenilirliğini önemli ölçüde artırmaktadır.

**Strateji 3: ML-Based Dynamic Parameter Optimization**

Teknik göstergelerin parametrelerini (örn. RSI periyodu, MACD fast/slow periods) ML ile dinamik olarak optimize etme:

```
1. Mevcut piyasa rejimini belirle (trending, ranging, volatile)
2. Regime'e uygun teknik gösterge parametrelerini seç
3. ML modeli ile bu parametreleri fine-tune et
4. Trading sinyalleri üret
```

#### 8.3.4. TraderNet-CR: DRL + Technical Analysis

2023 yılı araştırmasında, TraderNet-CR sistemi geliştirilmiştir. Bu sistem:

**Bileşenleri:**

1. **Technical Analysis Module:**
   - Candlestick pattern'leri analiz eder
   - RSI, MACD, Bollinger Bands gibi göstergeleri hesaplar

2. **DRL Agent (PPO-based):**
   - Teknik analiz çıktılarını state olarak kullanır
   - Trading aksiyonlarını (buy/sell/hold) öğrenir

3. **Trend Monitoring:**
   - Google Trends data ile market sentiment'i entegre eder

**Performans:**

- Bitcoin, Ethereum, Litecoin üzerinde test edilmiş
- Integrated TraderNet-CR, standalone yöntemleri aşmıştır
- PPO, DDQN'den daha iyi performans göstermiştir (Ethereum hariç)
- Candlestick image'ları ile temporal ve spatial bilgileri yakalamıştır

### 8.4. Teknik Analiz + ML'in Avantaj ve Sınırlamaları

**Avantajları:**

1. **Domain Knowledge + Data-Driven:**
   - Teknik analiz, yıllarca test edilmiş piyasa bilgisi
   - ML, bu bilgiyi veriye dayalı olarak optimize eder

2. **Yorumlanabilirlik:**
   - Teknik göstergeler, yorumlanabilir feature'lardır
   - Trader'lar modelin kararlarını anlayabilir

3. **False Signal Reduction:**
   - Birden fazla göstergenin ML ile kombinasyonu, false signal'leri azaltır

4. **Regime Adaptation:**
   - ML, farklı piyasa koşullarında hangi göstergelerin daha etkili olduğunu öğrenebilir

**Sınırlamaları:**

1. **Lagging Indicators:**
   - Çoğu teknik gösterge, geçmiş verilere dayalıdır (lagging)
   - Hızlı piyasa değişikliklerinde geç kalabilir

2. **Overfitting Risk:**
   - Çok fazla teknik gösterge kullanmak, overfitting'e yol açabilir

3. **Market Regime Changes:**
   - Geçmişte işleyen paternler, gelecekte işlemeyebilir

4. **Self-Fulfilling Prophecy:**
   - Herkes aynı teknik göstergeleri kullanırsa, etkililikleri azalır

---

## 9. PERFORMANS DEĞERLENDİRME VE RİSK YÖNETİMİ

### 9.1. Backtesting

Backtesting, bir trading stratejisinin geçmiş verilerde nasıl performans göstereceğini test etme sürecidir.

**Backtesting Best Practices:**

1. **Out-of-Sample Testing:**
   - Veriyi train/validation/test set'lere ayır
   - Modeli sadece train set'te eğit
   - Hiperparametreleri validation set'te ayarla
   - Final performansı test set'te değerlendir

2. **Walk-Forward Analysis:**
   - Zaman serisi cross-validation
   - Belirli bir periyotta eğit, sonraki periyotta test et
   - Sliding window yaklaşımı

3. **Realistic Assumptions:**
   - Transaction costs (işlem ücretleri)
   - Slippage (fiyat kayması)
   - Spread (alış-satış farkı)
   - Order execution delay

4. **Avoiding Look-Ahead Bias:**
   - Gelecekteki bilgiyi kullanmamak
   - Her zaman adımında sadece o ana kadar olan veri kullanılmalı

### 9.2. Risk Yönetimi Stratejileri

**1. Position Sizing:**

**Fixed Fractional Method:**
```
Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss Price)
```

**Kelly Criterion:**
```
f* = (p × b - q) / b
```
Burada p = kazanma olasılığı, q = kaybetme olasılığı, b = kazanç/kayıp oranı

**2. Stop-Loss ve Take-Profit:**

- **Fixed Percentage:** %2-3 stop-loss, %5-10 take-profit
- **ATR-Based:** Stop-loss = Entry ± (k × ATR), k genelde 2-3
- **Trailing Stop:** Kazanan pozisyonda stop-loss'u yukarı kaydır

**3. Diversification:**

- Birden fazla kripto varlık (5-10 arası)
- Farklı kategorilerden (large cap, mid cap, DeFi, Layer-2)
- Correlation analizi ile düşük korelasyonlu varlıklar seç

**4. Maximum Drawdown Control:**

- Günlük/haftalık maksimum kayıp limiti
- Drawdown threshold'u aşarsa trading'i durdur
- Sermayeyi koru, psikolojik etkileri minimize et

### 9.3. Performans Metrikleri (Detaylı)

**Sharpe Ratio Variants:**

**1. Sharpe Ratio:**
```
Sharpe = (R_p - R_f) / σ_p
```

**2. Information Ratio:**
```
IR = (R_p - R_b) / Tracking Error
```
Burada R_b benchmark getirisidir.

**3. Sortino Ratio:**
```
Sortino = (R_p - R_target) / σ_downside
```
Sadece negatif volatiliteyi dikkate alır.

**Win Rate ve Risk/Reward Metrics:**

**Win Rate:**
```
Win Rate = (Kazanan İşlem Sayısı / Toplam İşlem Sayısı) × 100
```

**Average Win vs Average Loss:**
```
Avg Win = Toplam Kazanç / Kazanan İşlem Sayısı
Avg Loss = Toplam Kayıp / Kaybeden İşlem Sayısı
```

**Profit Factor:**
```
Profit Factor = Toplam Kazanç / Toplam Kayıp
```
Profit Factor > 1 → Profitable strategy

**Expectancy:**
```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```
Pozitif expectancy, uzun vadede karlı strateji anlamına gelir.

---

## 10. SONUÇ VE DEĞERLENDİRME

Kripto spot piyasalarında otonom portföy yönetimi, finansal teknolojinin en hızlı gelişen alanlarından biridir. Bu araştırma yazısında, hibrit yapay zeka yaklaşımlarının teorik temellerini kapsamlı olarak inceledik.

### 10.1. Ana Bulgular

1. **Ensemble Yöntemlerin Üstünlüğü:**
   - Stacking, %81.80 doğruluk oranı ile en iyi performansı sergilemiştir
   - Bagging (Random Forest), volatilite tahmini ve pattern recognition'da etkilidir
   - Boosting (XGBoost, LightGBM), trend reversal tahmininde ARIMA'dan %23.7 daha iyidir

2. **Deep Reinforcement Learning'in Potansiyeli:**
   - PPO, %48 kümülatif getiri ve 1.78 Sharpe oranı ile geleneksel yöntemleri aşmaktadır
   - DQN, 6 kripto varlıkta ortalama %12.3 ROI elde etmiştir
   - A3C, multi-market trading için paralel eğitim avantajı sağlar
   - SAC, continuous action space'lerde portföy ağırlık optimizasyonu için idealdir

3. **Genetik Algoritmaların Adaptasyonu:**
   - CGA-Agent, BTC'de %29, ETH'de %550, BNB'de %169 total return artışı sağlamıştır
   - NEAT, gradient-free optimizasyon ile karmaşık network topology'leri keşfeder
   - Differential Evolution, portföy optimizasyonunda CVaR minimizasyonu için etkilidir

4. **Teknik Analiz + ML Sinerjisi:**
   - Multi-indicator confirmation (RSI + MACD + Bollinger Bands) %77 win rate
   - TraderNet-CR, DRL + teknik analiz kombinasyonu ile üstün performans
   - Dynamic parameter optimization, regime değişikliklerine adaptasyon sağlar

### 10.2. Hibrit Yaklaşımların Değeri

Tek başına hiçbir yöntem, kripto piyasalarının karmaşık ve dinamik yapısını tam olarak modelleyemez. Hibrit yaklaşımlar:

- **Variance ve Bias'ı Birlikte Azaltır:** Ensemble yöntemler
- **Exploration ve Exploitation'ı Dengeler:** DRL algoritmaları
- **Domain Knowledge ve Data-Driven Yaklaşımı Birleştirir:** Teknik analiz + ML
- **Local Optimum'dan Kaçınır:** Genetik algoritmalar

### 10.3. Pratik Uygulamalar İçin Öneriler

**Başlangıç Seviyesi:**
- Random Forest + Teknik Göstergeler
- Basit DQN ile buy/sell/hold sinyalleri
- Tek kripto varlık üzerinde test

**Orta Seviye:**
- Stacking (RF + XGBoost + SVM)
- PPO ile continuous action space
- 3-5 kripto varlık portföyü

**İleri Seviye:**
- Multi-agent DRL sistemi
- CGA-Agent ile adaptive parameter optimization
- 10+ varlık portföyü, multi-objective optimization

### 10.4. Gelecek Araştırma Yönleri

1. **Transformers in Crypto Trading:**
   - Attention mechanism ile uzun vadeli bağımlılıkları yakalama
   - Time series transformers (Temporal Fusion Transformer)

2. **Meta-Learning:**
   - Few-shot learning ile yeni kripto varlıklara hızlı adaptasyon
   - Model-Agnostic Meta-Learning (MAML) ile regime değişikliklerine adaptasyon

3. **Multi-Modal Learning:**
   - Fiyat verileri + sosyal medya sentiment + on-chain metrikleri birleştirme
   - Large Language Models (LLMs) ile haber analizi

4. **Explainable AI:**
   - Black-box modellerin kararlarını açıklama (SHAP, LIME)
   - Regülatör uyumluluk için şeffaflık

5. **Online Learning ve Continual Learning:**
   - Sürekli yeni veriyle modeli güncelleme
   - Catastrophic forgetting'i önleme

---

## KAYNAKÇA

Bu araştırma yazısında kullanılan başlıca kaynaklar:

**Ensemble Learning:**
- Comparative Analysis of Ensemble-Based Models for Predicting Cryptocurrency Price Movements (2025)
- Ensemble Learning for Chart Patterns (2025)
- Cryptocurrency price forecasting – A comparative analysis of ensemble learning and deep learning methods (2024)

**Deep Reinforcement Learning:**
- Deep Reinforcement Learning in Cryptocurrency Trading: A Profitable Approach (2024)
- Combining deep reinforcement learning with technical analysis and trend monitoring (2023)
- Reinforcement Learning in Dynamic Crypto Markets (2025)
- Reinforcement Learning for Dynamic Portfolio Optimization (2024)

**Neuroevolution ve Genetic Algorithms:**
- Agent-Based Genetic Algorithm for Crypto Trading Strategy Optimization (CGA-Agent, 2025)
- Neuroevolution in Deep Neural Networks (2020)
- Cryptocurrency Portfolio Optimization by Neural Networks (2023)
- Optimization and Diversification of Cryptocurrency Portfolios: A Composite Copula-Based Approach (2022)

**Technical Analysis + Machine Learning:**
- How Do MACD, RSI, and Bollinger Bands Predict Crypto Market Trends? (2025)
- Technical Indicators in Crypto Trading: RSI, MACD, Bollinger & More (2025)
- RSI, MACD, Bollinger Bands and Volume-Based Hybrid Trading Strategy (2024)

**AI-Powered Portfolio Management:**
- LLM-Powered Multi-Agent System for Automated Crypto Portfolio Management (2025)
- The Future of Automated Crypto Portfolio Management (2025)
- Crypto Portfolio Managed by AI Is Beating Humans (2025)

---

**NOT:** Bu yazı, kripto spot piyasalarında otonom portföy yönetimi için hibrit yapay zeka yaklaşımlarının teorik temellerini kapsamaktadır. Deneysel çalışmalar ve pratik uygulamalar için, bu kavramların kodlanması, backtesting ve live trading testleri gereklidir.
