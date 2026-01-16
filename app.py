import math
import pydeck as pdk
import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# 設定網頁標題與圖示
st.set_page_config(page_title="台南永康火燒雲預報", page_icon="🌅", layout="centered")

# CSS 優化：調整手機版字體與邊距
st.markdown("""
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 5rem; }
       h1 { font-size: 1.5rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 核心函式：取得氣象與空品資料 ---
def get_data(lat, lon):
    # 1. 取得 Open-Meteo 氣象預報
    try:
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
    except Exception as e:
        return None, None

    # 2. 取得民生公共物聯網空氣品質 (PM2.5)
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

# --- 核心演算法：計算火燒雲機率 ---
def calculate_burn_probability(weather_data, pm25, target_hour):
    try:
        idx = target_hour # 直接用小時當索引
        
        hourly = weather_data['hourly']
        low = hourly['cloud_cover_low'][idx]
        mid = hourly['cloud_cover_mid'][idx]
        high = hourly['cloud_cover_high'][idx]
        humidity = hourly['relative_humidity_2m'][idx]
        visibility = hourly['visibility'][idx]
        
        score = 0
        # 1. 中高雲 (畫布)
        mid_high_total = mid + high
        if 30 <= mid_high_total <= 80: score += 50
        elif 10 <= mid_high_total < 30: score += 30
        else: score += 10
            
        # 2. 低雲 (阻擋)
        if low < 30: score += 20
        elif low > 60: score -= 30
            
        # 3. 空氣品質
        if 15 <= pm25 <= 40: score += 20
        elif pm25 > 60: score -= 10
        else: score += 10
            
        # 4. 修正
        if humidity > 85: score -= 10
        if visibility > 20000: score += 10
            
        final_score = max(0, min(100, score))
        return final_score, {"low": low, "mid": mid, "high": high, "pm2.5": pm25}
    except Exception:
        return 0, {}

# --- 網頁介面顯示 ---
st.title("🌅 永康火燒雲預報")

col1, col2 = st.columns([1, 2])
with col1:
    st.info("觀測點：台南市永康區")
with col2:
    loc = streamlit_geolocation()

# 預設座標
lat, lon = 23.02, 120.22
if loc and loc.get('latitude'):
    lat = loc['latitude']
    lon = loc['longitude']
    st.success("已更新位置")

with st.spinner('📡 分析大氣數據中...'):
    weather_data, pm25 = get_data(lat, lon)

if weather_data and 'daily' in weather_data:
    # ========== 關鍵修正區 (第 112 行左右) ==========
    # 注意看這裡最後面的 
    sunset_str = weather_data['daily']['sunset'].pop(0) 
    # ============================================
    
    sunset_dt = datetime.fromisoformat(sunset_str)
    sunset_time = sunset_dt.strftime("%H:%M")
    sunset_hour = sunset_dt.hour
    
    prob, details = calculate_burn_probability(weather_data, pm25, sunset_hour)
    
    st.markdown("---")
    st.metric("🔥 火燒雲機率", f"{prob}%", delta=f"日落時間 {sunset_time}")
    
    if prob >= 80: st.error("📸 大景警報！建議立刻出門！")
    elif prob >= 60: st.warning("📷 有機會出景，值得碰運氣。")
    elif prob >= 40: st.info("☁️ 普通，可能只有淡淡顏色。")
    else: st.write("💤 機率偏低，雲太厚或太少。")

    st.markdown("#### 📊 大氣參數")
    c1, c2, c3 = st.columns(3)
    c1.metric("高空卷雲", f"{details.get('high', 0)}%")
    c2.metric("低空雲量", f"{details.get('low', 0)}%")
    c3.metric("PM2.5", f"{details.get('pm2.5', 0)}")
        
#... (前面的程式碼保持不變)...

    # ==========================================
    #  新的互動式地圖模組 (取代原本的 st.map)
    # ==========================================
    st.markdown("### 🗺️ 火燒雲觀測地圖")
    
    # 1. 建立圖層選擇器 (複選框)
    layers_selected = st.multiselect(
        "選擇顯示圖層：",
        ["📍 現在位置", "☁️ 低雲分布", "🌥️ 中雲分布", "🔥 高雲分布 (關鍵)", "☀️ 日落方位線"],
        default=["📍 現在位置", "🔥 高雲分布 (關鍵)", "☀️ 日落方位線"]
    )

    # 準備繪圖資料
    # 我們用圓形的半徑大小或透明度來代表雲量多少
    # 為了讓地圖好看，我們設定一個基礎半徑 (公尺)
    base_radius = 2000 
    
    deck_layers =

    # --- 圖層 1: 太陽方位線 (Sun Azimuth Line) ---
    if "☀️ 日落方位線" in layers_selected:
        # 取得日落時的太陽方位角
        azimuth = weather_data['hourly']['sun_azimuth'][target_hour_idx]
        
        # 利用三角函數計算延伸線的終點 (長度約 50 公里)
        line_len_km = 0.5  # 約 50km 的經緯度差
        angle_rad = math.radians(azimuth)
        end_lon = lon + line_len_km * math.sin(angle_rad)
        end_lat = lat + line_len_km * math.cos(angle_rad)

        line_data = [{"start": [lon, lat], "end": [end_lon, end_lat], "name": "Sunset Direction"}]
        
        layer_sun = pdk.Layer(
            "LineLayer",
            line_data,
            get_source_position="start",
            get_target_position="end",
            get_color=,  # 金黃色
            get_width=5,
            pickable=True,
        )
        deck_layers.append(layer_sun)

    # --- 圖層 2, 3, 4: 雲層 (Low, Mid, High) ---
    # 定義雲層的顏色與數據
    cloud_configs = {
        "☁️ 低雲分布": {"val": details.get('low', 0), "color": , "radius": 3000},   # 灰色
        "🌥️ 中雲分布": {"val": details.get('mid', 0), "color": , "radius": 2000},   # 橘色
        "🔥 高雲分布 (關鍵)": {"val": details.get('high', 0), "color": , "radius": 1000} # 紅色
    }

    for layer_name, config in cloud_configs.items():
        if layer_name in layers_selected:
            # 透明度依據雲量決定 (0-255)
            opacity = int((config["val"] / 100) * 200) + 50 
            
            layer_cloud = pdk.Layer(
                "ScatterplotLayer",
                data=[{"position": [lon, lat], "name": layer_name}],
                get_position="position",
                get_color=config["color"] + [opacity], # 加上透明度
                get_radius=config["radius"],
                pickable=True,
                stroked=True,
                filled=True,
                line_width_min_pixels=1,
            )
            deck_layers.append(layer_cloud)

    # --- 圖層 5: 現在位置 (User Location) ---
    if "📍 現在位置" in layers_selected:
        layer_user = pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lon, lat], "name": "You are here"}],
            get_position="position",
            get_color=, # 藍色
            get_radius=200,               # 小圓點
            pickable=True,
        )
        deck_layers.append(layer_user)

    # 繪製地圖
    view_state = pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=11,
        pitch=0,
    )

    st.pydeck_chart(pdk.Deck(
        layers=deck_layers,
        initial_view_state=view_state,
        tooltip={"text": "{name}"}
    ))

else:

    st.error("無法連線氣象伺服器，請稍後再試。")

