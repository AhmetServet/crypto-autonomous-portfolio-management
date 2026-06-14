# Bulgular

## Genel Bulgular

Bu çalışma kapsamında kripto para piyasalarında otonom portföy yönetimine yönelik geliştirilen sistemin veri toplama, veri saklama, model eğitimi, tahmin üretimi, karar oluşturma ve testnet/Spot Demo ortamında emir iletimi adımları uygulanmıştır. Sistem yalnızca teorik olarak tasarlanmamış, aynı zamanda çalışan bir yazılım mimarisi olarak implemente edilmiştir. Binance üzerinden BTCUSDT paritesine ait OHLCV piyasa verileri alınmış, elde edilen veriler yerel veritabanına işlenmiş, model eğitim ve tahmin pipeline'ı kurulmuştur. Böylece farklı model ailelerinin aynı veri seti üzerinde karşılaştırılabilmesi sağlanmıştır.

## Veri Seti

Deneylerde BTCUSDT paritesine ait 1 dakikalık piyasa verileri kullanılmıştır. Veri aralığı 26.05.2021 ile 14.06.2026 arasını kapsamaktadır. Kullanılan veri seti açık, yüksek, düşük, kapanış fiyatı ve hacim gibi OHLCV alanlarını içermektedir. Tabular ve derin öğrenme tabanlı modellerde bu ham piyasa verilerinden türetilen teknik gösterge özellikleri de kullanılmıştır. Bu yaklaşım sayesinde modellerin aynı veri kaynağı üzerinden eğitilmesi ve sonuçların daha tutarlı şekilde karşılaştırılması hedeflenmiştir.

## Sistem Mimarisi Ve Gerçekleme

Geliştirilen sistemde veri toplama, veri saklama, model eğitimi ve tahmin üretimi uçtan uca uygulanmıştır. Proje reposunda bu yapı modüler monolit yaklaşımıyla organize edilmiştir. API, servis, domain, model ve altyapı katmanları ayrı tutulmuş; Binance bağlantısı, veritabanı erişimi, model eğitimi, tahmin üretimi, risk kontrolü ve dashboard bileşenleri farklı sorumluluklara ayrılmıştır. Bu mimari, sistemin yalnızca deneysel bir notebook çalışması olarak kalmamasını, tekrar çalıştırılabilir bir yazılım altyapısına dönüşmesini sağlamıştır.

Sistem, farklı model türlerinin aynı çatı altında denenmesine izin verecek şekilde modüler tasarlanmıştır. ARIMA ve Prophet gibi istatistiksel modeller, XGBoost ve LightGBM gibi tabular makine öğrenmesi modelleri, LSTM ve GRU gibi derin öğrenme modelleri aynı tahmin altyapısına dahil edilmiştir. Model çıktıları karşılaştırılabilir metriklerle raporlanmış; dashboard, API ve komut satırı bileşenleri üzerinden sistem çıktılarının izlenebilir hale getirilmesi amaçlanmıştır. Bu kapsamda FastAPI tabanlı backend, React/Vite tabanlı dashboard, model artifact yönetimi, prediction journal, agent decision journal ve risk kontrol bileşenleri geliştirilmiştir.

## Web Arayüzü

Geliştirilen web arayüzü, sistemin komut satırı üzerinden yürütülen işlemlerini daha izlenebilir ve yönetilebilir hale getirmek amacıyla tasarlanmıştır. Arayüzde sembol ve zaman aralığı seçimi yapılabilmekte; güncel fiyat, son agent kararı, tahmin başarısı, aktif model sayısı ve API sağlık durumu gibi temel göstergeler üst bölümde özetlenmektedir. Dashboard yapısı, yalnızca görsel raporlama amacı taşımamakta; veri yönetimi, model eğitimi, tahmin üretimi, risk kontrolü, canlı döngü çalıştırma, Spot Demo emirleri ve işlem günlüklerinin incelenmesi gibi operasyonel işlevleri de aynı arayüz altında toplamaktadır. Bu nedenle web arayüzü, geliştirilen sistemin uçtan uca çalıştığını gösteren önemli çıktılardan biri olarak değerlendirilmiştir.

Arayüz altı ana sekmeden oluşmaktadır:

