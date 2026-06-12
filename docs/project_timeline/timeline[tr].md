## Çalışma Takvimi

| Tarih Aralığı | Faaliyet | Gerçekleştirecekler | Başarı Ölçütü ve Katkısı |
|---|---|---|---|
| 01/03/2026 – 15/03/2026 | **Sistem Mimarisinin Tasarımı** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş, Danışman: Doç. Dr. İlker Köse | **Başarı ölçütü:** Mimari diyagramın tamamlanması, kod deposu ve temel proje şablonunun çalışır olması. **Katkı: %15** |
| 15/03/2026 – 25/03/2026 | **Veri Pipeline ve Veritabanı Modülleri** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş | **Başarı ölçütü:** API'ye ulaşıp veriyi elde eden pipeline modülünün ve PostgreSQL CRUD fonksiyonlarının %100 çalışması. **Katkı: %10** |
| 25/03/2026 – 04/04/2026 | **Teknik İndikatör Modülü** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş | **Başarı ölçütü:** Seçilen indikatörlerin %100 doğrulukla hesaplanabilmesi ve veritabanına kaydedilebilmesi. **Katkı: %10** |
| 04/04/2026 – 20/04/2026 | **Baseline Tahmin Modelleri** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş | **Başarı ölçütü:** MAPE veya RMSE değerlerinin ARIMA/Prophet'e göre belirgin şekilde daha düşük olması ve Buy & Hold stratejisinin getirisinden düşük olmayan bir portföy performansı üretmesi. **Katkı: %10** |
| 20/04/2026 – 04/05/2026 | **Derin Öğrenme Modelleri (LSTM/GRU)** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş, Danışman: Doç. Dr. İlker Köse | **Başarı ölçütü:** LSTM/GRU modellerinin test setinde MAPE değerinin ARIMA/Prophet'e göre daha düşük olması. **Katkı: %10** |
| 04/05/2026 – 14/05/2026 | **Backtesting Çerçevesi** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş, Danışman: Doç. Dr. İlker Köse | **Başarı ölçütü:** En az 1000 sanal işlem simülasyonunun başarıyla tamamlanması; Profit Factor > 1; Max Drawdown < %30. **Katkı: %15** |
| 14/05/2026 – 21/05/2026 | **Paper Trading (Spot Demo Mode) Uygulaması** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş | **Başarı ölçütü:** En az 100 Spot Demo işleminin hatasız gerçekleşmesi. **Katkı: %5** |
| 21/05/2026 – 02/06/2026 | **Kullanıcı Arayüzü (React) + API Entegrasyonu** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş | **Başarı ölçütü:** Kullanıcı parametrelerinin %100 sorunsuz girilmesi, işlem sonuçlarının UI üzerinden izlenebilir olması. **Katkı: %10** |
| 02/06/2026 – 14/06/2026 | **Otonom AI Agent (LLM Tabanlı)** | Ahmet Servet Polat, Kenan Koçoğlu, Mehmet Enes Odabaş, Danışman: Doç. Dr. İlker Köse | **Başarı ölçütü:** AI agent'ın en az 1 hafta boyunca kesintisiz çalışıp, risk kısıtlarını (max drawdown, işlem boyutu) ihlal etmeden otonom olarak emir gönderip yönetebilmesi. **Katkı: %15** |

## Güncel Uygulama Durumu

- Veri pipeline: Binance REST ve public dump tabanlı OHLCV ingestion, coverage takibi, gap repair ve indikatör backfill akışları CLI ve dashboard API üzerinden çalışır durumdadır.
- Tahmin modelleri: ARIMA, Prophet, XGBoost, LightGBM, LSTM ve GRU için eğitim/prediction akışları mevcuttur. Üretim artefact'ları model registry üzerinden aktif/pasif yapılabilir.
- Backtesting: Walk-forward ve production training akışlarında Backtrader tabanlı holdout değerlendirme desteklenmektedir.
- Paper trading: Binance Spot Demo Mode için hesap okuma, manuel market buy/sell, LLM agent kararı, risk kontrolü ve order journaling uygulanmıştır.
- Dashboard: React + FastAPI dashboard; data management, training jobs, prediction runtime, model registry, live agent loop, risk controls, execution orders, Chart.js grafikler ve görsel durum panelleri içermektedir.
- Otonom agent: `run-live-once` ve `run-loop` akışları kapalı mum üzerinden veri tamamlama, indikatör hesaplama, prediction journaling, LLM kararı, risk kontrolü ve dry-run/Spot Demo execution yolunu kullanmaktadır.
