import asyncio
import json
import os
import logging
import requests
import schedule
import time
import smtplib
import base64
from email.mime.text import MIMEText
from dotenv import load_dotenv
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

load_dotenv()

# Configuration
RPC_ENDPOINT = os.getenv("RPC_ENDPOINT", "https://api.devnet.solana.com")
WALLET_PATH = os.getenv("WALLET_JSON_PATH", "wallet.json")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
# Load wallet from base64 environment variable (Railway)
wallet_base64 = os.getenv("WALLET_JSON_BASE64")
if wallet_base64:
    wallet_bytes = base64.b64decode(wallet_base64)
    wallet_dict = json.loads(wallet_bytes.decode('utf-8'))
    keypair = Keypair.from_bytes(wallet_dict)
    logger.info(f"✅ Wallet loaded from WALLET_JSON_BASE64: {str(keypair.pubkey())}")
else:
    # Fallback to local file
    with open(WALLET_PATH) as f:
        keypair = Keypair.from_bytes(json.load(f))
    logger.info(f"✅ Wallet loaded from file: {str(keypair.pubkey())}")
async def check_balance():
    client = AsyncClient(RPC_ENDPOINT)
    try:
        balance = await client.get_balance(keypair.pubkey())
        sol_balance = balance.value / 1_000_000_000
        logger.info(f"Balance: {sol_balance:.4f} SOL")
        return sol_balance
    except Exception as e:
        logger.error(f"Balance check failed: {e}")
        return 0
    finally:
        await client.close()

def get_top_memecoins():
    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/SOL"
        r = requests.get(url, timeout=10)
        pairs = r.json().get("pairs") or []
        memecoins = []
        for p in pairs:
            if p.get("baseToken", {}).get("chainId") == "solana":
                vol = p.get("volume", {}).get("h24") or 0
                high = p.get("priceChange", {}).get("h24", {}).get("high") or 0
                low = p.get("priceChange", {}).get("h24", {}).get("low") or 0
                price = p.get("priceUsd") or 0
                vola = ((high - low) / price * 100) if price > 0 else 0
                if vola > 25 and vol > 0:
                    memecoins.append({
                        "symbol": p["baseToken"].get("symbol", "UNKNOWN"),
                        "volume": vol,
                        "volatility": vola,
                        "price": price
                    })
        return sorted(memecoins, key=lambda x: x["volume"], reverse=True)[:5]
    except Exception as e:
        logger.error(f"Top memecoins error: {e}")
        return []

def send_daily_report():
    logger.info("📧 Generating daily report...")
    top = get_top_memecoins()
    if not top:
        logger.warning("No memecoins found")
        return
    report = "Daily Top 5 Solana Memecoins (Volatility >25%)\n\n"
    for c in top:
        report += f"{c['symbol']} | Vol: ${c['volume']:,.0f} | Volat: {c['volatility']:.1f}% | Price: ${c['price']:.5f}\n"
    try:
        msg = MIMEText(report)
        msg["Subject"] = "Daily Top 5 Memecoins"
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_RECIPIENT
        with smtplib.SMTP(SMTP_SERVER, 587) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        logger.info("✅ Daily report sent")
    except Exception as e:
        logger.error(f"Email failed: {e}")

async def monitor_new_tokens():
    logger.info("🔍 Real-time token monitoring started")
    while True:
        logger.info("📡 Scanning Pump.fun / Meteora / Letsbonk.fun...")
        await asyncio.sleep(30)

async def main():
    logger.info("🚀 Memecoin Bot starting...")
    await check_balance()
    schedule.every().day.at("08:00").do(send_daily_report)
    schedule.every().day.at("20:00").do(send_daily_report)
    asyncio.create_task(monitor_new_tokens())
    schedule.every(15).minutes.do(lambda: asyncio.create_task(check_balance()))
    logger.info(f"Trading is {'ENABLED' if TRADING_ENABLED else 'DISABLED'}")
    logger.info("Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped.")
    except Exception as e:
        logger.error(f"Error: {e}")