**Overview sekmesi:** Sistemin genel durumunu özetler. Fiyat grafikleri, OHLC piyasa görünümü, alım/satım/bekleme işaretleri, pozisyon ve risk bilgileri, güncel piyasa durumu, teknik göstergeler ve sistem sağlık bilgileri bu ekranda izlenebilir.  
Görsel placeholder: foto1  
Önerilen görsel açıklaması: Overview ekranı; güncel fiyat, piyasa grafikleri, pozisyon/risk özeti, teknik göstergeler ve sistem sağlık durumunu tek ekranda göstermektedir.

**Trade sekmesi:** Binance Spot Demo portföy bilgisini ve manuel emir testlerini içerir. Kullanıcı bu sekmede kullanılabilir USDT bakiyesini, base asset miktarını, kilitli bakiyeyi ve son emir kayıtlarını görebilir. Ayrıca onay kutusu gerektiren manuel market alım ve satım formlarıyla Spot Demo ortamında kontrollü emir gönderimi yapılabilir.  
Görsel placeholder: foto2  
Önerilen görsel açıklaması: Trade ekranı; Spot Demo portföy durumunu, manuel market alım/satım formlarını ve gerçekleşen emir kayıtlarını göstermektedir.

**Agent sekmesi:** Otonom karar döngüsünün çalıştırıldığı ve risk parametrelerinin yönetildiği bölümdür. Bu sekmede dry-run veya spot-demo modu seçilebilir, market data modu belirlenebilir, stale model ve veri boşluğu kurtarma seçenekleri ayarlanabilir. Ayrıca max trade size, max position size, günlük zarar limiti, emir sayısı limiti, cooldown ve exposure gibi risk kontrolleri düzenlenebilir. Agent tek seferlik çalıştırılabilir veya sürekli live loop olarak başlatılıp durdurulabilir.  
Görsel placeholder: foto3  
Önerilen görsel açıklaması: Agent ekranı; çalışma modu, risk limitleri, canlı döngü kontrolü ve tek seferlik agent çalıştırma araçlarını içermektedir.

**Data sekmesi:** Veritabanı ve piyasa verisi yönetimi için kullanılır. Bu bölümde coin sembolleri için veritabanı başlatılabilir, Binance OHLCV verisi çekilebilir, veri kalıcılığı seçilebilir, geçmiş veri ingest işlemleri yapılabilir, veri kapsama durumu kontrol edilebilir, eksik mum verileri onarılabilir ve teknik gösterge backfill işlemleri çalıştırılabilir.  
Görsel placeholder: foto4  
Önerilen görsel açıklaması: Data ekranı; veritabanı başlatma, OHLCV veri çekme, geçmiş veri ingest etme, coverage kontrolü, gap repair ve indicator backfill işlemlerini göstermektedir.

**Models sekmesi:** Model eğitimi, model artifact yönetimi ve tahmin üretimi için tasarlanmıştır. Aktif model kartları, eğitim tipi seçimi, preset tabanlı training job oluşturma, eğitim işleri ve logları, prediction araçları, prediction settlement işlemleri ve model registry bu sekmede yer almaktadır. Model registry üzerinden modellerin aktif/pasif duruma alınması, arşivlenmesi ve metriklerinin incelenmesi mümkündür.  
Görsel placeholder: foto5  
Önerilen görsel açıklaması: Models ekranı; aktif modelleri, eğitim panelini, tahmin araçlarını ve model registry üzerinden artifact yönetimini göstermektedir.

**Journal sekmesi:** Sistemin denetlenebilirlik katmanını temsil eder. Bu sekmede son agent kararları, model tahminleri ve emir kayıtları tablo halinde görüntülenir. Karar kayıtlarında action, confidence, risk durumu, execution durumu, LLM modeli, latency, risk ihlalleri ve karar gerekçesi gibi alanlar incelenebilir. Ayrıca ilgili karar için kullanılan LLM prompt'u ve ham yanıt detayları açılır panel üzerinden görüntülenebilir.  
Görsel placeholder: foto6  
Önerilen görsel açıklaması: Journal ekranı; agent kararlarını, model tahminlerini, emir kayıtlarını ve LLM prompt detaylarını denetlenebilir şekilde göstermektedir.

## Karar Üretimi Ve Risk Kontrol

