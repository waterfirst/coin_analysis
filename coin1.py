import streamlit as st
import pandas as pd
import pyupbit
import plotly.express as px
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import datetime
import time

st.set_page_config(page_title="Crypto SEPA Strategy", page_icon="🪙", layout="wide")

if "analyzed_data" not in st.session_state:
    st.session_state.analyzed_data = None
    st.session_state.analysis_complete = False


def get_krw_tickers():
    try:
        return pyupbit.get_tickers(fiat="KRW")
    except Exception as e:
        st.error(f"코인 목록 가져오기 실패: {e}")
        return []


def calculate_technical_indicators(df):
    try:
        for window in [5, 50, 150, 200]:
            df[f"MA{window}"] = df["close"].rolling(window=window).mean()
        return df
    except Exception as e:
        st.error(f"지표 계산 오류: {e}")
        return None


def check_sepa_conditions(df):
    if df is None or len(df) < 200:
        return False, {}, 0

    latest = df.iloc[-1]
    month_ago = df.iloc[-30]
    year_low = df["low"].tail(252).min()

    criteria = {
        "현재가가 200일선 위": latest["close"] > latest["MA200"],
        "150일선이 200일선 위": latest["MA150"] > latest["MA200"],
        "50일선이 150/200일선 위": latest["MA50"] > latest["MA150"]
        and latest["MA50"] > latest["MA200"],
        "현재가가 5일선 위": latest["close"] > latest["MA5"],
        "200일선 상승 추세": latest["MA200"] > month_ago["MA200"],
        "52주 최저가 대비 30% 이상": (latest["close"] / year_low - 1) > 0.3,
    }

    weights = {
        k: (
            0.2
            if k
            in ["현재가가 200일선 위", "200일선 상승 추세", "52주 최저가 대비 30% 이상"]
            else (
                0.15
                if k == "150일선이 200일선 위" or k == "50일선이 150/200일선 위"
                else 0.1
            )
        )
        for k in criteria.keys()
    }

    score = sum(weights[k] for k, v in criteria.items() if v)
    return True, criteria, score


def analyze_coin(symbol):
    try:
        df = pyupbit.get_ohlcv(symbol, interval="day", count=252)
        if df is None or df.empty:
            return None

        df = calculate_technical_indicators(df)
        if df is None:
            return None

        meets_criteria, criteria, score = check_sepa_conditions(df)
        if not meets_criteria:
            return None

        volatility = df["close"].pct_change().std() * 100
        volume_trend = (
            "증가"
            if df["volume"].tail(7).mean() > df["volume"].tail(30).mean()
            else "감소"
        )
        trend_strength = (
            (df.iloc[-1]["close"] - df.iloc[-1]["MA200"]) / df.iloc[-1]["MA200"] * 100
        )

        return {
            "심볼": symbol,
            "현재가": df.iloc[-1]["close"],
            "거래량": df.iloc[-1]["volume"],
            "SEPA점수": score,
            "criteria_details": criteria,
            "차트데이터": df,
            "특징": {
                "일일변동성": f"{volatility:.2f}%",
                "거래량추세": volume_trend,
                "추세강도": f"{trend_strength:.2f}%",
                "거래량변화율": f"{(df['volume'].tail(7).mean() / df['volume'].tail(30).mean() - 1) * 100:.1f}%",
            },
        }
    except Exception as e:
        st.error(f"{symbol} 분석 오류: {e}")
        return None


def create_chart(symbol, df):
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

    colors = {"MA5": "purple", "MA50": "blue", "MA150": "green", "MA200": "red"}
    for ma, color in colors.items():
        fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma, line=dict(color=color)))

    fig.update_layout(
        title=f"{symbol} Price Chart", height=600, template="plotly_white"
    )
    return fig


def create_investment_analysis(df_results):
    """상위 5개 코인에 대한 투자 분석을 생성합니다."""
    st.subheader("📊 상위 5개 코인 투자 분석")

    top_5 = df_results.head(5)

    for _, coin in top_5.iterrows():
        with st.expander(f"{coin['심볼']} 상세 분석"):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.plotly_chart(
                    create_chart(coin["심볼"], coin["차트데이터"]),
                    use_container_width=True,
                )

            with col2:
                st.metric("현재가", f"₩{coin['현재가']:,.0f}")
                st.metric("SEPA 점수", f"{coin['SEPA점수']:.2f}")

                # 기술적 분석
                ma_trend = (
                    "상승"
                    if coin["차트데이터"].iloc[-1]["MA200"]
                    > coin["차트데이터"].iloc[-20]["MA200"]
                    else "하락"
                )
                vol_trend = "증가" if coin["특징"]["거래량추세"] == "증가" else "감소"

                analysis = {
                    "추세": ma_trend,
                    "변동성": coin["특징"]["일일변동성"],
                    "거래량추세": vol_trend,
                    "강도": coin["특징"]["추세강도"],
                }

                st.subheader("기술적 분석")
                for key, value in analysis.items():
                    st.text(f"{key}: {value}")

                # 투자 의견
                investment_opinions = {
                    "KRW-BTC": "매수 추천 (분할매수)\n- 200일선 위 강세\n- 상승추세 지속\n- 고점 주의",
                    "KRW-ETH": "매수 유망\n- BTC 대비 저평가\n- 200일선 상향돌파\n- 상승 모멘텀",
                    "KRW-MTL": "관망\n- 높은 변동성\n- 하락추세\n- 거래량 감소",
                    "KRW-BORA": "조정 후 매수\n- 200일선 지지\n- 조정 진행중",
                    "KRW-JST": "지지선 확인 후 매수\n- 급등후 안정화\n- 200일선 상승전환",
                }

                st.subheader("투자 의견")
                st.markdown(investment_opinions.get(coin["심볼"], "분석 필요"))


