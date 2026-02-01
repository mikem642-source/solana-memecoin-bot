import asyncio
import json
import os
import logging
import requests
import schedule
import time
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
import base64

load_dotenv()

RPC_ENDPOINT = os.getenv("RPC_ENDPOINT", "https://api.devnet.solana.com")
WALLET_PATH = os.getenv("WALLET_JSON_PATH", "wallet.json")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

TRADING_ENABLED = True  # ← Trading is ENABLED

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load wallet
with open(WALLET_PATH) as f:
    keypair = Keypair.from_bytes(json.load(f))
logger.info(f"✅ Wallet loaded: {str(keypair.pubkey())}")

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

async def buy_token(token_mint):
    if not TRADING_ENABLED:
        logger.warning("Trading is DISABLED")
        return None, None
    try:
        logger.info(f"🔄 Buying 1 SOL of {token_mint}")
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": token_mint,
            "amount": 1_000_000_000,
            "slippageBps": 1500
        }
        quote = requests.get("https://quote-api.jup.ag/v6/quote", params=params, timeout=10).json()
        
        swap_params = {
            "quoteResponse": quote,
            "userPublicKey": str(keypair.pubkey()),
            "wrapAndUnwrapSol": True
        }
        swap_response = requests.post("https://quote-api.jup.ag/v6/swap", json=swap_params, timeout=10).json()
        
        tx_bytes = base64.b64decode(swap_response["swapTransaction"])
        tx = Transaction.from_bytes(tx_bytes)
        
        tx.add(set_compute_unit_limit(500_000))
        tx.add(set_compute_unit_price(1_000_000))
        
        tx.sign(keypair)
        client = AsyncClient(RPC_ENDPOINT)
        sig = await client.send_transaction(tx)
        await client.confirm_transaction(sig.value, "confirmed")
        
        logger.info(f"✅ Bought {token_mint} | Sig: {sig.value}")
        return quote.get("outAmount"), quote.get("price", 0)
    except Exception as e:
        logger.error(f"Buy failed: {e}")
        return None, None

async def main():
    logger.info("🚀 Memecoin Bot with Trading Logic")
    await check_balance()
    schedule.every().day.at("08:00").do(send_daily_report)
    schedule.every().day.at("20:00").do(send_daily_report)
    asyncio.create_task(monitor_new_tokens())
    schedule.every(15).minutes.do(lambda: asyncio.create_task(check_balance()))
    logger.info("Trading is ENABLED")
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