Sistemin tahmin çıktıları yalnızca metrik üretmek için kullanılmamış, aynı zamanda işlem kararına dönüştürülebilecek şekilde tasarlanmıştır. Model tahminleri alım, satım veya bekleme sinyaline çevrilmiş; ardından bu sinyaller risk kontrol katmanından geçirilmiştir. Bu yapı sayesinde sistem, sadece fiyat tahmini yapan bir yapı olmaktan çıkarılarak karar destek ve otonom işlem altyapısına dönüştürülmüştür. Dry-run ve testnet/Spot Demo mantığıyla gerçek piyasa koşullarına yakın senaryolarda, gerçek sermaye riske edilmeden karar üretimi ve emir iletimi test edilmiştir. Bu yapı, ileride risk yönetimi, portföy optimizasyonu ve gerçek emir entegrasyonu için temel oluşturabilecek niteliktedir.

## Model Değerlendirme Yöntemi

Modellerin değerlendirilmesinde eğitim ve test dönemlerinin ayrılması esas alınmıştır. Zaman serisi problemlerinde gelecekteki verinin eğitim sürecine sızması yanıltıcı sonuçlar üretebileceği için, modellerin geçmiş veriden öğrenerek daha sonraki dönemlerdeki fiyat hareketlerini tahmin etmesi hedeflenmiştir. Ayrıca walk-forward deney yaklaşımı ve holdout değerlendirmeleriyle modellerin farklı zaman kesitlerinde nasıl davrandığı incelenmiştir. Bu yöntem, kripto para piyasalarında değişen piyasa koşullarına karşı model performansını daha gerçekçi biçimde değerlendirmek açısından önemlidir.

## Model Performans Bulguları

Çalışmada tabular, istatistiksel ve derin öğrenme tabanlı modeller test edilmiştir. Modellerin performansları accuracy, RMSE ve MAE metrikleri üzerinden değerlendirilmiştir. Accuracy metriği modelin fiyat yönünü doğru tahmin etme başarısını; RMSE ve MAE metrikleri ise tahmin edilen değer ile gerçekleşen değer arasındaki hata düzeyini göstermektedir. Bu nedenle accuracy yön tahmini açısından, RMSE ve MAE ise sayısal tahmin kalitesi açısından değerlendirilmiştir. Elde edilen sonuçlar Tablo 1'de gösterilmiştir.

| Model | Model Türü | Eğitim Tarihi | Accuracy | RMSE | MAE |
|---|---|---:|---:|---:|---:|
| XGBoost | Tabular | 06.06, 01:32 | 52.35% | 200.068 | 0.20 |
| LSTM | Deep Learning | 06.06, 01:32 | 53.92% | 196.087 | 0.20 |
| LightGBM | Tabular | 06.06, 01:32 | 52.64% | 199.845 | 0.20 |
| ARIMA | Statistical | 06.06, 01:32 | 75.00% | 142.046 | 0.21 |
| GRU | Deep Learning | 26.05, 03:00 | 50.68% | 211.916 | 0.16 |
| Prophet | Statistical | 26.05, 00:49 | 72.73% | 200.373 | 0.26 |

Tablo 1 incelendiğinde, istatistiksel modellerin özellikle yön tahmini açısından daha yüksek accuracy değerleri ürettiği görülmektedir. ARIMA modeli %75.00 accuracy değeriyle en yüksek başarıyı göstermiştir. Prophet modeli de %72.73 accuracy ile diğer modellere kıyasla yüksek bir sonuç üretmiştir. Buna karşılık XGBoost, LightGBM, LSTM ve GRU modellerinin accuracy değerleri birbirine yakın gerçekleşmiş ve yaklaşık %50-54 aralığında kalmıştır. Bu durum, finansal zaman serilerinin yüksek gürültü içermesi, kısa vadeli fiyat hareketlerinin tahmin edilmesindeki zorluklar ve model hiperparametrelerinin sınırlı kaynaklarla optimize edilmesiyle ilişkilendirilebilir.

RMSE değerleri açısından ARIMA modelinin diğer modellere göre daha düşük hata ürettiği görülmektedir. Ancak MAE değerleri incelendiğinde GRU modelinin daha düşük bir değer verdiği görülmektedir. Bu fark, tek bir metriğe bakarak model seçimi yapmanın yeterli olmadığını göstermektedir. Özellikle finansal zaman serilerinde yön doğruluğu, sayısal tahmin hatası ve işlem stratejisine etkisi birlikte değerlendirilmelidir. Yüksek accuracy değerinin tek başına daha yüksek portföy getirisi anlamına gelmemesi, bu çalışmanın önemli bulgularından biridir.

