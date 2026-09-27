import time
import logging
import requests
import pandas as pd
import yfinance as yf

# ==========================================
# AYARLAR — KENDİ BİLGİLERİNİ BURAYA YAZ
# ==========================================
BOT_TOKEN = "8778638900:AAHnmLfsW5VQ2t7InAZ0ApUZ1oeHWi0b2_4"
CHAT_ID = "-1004483021246"

SYMBOL = "GC=F"       # Gold Futures
TIMEFRAME = "1h"      # 1 Saatlik
CHECK_INTERVAL = 900  # 15 dakika

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class TelegramBot:
    def __init__(self, token, chat_id):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send_message(self, text):
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("ok", False):
                logging.error("Telegram API hatası: %s", result)

            return result.get("ok", False)

        except Exception as e:
            logging.error("Telegram gönderim hatası: %s", e)
            return False


def normalize_yfinance_data(data):
    """yfinance MultiIndex döndürürse kolonları tek seviyeye indirir."""
    if isinstance(data.columns, pd.MultiIndex):
        try:
            data.columns = data.columns.get_level_values(0)
        except Exception:
            data.columns = [
                col[0] if isinstance(col, tuple) else col
                for col in data.columns
            ]

    return data


def analyze_market():
    """Gold verisini çeker ve basit 3 mum FVG setup'ı arar."""
    try:
        data = yf.download(
            tickers=SYMBOL,
            period="5d",
            interval=TIMEFRAME,
            progress=False,
            auto_adjust=False
        )

        if data is None or data.empty or len(data) < 5:
            logging.warning("Yeterli piyasa verisi alınamadı.")
            return None

        data = normalize_yfinance_data(data)

        required = ["Open", "High", "Low", "Close"]
        if not all(col in data.columns for col in required):
            logging.error("Beklenen OHLC kolonları bulunamadı: %s", data.columns)
            return None

        df = data[required].dropna().tail(5).copy()

        if len(df) < 3:
            return None

        # Son 3 mum
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]

        current_price = float(c3["Close"])

        # ------------------------------------------
        # BULLISH FVG
        # 3. mumun Low'u 1. mumun High'ından yüksekse
        # ------------------------------------------
        if float(c3["Low"]) > float(c1["High"]):
            fvg_low = float(c1["High"])
            fvg_high = float(c3["Low"])

            sl = fvg_low * 0.998
            risk = current_price - sl

            if risk <= 0:
                return None

            tp1 = current_price + risk * 1.5
            tp2 = current_price + risk * 2.5

            return {
                "signal": "BUY",
                "price": current_price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "reason": (
                    f"Bullish FVG "
                    f"[{fvg_low:.2f} - {fvg_high:.2f}]"
                )
            }

        # ------------------------------------------
        # BEARISH FVG
        # 3. mumun High'ı 1. mumun Low'undan düşükse
        # ------------------------------------------
        if float(c3["High"]) < float(c1["Low"]):
            fvg_high = float(c1["Low"])
            fvg_low = float(c3["High"])

            sl = fvg_high * 1.002
            risk = sl - current_price

            if risk <= 0:
                return None

            tp1 = current_price - risk * 1.5
            tp2 = current_price - risk * 2.5

            return {
                "signal": "SELL",
                "price": current_price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "reason": (
                    f"Bearish FVG "
                    f"[{fvg_low:.2f} - {fvg_high:.2f}]"
                )
            }

        return None

    except Exception as e:
        logging.exception("Piyasa analiz hatası: %s", e)
        return None


def main():
    # Token ve Chat ID kontrolü
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        raise ValueError("BOT_TOKEN kısmına Telegram BotFather tokenını yaz.")

    if CHAT_ID == "@YOUR_CHANNEL_OR_CHAT_ID":
        raise ValueError("CHAT_ID kısmına Telegram kanal/grup ID'sini yaz.")

    bot = TelegramBot(BOT_TOKEN, CHAT_ID)

    bot.send_message(
        "🤖 *SMC Trading Bot Başarıyla Başlatıldı!*\n"
        "24/7 Piyasa taraması aktif..."
    )

    last_signal = None

    while True:
        try:
            logging.info("Piyasa kontrol ediliyor...")

            setup = analyze_market()

            if setup and setup["signal"] != last_signal:
                emoji = "🟢" if setup["signal"] == "BUY" else "🔴"

                message = (
                    f"{emoji} *YENİ SİNYAL: {setup['signal']}*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 *Enstrüman:* `XAUUSD (GOLD)`\n"
                    f"⏱ *Zaman Dilimi:* `{TIMEFRAME}`\n"
                    f"🎯 *Giriş Fiyatı:* `{setup['price']:.2f}`\n\n"
                    f"🛑 *Stop Loss:* `{setup['sl']:.2f}`\n"
                    f"🎯 *Take Profit 1:* `{setup['tp1']:.2f}`\n"
                    f"🚀 *Take Profit 2:* `{setup['tp2']:.2f}`\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 *Setup:* _{setup['reason']}_\n"
                    f"⚠️ *Risk Yönetimi:* "
                    f"_Sermayenin %1'inden fazlasını riske atmayın._"
                )

                if bot.send_message(message):
                    last_signal = setup["signal"]

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logging.info("Bot durduruldu.")
            break

        except Exception as e:
            logging.exception("Ana döngü hatası: %s", e)
            time.sleep(60)


if __name__ == "__main__":
    main()
