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


def create_investment_summary(df_results):
    """상위 5개 코인에 대한 종합 투자 분석을 생성합니다."""
    st.subheader("📈 투자 전략 분석")

    # 시장 상황 요약
    market_status = "강세" if df_results.head(5)["SEPA점수"].mean() > 0.7 else "약세"
    st.markdown(f"### 현재 시장 상황: {market_status}")

    # 투자 전략 제시
    st.markdown(
        """
   ### 투자 포트폴리오 추천
   - 안전: BTC/ETH (60-70%)
   - 공격: 알트코인 (30-40%)
   """
    )

    # 상위 5개 코인 투자 요약
    st.markdown("### 상위 코인 투자 분석")
    for _, coin in df_results.head(5).iterrows():
        with st.expander(f"{coin['심볼']} - SEPA 점수: {coin['SEPA점수']:.2f}"):
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown("**기술적 분석**")
                st.markdown(
                    f"""
               - 추세: {'상승' if coin['차트데이터'].iloc[-1]['MA200'] > coin['차트데이터'].iloc[-20]['MA200'] else '하락'}
               - 변동성: {coin['특징']['일일변동성']}
               - 거래량 추세: {coin['특징']['거래량추세']}
               - 추세 강도: {coin['특징']['추세강도']}
               """
                )

            with col2:
                st.markdown("**투자 의견**")
                st.markdown(coin["특징"]["투자의견"])


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


def generate_investment_opinion(
    sepa_score, volatility, trend_strength, volume_trend, price_to_ma200
):
    """
    기술적 지표를 기반으로 투자 의견을 동적으로 생성합니다.

    Parameters:
    - sepa_score: SEPA 전략 점수
    - volatility: 일일 변동성
    - trend_strength: 추세 강도
    - volume_trend: 거래량 추세
    - price_to_ma200: 현재가/200일 이평선 비율
    """
    opinion = ""

    # SEPA 점수에 따른 기본 투자 의견
    if sepa_score >= 0.9:
        opinion = "매우 추천\n"
    elif sepa_score >= 0.8:
        opinion = "매수 유망\n"
    elif sepa_score >= 0.7:
        opinion = "매수 고려\n"
    else:
        opinion = "관망 추천\n"

    # 세부 분석 추가
    reasons = []

    # 추세 강도 분석
    if trend_strength > 20:
        reasons.append("강한 상승 추세")
    elif trend_strength > 10:
        reasons.append("적정 상승 추세")
    elif trend_strength < 0:
        reasons.append("하락 추세 주의")

    # 변동성 분석
    if float(volatility.strip("%")) > 15:
        reasons.append("높은 변동성 주의")
    elif float(volatility.strip("%")) < 5:
        reasons.append("안정적 변동성")

    # 거래량 추세 분석
    if volume_trend == "증가":
        reasons.append("거래량 증가 중")
    else:
        reasons.append("거래량 감소 중")

    # MA200 대비 가격 분석
    price_ratio = float(price_to_ma200.strip("%"))
    if price_ratio > 20:
        reasons.append("과매수 구간")
    elif price_ratio < -10:
        reasons.append("과매도 구간")

    # 투자 전략 제시
    if sepa_score >= 0.8:
        if float(volatility.strip("%")) > 15:
            opinion += "- 분할 매수 전략 추천\n"
        else:
            opinion += "- 추세 추종 전략 추천\n"

    # 세부 이유 추가
    opinion += "\n".join(f"- {reason}" for reason in reasons)

    return opinion


def get_coin_characteristics(symbol, df):
    """코인의 특성을 분석합니다."""
    latest = df.iloc[-1]

    volatility = df["close"].pct_change().std() * 100
    volume_trend = (
        "증가" if df["volume"].tail(7).mean() > df["volume"].tail(30).mean() else "감소"
    )
    trend_strength = (latest["close"] - latest["MA200"]) / latest["MA200"] * 100
    price_to_ma200 = f"{trend_strength:.2f}%"

    characteristics = {
        "일일변동성": f"{volatility:.2f}%",
        "거래량추세": volume_trend,
        "추세강도": f"{trend_strength:.2f}%",
    }

    # 투자 의견 생성
    characteristics["투자의견"] = generate_investment_opinion(
        sepa_score=df.get("SEPA점수", 0.7),  # SEPA 점수가 없는 경우 기본값 0.7
        volatility=characteristics["일일변동성"],
        trend_strength=trend_strength,
        volume_trend=volume_trend,
        price_to_ma200=price_to_ma200,
    )

    return characteristics


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

        # 투자 전략 분석
        create_investment_summary(df_results)

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

        # 상위 5개 코인 탭 분석
        st.subheader("🏆 상위 5개 코인 차트 분석")
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

                    for key, value in coin["특징"].items():
                        if key != "투자의견":
                            st.metric(key, value)

                    with st.expander("SEPA 조건"):
                        for k, v in coin["criteria_details"].items():
                            st.markdown(f"{'✅' if v else '❌'} {k}")

        # 개별 코인 상세 분석
        st.markdown("---")
        st.subheader("📊 개별 코인 상세 분석")
        selected_coin = st.selectbox("분석할 코인 선택", df_results["심볼"].tolist())

        if selected_coin:
            coin_data = df_results[df_results["심볼"] == selected_coin].iloc[0]

            col1, col2 = st.columns([3, 1])
            with col1:
                st.plotly_chart(create_chart(selected_coin, coin_data["차트데이터"]))

            with col2:
                st.subheader("코인 정보")
                st.metric("현재가", f"₩{coin_data['현재가']:,.0f}")
                st.metric("SEPA 점수", f"{coin_data['SEPA점수']:.2f}")
                st.metric("거래량", f"₩{coin_data['거래량']:,.0f}")

                st.markdown("### 투자 의견")
                st.markdown(coin_data["특징"]["투자의견"])

                with st.expander("기술적 지표 상세"):
                    for key, value in coin_data["특징"].items():
                        if key != "투자의견":
                            st.text(f"{key}: {value}")

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