## Testnet Ve İşlem Gerçekleme Bulguları

Sistemin teknik gerçekleme tarafında, model çıktılarının yalnızca teorik olarak değerlendirilmesiyle sınırlı kalınmamış, aynı zamanda testnet/Spot Demo ortamında işlem üretme kabiliyeti de denenmiştir. Bu kapsamda agent decision journal tablosundaki son 100 karar kaydı incelenmiştir. İncelenen kayıtlar 14.06.2026 tarihinde 16:25-18:05 saatleri arasında, BTCUSDT paritesinde ve 1 dakikalık zaman aralığında üretilmiştir. Bu 100 kararın tamamı spot_demo modunda çalıştırılmıştır.

Son 100 kararın 92'si hold, 8'i buy olarak üretilmiştir. Sell kararı oluşmamıştır. Buy kararlarının 5 tanesi risk kontrolünden geçerek Spot Demo ortamında filled durumuyla tamamlanmış, 3 tanesi ise maksimum pozisyon büyüklüğü sınırını aşacağı için risk kontrol katmanı tarafından reddedilmiştir. Gerçekleşen 5 alım emrinin her biri yaklaşık 50 USDT büyüklüğündedir ve toplamda yaklaşık 248.22 USDT karşılığında BTC alımı yapılmıştır. İşlemler sonucunda testnet portföyündeki BTC miktarı yaklaşık 0.00387452 BTC seviyesine ulaşmıştır.

| Karar / Durum | Adet | Açıklama |
|---|---:|---|
| Hold | 92 | İşlem yapılmadan mevcut durum korundu. |
| Buy | 8 | Alım kararı üretildi. |
| Sell | 0 | Satış kararı oluşmadı. |
| Filled Buy | 5 | Risk kontrolünden geçerek gerçekleşen alım emirleri. |
| Rejected Buy | 3 | Maksimum pozisyon büyüklüğü sınırı nedeniyle reddedilen alım kararları. |

| Operasyonel Metrik | Değer |
|---|---:|
| İncelenen karar sayısı | 100 |
| Çalışma modu | spot_demo |
| Sembol | BTCUSDT |
| Zaman aralığı | 14.06.2026 16:25-18:05 |
| Ortalama confidence | 0.445 |
| Minimum confidence | 0.20 |
| Maksimum confidence | 0.78 |
| Ortalama LLM latency | 8.42 saniye |
| Minimum LLM latency | 4.01 saniye |
| Maksimum LLM latency | 36.56 saniye |
| Filled emir sayısı | 5 |
| Risk nedeniyle reddedilen emir sayısı | 3 |
| Portföy değer değişimi | -0.27 USDT |

Son 100 kaydın başlangıç ve bitiş portföy değerleri, ilgili karar kayıtlarında saklanan portföy snapshot'ları ve güncel kapanış fiyatları kullanılarak hesaplanmıştır. İlk kayıtta yaklaşık portföy değeri 4999.63 USDT, son kayıtta ise yaklaşık 4999.37 USDT olarak bulunmuştur. Buna göre incelenen aralıkta portföy değeri yaklaşık -0.27 USDT, oransal olarak ise yaklaşık -%0.005 değişmiştir. Bu sonuç realized kar/zarar olarak değil, satış işlemi gerçekleşmediği için anlık fiyat üzerinden hesaplanan portföy değer değişimi olarak değerlendirilmelidir.

Kararların büyük çoğunluğunun hold olması, sistemin belirsiz veya çelişkili model sinyallerinde işlem yapmaktan kaçındığını göstermektedir. Bu durum kısa test aralığında işlem sayısını azaltmış olsa da, risk kontrollü otonom işlem mimarisi açısından olumlu bir davranış olarak değerlendirilebilir. Sistem, model veya LLM çıktısını doğrudan emir olarak uygulamamış; kararları önce risk kontrol katmanından geçirmiştir.

Risk kontrol katmanının yalnızca teorik olarak bulunmadığı, gerçek karar akışında aktif olarak çalıştığı görülmüştür. Maksimum pozisyon büyüklüğü sınırını aşacak 3 alım kararı sistem tarafından emir olarak gönderilmeden reddedilmiştir. Bu bulgu, otonom karar mekanizmasının üzerinde bağımsız bir güvenlik katmanı bulunduğunu ve işlem kararlarının risk limitleriyle sınırlandırıldığını göstermektedir.

