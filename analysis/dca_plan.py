"""
DCA (Dollar-Cost Averaging / kademeli alım) plan önerisi.

Tek seferde büyük bir pozisyon açmak yerine, toplam bütçeyi eşit
parçalara bölüp fiyat düştükçe kademeli olarak alım yapmayı önerir.
Amaç: giriş zamanlamasındaki belirsizliği azaltmak — "en dip nerede"
sorusuna cevap aramak yerine, ortalama maliyeti zamana yayarak
düşürmek.

ÖNEMLİ: Bu sistem GERÇEK EMİR GÖNDERMEZ, sadece bir plan önerir. Fiyat
öngörülen seviyelere GELMEYEBİLİR (yani bazı dilimler hiç alınmayabilir)
— bu normaldir, DCA'nın doğasında var. Fiyat hiç gerilemeden yükselirse
sadece ilk dilim alınmış olur, kalan bütçe nakit kalır.
"""
import pandas as pd


def suggest_dca_plan(
    entry_price: float,
    total_position_value: float,
    num_tranches: int = 4,
    drawdown_step_pct: float = 5.0,
) -> list[dict]:
    """
    entry_price: şu anki fiyat (ilk dilim burada alınır)
    total_position_value: toplam ayrılan bütçe ($)
    num_tranches: kaç parçaya bölünecek
    drawdown_step_pct: her sonraki dilim, bir öncekinden yüzde kaç daha
        düşük fiyatta tetiklenecek

    Dönüş: [{"dilim": 1, "tetik_fiyati": ..., "fiyat_dususu_pct": ...,
             "tutar": ..., "adet": ..., "kumulatif_tutar": ...}, ...]
    """
    if entry_price <= 0 or total_position_value <= 0 or num_tranches < 1:
        return []

    tranche_value = total_position_value / num_tranches
    plan = []
    cumulative = 0.0

    for i in range(num_tranches):
        drop_pct = i * drawdown_step_pct
        trigger_price = entry_price * (1 - drop_pct / 100)
        adet = tranche_value / trigger_price if trigger_price > 0 else 0
        cumulative += tranche_value
        plan.append({
            "dilim": i + 1,
            "tetik_fiyati": round(trigger_price, 4),
            "fiyat_dususu_pct": round(drop_pct, 2),
            "tutar": round(tranche_value, 2),
            "adet": round(adet, 4),
            "kumulatif_tutar": round(cumulative, 2),
        })

    return plan


def dca_plan_to_dataframe(symbol: str, plan: list[dict]) -> pd.DataFrame:
    if not plan:
        return pd.DataFrame()
    df = pd.DataFrame(plan)
    df.insert(0, "symbol", symbol)
    return df
