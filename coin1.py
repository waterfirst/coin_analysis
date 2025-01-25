import streamlit as st
import pandas as pd
import pyupbit
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import datetime


# Function to download data for a single cryptocurrency
def download_crypto_data(ticker):
    try:
        data = yf.download(ticker, period="1y", interval="1d")
        if data.empty:
            print(f"No data found for {ticker}.")
            return None
        data["Ticker"] = ticker
        return data
    except Exception as e:
        print(f"Error downloading data for {ticker}: {e}")
        return None


# Function to analyze a cryptocurrency's data
def analyze_crypto(data):
    if data is None or data.empty:
        return None

    data["Daily Return"] = data["Adj Close"].pct_change()
    data["SMA_20"] = data["Adj Close"].rolling(window=20).mean()
    data["SMA_50"] = data["Adj Close"].rolling(window=50).mean()
    data["Signal"] = np.where(data["SMA_20"] > data["SMA_50"], "Buy", "Sell")

    return data


# Function to plot analysis results
def plot_crypto_analysis(data, ticker):
    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data["Adj Close"], label="Adjusted Close Price", alpha=0.7)
    plt.plot(data.index, data["SMA_20"], label="20-Day SMA", alpha=0.7)
    plt.plot(data.index, data["SMA_50"], label="50-Day SMA", alpha=0.7)

    buy_signals = data[data["Signal"] == "Buy"]
    sell_signals = data[data["Signal"] == "Sell"]

    plt.scatter(
        buy_signals.index,
        buy_signals["Adj Close"],
        label="Buy Signal",
        marker="^",
        color="green",
    )
    plt.scatter(
        sell_signals.index,
        sell_signals["Adj Close"],
        label="Sell Signal",
        marker="v",
        color="red",
    )

    plt.title(f"{ticker} Analysis")
    plt.xlabel("Date")
    plt.ylabel("Price (USD)")
    plt.legend()
    plt.grid()
    plt.show()


# List of cryptocurrencies to analyze (add more tickers as needed)
crypto_tickers = ["BTC-USD", "ETH-USD", "ADA-USD"]

# Download data concurrently
with ThreadPoolExecutor() as executor:
    crypto_data_list = list(executor.map(download_crypto_data, crypto_tickers))

# Analyze and plot each cryptocurrency
df_combined = pd.DataFrame()
for i, data in enumerate(crypto_data_list):
    if data is not None:
        analyzed_data = analyze_crypto(data)
        df_combined = pd.concat([df_combined, analyzed_data])
        plot_crypto_analysis(analyzed_data, crypto_tickers[i])


# Streamlit page setup
st.set_page_config(page_title="Crypto Analysis", page_icon="💰", layout="wide")


def get_krw_tickers():
    try:
        return pyupbit.get_tickers(fiat="KRW")
    except Exception as e:
        st.error(f"Error fetching tickers: {e}")
        return []


def fetch_coin_data(symbol):
    try:
        df = pyupbit.get_ohlcv(symbol, interval="day", count=252)
        if df is not None and not df.empty:
            df["MA200"] = df["close"].rolling(window=200).mean()
        return df
    except Exception as e:
        st.error(f"Error fetching data for {symbol}: {e}")
        return None


def calculate_signals(df):
    try:
        if len(df) >= 200:
            latest = df.iloc[-1]
            prev_month = df.iloc[-30]

            signals = {
                "Above MA200": latest["close"] > latest["MA200"],
                "MA200 Trending Up": latest["MA200"] > prev_month["MA200"],
            }
            return signals
        return {}
    except Exception as e:
        st.error(f"Error calculating signals: {e}")
        return {}


def plot_chart(symbol, df):
    try:
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="Price",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["MA200"], line=dict(color="red", width=2), name="MA200"
            )
        )
        fig.update_layout(title=f"{symbol} Price Chart", template="plotly_white")
        return fig
    except Exception as e:
        st.error(f"Error creating chart for {symbol}: {e}")
        return go.Figure()


def main():
    st.title("💰 Cryptocurrency Analysis Dashboard")

    st.sidebar.header("Settings")
    analyze_btn = st.sidebar.button("Start Analysis")

    if analyze_btn:
        symbols = get_krw_tickers()
        if not symbols:
            st.error("No tickers found.")
            return

        all_data = []
        progress = st.progress(0)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(fetch_coin_data, symbol): symbol for symbol in symbols
            }
            for i, future in enumerate(futures):
                symbol = futures[future]
                data = future.result()
                if data is not None:
                    signals = calculate_signals(data)
                    all_data.append(
                        {"Symbol": symbol, "Signals": signals, "Data": data}
                    )
                progress.progress((i + 1) / len(symbols))

        if all_data:
            st.success("Analysis complete.")
            for coin in all_data:
                with st.expander(f"{coin['Symbol']}"):
                    st.plotly_chart(plot_chart(coin["Symbol"], coin["Data"]))


if __name__ == "__main__":
    main()