Karar kayıtlarında her işlem için gerekçe saklanmıştır. Bu gerekçelerde model tahminlerinin çelişkili olması, RSI, MACD ve Bollinger Band gibi teknik göstergeler, fiyatın teknik seviyelere yakınlığı, mevcut pozisyon büyüklüğü ve risk limitleri gibi faktörlerin dikkate alındığı görülmüştür. Böylece sistemin kararları yalnızca sonuç olarak değil, karar gerekçesiyle birlikte denetlenebilir hale getirilmiştir.

Son 100 karar kaydında LLM karar üretim süresi ortalama 8.42 saniye olarak ölçülmüştür. Bu değer 1 dakikalık karar döngüsü içinde kabul edilebilir görünmekle birlikte, maksimum 36.56 saniyeye ulaşan gecikmeler daha uzun süreli canlı çalışmada izlenmesi gereken bir operasyonel risk oluşturmaktadır. Son 100 kararda ortalama confidence değeri 0.445 olarak hesaplanmıştır. Bu değer, sistemin kısa test aralığında yüksek güvenli agresif işlem kararlarından ziyade daha temkinli kararlar ürettiğini göstermektedir.

Görsel placeholder: testnet_grafik  
Önerilen görsel açıklaması: Testnet/Spot Demo çalışmasında fiyat hareketi, teknik göstergeler ve agent karar noktaları birlikte gösterilmektedir. Yeşil üçgenler alım kararlarını, kırmızı üçgenler satış kararlarını, beyaz noktalar ise hold kararlarını temsil etmektedir.

Grafik incelendiğinde alım kararlarının fiyatın düşüş sonrası toparlanma denemeleri sırasında yoğunlaştığı, ancak sistemin büyük bölümde hold kararı vererek işlem sıklığını sınırladığı görülmektedir. Satış sinyalinin oluşmaması nedeniyle test aralığında strateji daha çok pozisyon oluşturma ve bekleme davranışı sergilemiştir.

Testnet işlemleri, sistemin yalnızca tahmin üreten bir yapı olmadığını göstermiştir. Emir formatlama, sembol bazlı işlem yürütme, bakiye ve pozisyon kontrolü, risk sınırlarının uygulanması, emir sonucunun kaydedilmesi ve karar geçmişinin izlenmesi gibi operasyonel adımlar da sistem içinde test edilmiştir. Projede yer alan agent decision journal ve prediction journal yapıları sayesinde hem model tahminlerinin hem de bu tahminlerden türetilen kararların daha sonra incelenebilmesi hedeflenmiştir. Bu durum, sistemin denetlenebilirlik ve izlenebilirlik açısından temel gereksinimleri karşılama yönünde ilerlediğini göstermektedir.

Son 100 karar yaklaşık 100 dakikalık kısa bir zaman aralığını kapsadığı için bu sonuçlar stratejinin uzun vadeli başarısını kanıtlamak için yeterli değildir. Ancak sistemin uçtan uca çalışma, emir üretme, risk kontrolü ve kayıt tutma kabiliyetini göstermesi açısından anlamlıdır.

## Operasyonel Sınırlılıklar

Bununla birlikte, sistemin uzun süreli canlı çalışma koşullarında bazı sınırlılıkları olduğu görülmüştür. Proje kapsamında sistemin bir hafta boyunca kesintisiz çalıştırılması hedeflenmiş olsa da, özellikle derin öğrenme modellerinin çalıştırılması ve güncel tahminlerin düzenli olarak üretilmesi için yüksek GPU kaynağına ihtiyaç duyulması nedeniyle bu hedef tam olarak gerçekleştirilememiştir. LSTM ve GRU gibi modeller, her tahmin döngüsünde uygun veri penceresinin hazırlanmasını ve model artifact'lerinin yüklenmesini gerektirdiğinden, kaynak tüketimi tabular ve istatistiksel modellere göre daha yüksek gerçekleşmiştir.

