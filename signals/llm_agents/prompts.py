"""
Katman 3c — Prompt Şablonları
================================
Her fonksiyon (system_prompt, user_prompt) çifti döndürür. Metinler
Türkçe tutuldu (kullanıcıyla aynı dilde) ama LLM'in JSON anahtarlarını
İngilizce döndürmesi istendi (nodes.py'nin ayrıştırma kodu bunu bekliyor).
"""

from __future__ import annotations


def technical_analyst_prompt(symbol: str, stats: dict) -> tuple[str, str]:
    system = (
        "Sen deneyimli bir teknik analistsin. Sana verilen sayısal piyasa "
        "istatistiklerine dayanarak KISA (en fazla 4-5 cümle), somut bir "
        "teknik durum raporu yaz. Spekülasyon yapma, sadece verilen sayılara "
        "dayalı gözlem sun. Türkçe yaz."
    )
    user = (
        f"Sembol: {symbol}\n\n"
        f"Son teknik göstergeler:\n"
        f"- Son kapanış: {stats.get('last_close')}\n"
        f"- 1 barlık getiri: %{stats.get('return_1', 0) * 100:.3f}\n"
        f"- 12 barlık getiri: %{stats.get('return_12', 0) * 100:.3f}\n"
        f"- 24 barlık volatilite: {stats.get('volatility_24')}\n"
        f"- RSI(14): {stats.get('rsi_14')}\n"
        f"- 20 barlık SMA'ya oranı: {stats.get('sma_ratio_20')}\n\n"
        f"Bu verilere dayanarak kısa bir teknik durum raporu yaz."
    )
    return system, user


def news_analyst_prompt(symbol: str, news_text: str | None) -> tuple[str, str]:
    system = (
        "Sen bir finansal haber/duygu analistisin. Sana bir haber metni "
        "verilirse bunun piyasa duyarlılığına etkisini KISA özetle. Haber "
        "metni verilmemişse, veri olmadığını açıkça belirt — ASLA haber "
        "uydurmaya çalışma. Türkçe yaz."
    )
    if news_text:
        user = f"Sembol: {symbol}\n\nHaber metni:\n{news_text}\n\nBu haberin piyasa duyarlılığına etkisini özetle."
    else:
        user = (
            f"Sembol: {symbol}\n\nBu sembol için herhangi bir haber metni sağlanmadı. "
            f"Bunu açıkça belirt ve 'haber verisi yok' şeklinde kısa bir not döndür."
        )
    return system, user


def researcher_prompt(
    role: str, symbol: str, technical_report: str, news_report: str
) -> tuple[str, str]:
    """role: 'bull' (boğa/iyimser) veya 'bear' (ayı/kötümser)."""
    stance = "iyimser (boğa)" if role == "bull" else "kötümser (ayı)"
    system = (
        f"Sen bir yatırım araştırmacısısın ve rolün SİSTEMATİK OLARAK {stance} "
        f"tarafı savunmak. Amacın tek taraflı bir görüş dayatmak değil, "
        f"o yönün en güçlü, en mantıklı gerekçesini ortaya koymak — böylece "
        f"trader her iki tarafı da görüp karar verebilsin. 3-4 cümlelik, "
        f"somut gerekçelere dayanan bir argüman yaz. Türkçe yaz."
    )
    user = (
        f"Sembol: {symbol}\n\n"
        f"Teknik rapor: {technical_report}\n\n"
        f"Haber raporu: {news_report}\n\n"
        f"Bu bilgilere dayanarak {stance} tarafın en güçlü argümanını sun."
    )
    return system, user


def trader_prompt(
    symbol: str, bull_argument: str, bear_argument: str, history_summary: str
) -> tuple[str, str]:
    system = (
        "Sen bir trader'sın. Sana boğa ve ayı araştırmacılarının argümanları "
        "ile bu sembolde geçmişte alınan kararların sonuçları veriliyor. "
        "Görevin: bu bilgileri tartıp NİHAİ bir karar vermek.\n\n"
        "YANITINI SADECE aşağıdaki JSON formatında ver, başka hiçbir metin ekleme:\n"
        '{"side": "long" | "short" | "flat", "confidence": 0.0-1.0, "rationale": "kısa gerekçe"}\n\n'
        "Notlar:\n"
        "- 'flat' = net bir yön göremiyorsan veya belirsizlik yüksekse (bu "
        "  GEÇERLİ ve genellikle en güvenli bir cevaptır).\n"
        "- confidence, kararına ne kadar güvendiğini 0-1 arası gösterir.\n"
        "- Geçmişte bu sembolde art arda kayıp varsa bunu dikkate al, daha "
        "  temkinli ol."
    )
    user = (
        f"Sembol: {symbol}\n\n"
        f"Boğa argümanı: {bull_argument}\n\n"
        f"Ayı argümanı: {bear_argument}\n\n"
        f"Bu sembolde geçmiş performans özeti: {history_summary}\n\n"
        f"Nihai kararını JSON formatında ver."
    )
    return system, user
