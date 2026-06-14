# Sonuç

Bu proje kapsamında kripto para piyasalarında otonom portföy yönetimi için çalışır bir prototip geliştirilmiştir. Sistem; veri toplama, model eğitimi, tahmin üretimi, karar mekanizması, risk kontrolü ve web arayüzü bileşenlerini bir araya getirmiştir.

Çalışmanın çıkış noktası, kripto spot piyasalarının yüksek volatiliteye sahip yapısında yatırımcıların maruz kaldığı bilgi yükü ve duygusal karar alma problemlerine daha sistematik bir çözüm üretmektir. Bu doğrultuda geliştirilen yapı, tek model-tek piyasa yaklaşımıyla sınırlı kalmamış; farklı model ailelerini, risk kurallarını ve LLM tabanlı agent karar mekanizmasını aynı sistem içinde birleştirmiştir.

Çalışma sonucunda farklı model ailelerinin karşılaştırılabildiği ve model çıktılarının testnet/Spot Demo ortamında kontrollü işlem kararlarına dönüştürülebildiği görülmüştür. Agent yapısının API üzerinden veri işleme, araç çağırma mantığına uygun şekilde sistem bileşenlerini kullanma ve karar gerekçelerini kayıt altına alma kabiliyeti teknik olarak doğrulanmıştır. Ancak makine öğrenmesi modellerinin accuracy değerlerinin düşük kalması, mevcut modelleme yaklaşımının kısa vadeli yön tahmini için henüz yeterli olmadığını göstermektedir.

Bununla birlikte, mevcut sistem yatırım amaçlı kullanılabilecek olgunlukta değildir. Model tabanlı stratejilerin buy & hold stratejisini aşamaması, çoklu coin desteğinin uygulanamaması ve uzun süreli kesintisiz çalışmanın gerçekleştirilememesi önemli sınırlılıklardır.

Bu nedenle çalışma, karlılığı kanıtlanmış bir alım-satım sistemi olarak değil, ileride geliştirilecek daha kapsamlı bir otonom portföy yönetim altyapısı için temel oluşturan bir prototip olarak değerlendirilmelidir. Gelecekte haber akışı ve sosyal medya duyarlılığı gibi metin tabanlı sinyallerin NLP modülleriyle sisteme eklenmesi, Transformer tabanlı modellerin denenmesi ve mimarinin farklı piyasa/işlem ortamlarına genişletilmesi çalışmanın doğal devamı olarak görülmektedir.