Bu nedenle deneyler BTCUSDT paritesi ile sınırlandırılmıştır. Çoklu coin desteği mimari olarak mümkün olmakla birlikte, her coin için ayrı veri geçmişi, ayrı model eğitimi, model artifact saklama, periyodik tahmin üretimi, karar mekanizması ve risk kontrolü çalıştırılması gerekmektedir. Bu gereksinimler sistem yükünü doğrusal olarak artırmaktadır. Mevcut donanım, zaman ve GPU kaynakları dikkate alındığında ETH, BNB veya diğer coinlerin aynı kapsamda eklenmesi bu çalışmanın dışında bırakılmıştır.

## Strateji Performansı Ve Buy & Hold Karşılaştırması

Strateji performansı açısından değerlendirildiğinde, test edilen modellerin buy & hold stratejisini aşamadığı görülmüştür. Karşılaştırma amacıyla, BTC'nin 2021 yılında alınarak elde tutulduğu varsayımsal senaryoda yaklaşık %55.2 oranında getiri sağlanabileceği hesaplanmıştır. Model tabanlı stratejiler ise bu referans performansın üzerine çıkamamıştır. Buy & hold stratejisinin daha başarılı görünmesinin temel nedeni, incelenen dönemde BTC fiyatının uzun vadede yükseliş eğilimi göstermesidir. Model tabanlı stratejiler ise kısa vadeli alım-satım kararları verdiği için yanlış sinyaller, piyasadan çıkış zamanlaması, işlem sıklığı, komisyon ve olası slippage etkileri nedeniyle uzun vadeli tutma stratejisini aşamamıştır.

Bu bulgu, yüksek tahmin başarısının doğrudan finansal başarıya dönüşmediğini göstermektedir. Özellikle kısa vadeli kripto para işlemlerinde modelin yönü doğru tahmin etmesi yeterli değildir; tahminin büyüklüğü, işlem maliyeti, pozisyon büyüklüğü, risk limiti, yanlış sinyalden sonra sistemin nasıl davrandığı ve piyasada kalma süresi de toplam performansı belirlemektedir. Bu nedenle model performansı yalnızca accuracy, RMSE veya MAE ile değil; strateji getirisi, maksimum düşüş, işlem başına ortalama sonuç, risk başına getiri ve portföy oynaklığı gibi finansal metriklerle de değerlendirilmelidir.

## Genişletilebilirlik Bulguları

Çalışmanın bir diğer bulgusu, sistemin yazılım mimarisi açısından genişletilebilir olmasına rağmen operasyonel maliyetlerin model sayısı ve coin sayısıyla birlikte hızlı biçimde artmasıdır. Repo içinde model registry, artifact yönetimi, prediction runtime, dashboard training job yapısı ve canlı döngü komutları geliştirilmiştir. Ancak çoklu coin ve çoklu model senaryosunda her modelin dakikalık olarak çalıştırılması, her coin için veri güncelliğinin korunması ve risk limitlerinin ayrı ayrı izlenmesi daha güçlü donanım ve daha olgun bir iş zamanlayıcı yapısı gerektirmektedir.

## Genel Değerlendirme

Genel olarak bulgular, geliştirilen sistemin teknik olarak çalışır durumda olduğunu ve testnet/Spot Demo üzerinde emir üretebildiğini göstermektedir. Veri alımı, veritabanına kayıt, özellik üretimi, model eğitimi, tahmin üretimi, tahmin günlüğü, karar üretimi, risk kontrolü, emir iletimi ve dashboard üzerinden izleme gibi temel bileşenler uygulanmıştır. Ancak model performanslarının buy & hold stratejisini aşamaması, sistemin yatırım kararı üretme açısından henüz olgunlaşmadığını ortaya koymaktadır.

Bu nedenle mevcut çalışma, karlılığı kanıtlanmış bir alım-satım sistemi olmaktan çok, kripto para piyasaları için veri işleme, model karşılaştırma, tahmin günlüğü, risk kontrollü karar üretimi ve otonom işlem altyapısı geliştirmeye yönelik bir prototip olarak değerlendirilmelidir. Gelecek çalışmalarda çoklu coin desteği, daha düşük kaynak tüketen inference yapısı, daha uzun süreli canlı test, işlem maliyeti ve slippage simülasyonu, stop-loss ve take-profit kuralları, portföy ağırlıklandırma, ensemble model denemeleri ve risk-ayarlı performans metrikleri sisteme eklenerek model tabanlı stratejilerin buy & hold karşısındaki başarısı daha kapsamlı biçimde incelenebilir.
