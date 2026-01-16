import streamlit as st
import requests
import pandas as pd
import numpy as np
import math
import pydeck as pdk
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# 設定網頁標題與圖示
st.set_page_config(page_title="台南永康火燒雲預報", page_icon="🌅", layout="centered")

# CSS 優化
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 5rem; }
       h1 { font-size: 1.5rem!important; }
       div[data-testid="stMetricValue"] { font-size: 1.2rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 1. 取得資料函式 ---
def get_data(lat, lon):
    try:
        # Open-Meteo API
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,relative_humidity_2m,sun_azimuth",
            "daily": "sunset",
            "timezone": "Asia/Taipei",
            "forecast_days": 1
        }
        weather_res = requests.get(weather_url, params=weather_params).json()
    except Exception:
        return None, None

    # 民生公共物聯網 API (PM2.5)
    pm25_value = 25 # 預設值
    try:
        iot_url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_EPAIoT/v1.1/Things"
        iot_params = {
            "$filter": "properties/stationName eq '臺南'",
            "$expand": "Datastreams($filter=name eq 'PM2.5';$expand=Observations($top=1;$orderby=phenomenonTime desc))"
        }
        iot_res = requests.get(iot_url, params=iot_params, timeout=5).json()
        
        if 'value' in iot_res and len(iot_res['value']) > 0:
            datastreams = iot_res['value'].get('Datastreams',)
            if datastreams:
                observations = datastreams.get('Observations',)
                if observations:
                    pm25_value = observations['result']
    except Exception:
        pass 

    return weather_res, pm25_value

# --- 2. 計算機率函式 ---
def calculate_burn_probability(weather_data, pm25, target_hour):
    try:
        idx = target_hour
        hourly = weather_data['hourly']
        
        low = hourly['cloud_cover_low'][idx]
        mid = hourly['cloud_cover_mid'][idx]
        high = hourly['cloud_cover_high'][idx]
        humidity = hourly['relative_humidity_2m'][idx]
        vis = hourly['visibility'][idx]
        
        score = 0
        # 評分邏輯
        mid_high_total = mid + high
        if 30 <= mid_high_total <= 80: score += 50
        elif 10 <= mid_high_total < 30: score += 30
        else: score += 10
            
        if low < 30: score += 20
        elif low > 60: score -= 30
            
        if 15 <= pm25 <= 40: score += 20
        elif pm25 > 60: score -= 10
        else: score += 10
            
        if humidity > 85: score -= 10
        if vis > 20000: score += 10
            
        return max(0, min(100, score)), {"low": low, "mid": mid, "high": high, "pm2.5": pm25}
    except Exception:
        return 0, {}

# --- 3. 網頁主介面 ---
st.title("🌅 永康火燒雲預報")

col1, col2 = st.columns([1, 2])
with col1:
    st.info("觀測點：台南市永康區")
with col2:
    loc = streamlit_geolocation()

# 座標處理
lat, lon = 23.02, 120.22
if loc and loc.get('latitude'):
    lat = loc['latitude']
    lon = loc['longitude']
    st.success("已定位")

with st.spinner('📡 分析大氣數據中...'):
    weather_data, pm25 = get_data(lat, lon)

if weather_data and 'daily' in weather_data:
    # 資料解析
    sunset_str = weather_data['daily']['sunset']
    sunset_dt = datetime.fromisoformat(sunset_str)
    sunset_time = sunset_dt.strftime("%H:%M")
    sunset_hour = sunset_dt.hour
    
    prob, details = calculate_burn_probability(weather_data, pm25, sunset_hour)
    
    # 顯示結果
    st.markdown("---")
    st.metric("🔥 火燒雲機率", f"{prob}%", delta=f"日落時間 {sunset_time}")
    
    if prob >= 80: st.error("📸 大景警報！建議立刻出門！")
    elif prob >= 60: st.warning("📷 有機會出景，值得碰運氣。")
    elif prob >= 40: st.info("☁️ 普通，可能只有淡淡顏色。")
    else: st.write("💤 機率偏低。")

    st.markdown("#### 📊 大氣參數")
    c1, c2, c3 = st.columns(3)
    c1.metric("高空卷雲", f"{details.get('high', 0)}%")
    c2.metric("低空雲量", f"{details.get('low', 0)}%")
    c3.metric("PM2.5", f"{details.get('pm2.5', 0)}")
    
    # ==========================================
    #  互動式地圖模組 (PyDeck)
    # ==========================================
    st.markdown("---")
    st.markdown("### 🗺️ 火燒雲戰情地圖")
    
    layers_selected = st.multiselect(
        "選擇顯示圖層：",
        ["📍 現在位置", "☁️ 低雲分布", "🌥️ 中雲分布", "🔥 高雲分布", "☀️ 日落方位線"],
        default=["📍 現在位置", "🔥 高雲分布", "☀️ 日落方位線"]
    )

    deck_layers =' ' # <--- 這裡修正了！加上了

    # 1. 太陽方位線
    if "☀️ 日落方位線" in layers_selected:
        try:
            azimuth = weather_data['hourly']['sun_azimuth'][sunset_hour]
            line_len = 0.5
            angle = math.radians(azimuth)
            end_lon = lon + line_len * math.sin(angle)
            end_lat = lat + line_len * math.cos(angle)

            deck_layers.append(pdk.Layer(
                "LineLayer",
                [{"start": [lon, lat], "end": [end_lon, end_lat]}],
                get_source_position="start",
                get_target_position="end",
                get_color=, 
                get_width=5,
            ))
        except: pass

    # 2. 雲層分布 (紅/橘/灰圓圈)
    cloud_cfgs = {
        "☁️ 低雲分布": {"val": details.get('low'), "col": [128, 128, 128], "r": 3000},
        "🌥️ 中雲分布": {"val": details.get('mid'), "col": , "r": 2000},
        "🔥 高雲分布": {"val": details.get('high'), "col": , "r": 1000}
    }
    
    for name, cfg in cloud_cfgs.items():
        if name in layers_selected:
            op = int((cfg['val']/100)*200) + 50
            deck_layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=[{"pos": [lon, lat]}],
                get_position="pos",
                get_color=cfg['col'] + [op],
                get_radius=cfg['r'],
                pickable=True,
            ))

    # 3. 現在位置 (藍點)
    if "📍 現在位置" in layers_selected:
        deck_layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"pos": [lon, lat]}],
            get_position="pos",
            get_color=,
            get_radius=200,
        ))

    view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=11)
    st.pydeck_chart(pdk.Deck(layers=deck_layers, initial_view_state=view_state))

else:

    st.error("無法連線氣象伺服器，請稍後再試。")