def analyze_all_coins():
    symbols = get_krw_tickers()
    if not symbols:
        return None

    sepa_coins = []
    progress_bar = st.progress(0)

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_coin = {
            executor.submit(analyze_coin, symbol): symbol for symbol in symbols
        }

        completed = 0
        for future in future_to_coin:
            result = future.result()
            if result is not None:
                result["특징"] = get_coin_characteristics(
                    result["심볼"], result["차트데이터"]
                )
                sepa_coins.append(result)
            completed += 1
            progress_bar.progress(completed / len(symbols))

    if sepa_coins:
        df_results = pd.DataFrame(sepa_coins)
        return df_results.sort_values("SEPA점수", ascending=False)

    return None


def get_coin_characteristics(symbol, df):
    """코인의 특성을 분석합니다."""
    latest = df.iloc[-1]

    volatility = df["close"].pct_change().std() * 100
    volume_trend = (
        "증가" if df["volume"].tail(7).mean() > df["volume"].tail(30).mean() else "감소"
    )
    trend_strength = (latest["close"] - latest["MA200"]) / latest["MA200"] * 100
    volume_to_mcap = latest["volume"] / (latest["close"] * df["volume"].mean())

    return {
        "일일변동성": f"{volatility:.2f}%",
        "거래량추세": volume_trend,
        "추세강도": f"{trend_strength:.2f}%",
        "거래량/시가총액": f"{volume_to_mcap:.4f}",
        "투자의견": get_investment_opinion(
            symbol, volatility, trend_strength, volume_trend
        ),
    }


def get_investment_opinion(symbol, volatility, trend_strength, volume_trend):
    """투자 의견을 생성합니다."""
    opinions = {
        "KRW-BTC": "매수 추천 (분할매수)\n- 200일선 위 강세\n- 상승추세 지속",
        "KRW-ETH": "매수 유망\n- BTC 대비 저평가\n- 상승 모멘텀",
        "KRW-MTL": "관망\n- 높은 변동성\n- 하락추세",
        "KRW-BORA": "조정 후 매수\n- 200일선 지지\n- 조정 진행중",
        "KRW-JST": "지지선 확인 후 매수\n- 급등후 안정화\n- 200일선 전환",
    }
    return opinions.get(symbol, "분석 필요")


def main():
    st.title("Crypto SEPA Strategy Dashboard 🪙")

    col_time, col_btn = st.columns([4, 1])
    with col_time:
        st.markdown(
            f"현재 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    with col_btn:
        analyze_button = st.button(
            "분석 시작", disabled=st.session_state.analysis_complete
        )

    if analyze_button:
        start_time = time.time()
        with st.spinner("코인 분석 중..."):
            st.session_state.analyzed_data = analyze_all_coins()
            st.session_state.analysis_complete = True

        st.info(f"분석 완료! ({time.time() - start_time:.1f}초)")
        st.balloons()

    if (
        st.session_state.analysis_complete
        and st.session_state.analyzed_data is not None
    ):
        df_results = st.session_state.analyzed_data

        # 상위 5개 코인 탭
        st.subheader("🏆 상위 5개 코인 분석")
        tabs = st.tabs(
            [
                f"#{i+1} {coin['심볼']}"
                for i, (_, coin) in enumerate(df_results.head(5).iterrows())
            ]
        )

        for i, (tab, (_, coin)) in enumerate(zip(tabs, df_results.head(5).iterrows())):
            with tab:
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.plotly_chart(
                        create_chart(coin["심볼"], coin["차트데이터"]),
                        use_container_width=True,
                    )

                with col2:
                    st.metric("현재가", f"₩{coin['현재가']:,.0f}")
                    st.metric("SEPA 점수", f"{coin['SEPA점수']:.2f}")

                    st.subheader("기술적 분석")
                    for key, value in coin["특징"].items():
                        if key != "투자의견":
                            st.metric(key, value)

                    st.subheader("투자 의견")
                    st.markdown(coin["특징"]["투자의견"])

                    with st.expander("SEPA 조건"):
                        for k, v in coin["criteria_details"].items():
                            st.markdown(f"{'✅' if v else '❌'} {k}")

        # SEPA 점수 차트
        st.plotly_chart(
            px.bar(
                df_results.head(10),
                x="심볼",
                y="SEPA점수",
                title="상위 10개 코인 SEPA 점수",
                color="SEPA점수",
            )
        )

        # 전체 코인 리스트
        with st.expander("전체 분석 코인 목록"):
            st.dataframe(
                df_results[["심볼", "현재가", "SEPA점수", "거래량"]].style.format(
                    {"현재가": "₩{:,.0f}", "SEPA점수": "{:.2f}", "거래량": "₩{:,.0f}"}
                )
            )

    col_reset, _ = st.columns([1, 4])
    with col_reset:
        if st.button("분석 초기화", type="primary"):
            st.session_state.analysis_complete = False
            st.session_state.analyzed_data = None
            st.rerun()


if __name__ == "__main__":
    main()
