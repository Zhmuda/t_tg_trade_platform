from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import os

from tinkoff.invest import Client
from tinkoff.invest.utils import now

# === НАСТРОЙКИ ===
TOKEN = 't.uXE8f0PWbG6bIrScOI0DxyMiu5CXXjpvbxhW-HtjXpcUVIK6SJEJz27HId-Qnz3p-tP8VZzN-zR1IOC3owAatw'
DATA_DIR = Path(__file__).resolve().parent
PORTFOLIO_XLSX = DATA_DIR / "chatgpt_portfolio_update.xlsx"
TRADE_LOG_XLSX = DATA_DIR / "chatgpt_trade_log.xlsx"

# === ВСПОМОГАТЕЛЬНЫЕ ===
today = datetime.today().strftime("%Y-%m-%d")

def get_price_moex(ticker: str) -> float:
    with Client(TOKEN) as client:
        instruments = client.instruments.shares().instruments
        instrument = next((s for s in instruments if s.ticker == ticker), None)
        print(instrument)
        if not instrument:
            raise ValueError(f"Не найден тикер: {ticker}")
        figi = instrument.figi
        candles = client.market_data.get_candles(
            figi=figi,
            from_=now() - timedelta(days=2),
            to=now(),
            interval=1
        )
        if not candles.candles:
            raise ValueError(f"Нет данных по свечам: {ticker}")
        last = candles.candles[-1].close
        return last.units + last.nano / 1e9

def process_portfolio(portfolio: pd.DataFrame, starting_cash: float) -> tuple[pd.DataFrame, float]:
    results = []
    total_value = 0.0
    total_pnl = 0.0
    cash = starting_cash

    for _, stock in portfolio.iterrows():
        ticker = stock["ticker"]
        shares = int(stock["shares"])
        cost = float(stock["buy_price"])
        stop = float(stock["stop_loss"])

        try:
            price = round(get_price_moex(ticker), 2)
        except Exception as e:
            print(f"Ошибка получения данных для {ticker}: {e}")
            price = None

        if price is None:
            row = {
                "Date": today, "Ticker": ticker, "Shares": shares,
                "Cost Basis": cost, "Stop Loss": stop,
                "Current Price": "", "Total Value": "",
                "PnL": "", "Action": "NO DATA",
                "Cash Balance": "", "Total Equity": "",
            }
        else:
            value = round(price * shares, 2)
            pnl = round((price - cost) * shares, 2)

            if price <= stop:
                action = "SELL - Stop Loss Triggered"
                cash += value
                portfolio = portfolio[portfolio["ticker"] != ticker]
                log_trade(ticker, shares, cost, price, pnl, "STOPLOSS")
            else:
                action = "HOLD"
                total_value += value
                total_pnl += pnl

            row = {
                "Date": today, "Ticker": ticker, "Shares": shares,
                "Cost Basis": cost, "Stop Loss": stop,
                "Current Price": price, "Total Value": value,
                "PnL": pnl, "Action": action,
                "Cash Balance": "", "Total Equity": "",
            }

        results.append(row)

    total_row = {
        "Date": today, "Ticker": "TOTAL", "Shares": "",
        "Cost Basis": "", "Stop Loss": "", "Current Price": "",
        "Total Value": round(total_value, 2), "PnL": round(total_pnl, 2),
        "Action": "", "Cash Balance": round(cash, 2),
        "Total Equity": round(total_value + cash, 2)
    }
    results.append(total_row)

    df = pd.DataFrame(results)
    if PORTFOLIO_XLSX.exists():
        existing = pd.read_excel(PORTFOLIO_XLSX)
        existing = existing[existing["Date"] != today]
        df = pd.concat([existing, df], ignore_index=True)

    df.to_excel(PORTFOLIO_XLSX, index=False)
    return portfolio, cash

def log_trade(ticker: str, shares: int, buy_price: float, sell_price: float, pnl: float, reason: str):
    log = {
        "Date": today, "Ticker": ticker,
        "Shares Sold": shares, "Sell Price": sell_price,
        "Cost Basis": buy_price, "PnL": pnl,
        "Reason": f"AUTO SELL - {reason}",
    }
    if TRADE_LOG_XLSX.exists():
        df = pd.read_excel(TRADE_LOG_XLSX)
        df = pd.concat([df, pd.DataFrame([log])], ignore_index=True)
    else:
        df = pd.DataFrame([log])
    df.to_excel(TRADE_LOG_XLSX, index=False)

def main():
    cash = 15000
    portfolio = pd.read_excel(DATA_DIR / "chatgpt_portfolio_input.xlsx")  # <-- входной файл
    portfolio, cash = process_portfolio(portfolio, cash)
    print("\nОбновление завершено.\n")

if __name__ == "__main__":
    main()
