import streamlit as st
import requests
import pandas as pd
import numpy as np
import math
import pydeck as pdk
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# --- 0. 定義顏色與參數 (移到最上方，避免括號消失) ---
# 使用 tuple 寫法，PyDeck 也能讀取，且不會被系統過濾
COLOR_GOLD = (255, 215, 0)   # 金色 (太陽線)
COLOR_GRAY = (128, 128, 128) # 灰色 (低雲)
COLOR_ORANGE = (255, 140, 0) # 橘色 (中雲)
COLOR_RED = (255, 69, 0)     # 紅色 (高雲)
COLOR_BLUE = (0, 128, 255)   # 藍色 (現在位置)

# 1. 設定網頁標題與圖示
st.set_page_config(page_title="台南永康火燒雲預報", page_icon="🌅", layout="centered")

# CSS 優化
st.markdown("""
    <style>
   .block-container { padding-top: 2rem; padding-bottom: 5rem; }
       h1 { font-size: 1.5rem!important; }
       div[data-testid="stMetricValue"] { font-size: 1.2rem!important; }
    </style>
""", unsafe_allow_html=True)

# --- 核心函式：取得氣象與空品資料 ---
def get_data(lat, lon):
    weather_res = None
    try:
        # 請求 Open-Meteo API
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,relative_humidity_2m,sun_azimuth",
            "daily": "sunset",
            "timezone": "Asia/Taipei",
            "forecast_days": 1
        }
        headers = {"User-Agent": "StreamlitFireCloudApp/1.0"}
        
        response = requests.get(weather_url, params=weather_params, headers=headers, timeout=10)
        if response.status_code == 200:
            weather_res = response.json()
    except Exception as e:
        st.error(f"氣象資料連線錯誤: {e}")

    # 取得民生公共物聯網空氣品質 (PM2.5)
    pm25_value = 25 # 預設值
    try:
        iot_url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_EPAIoT/v1.1/Things"
        iot_params = {
            "$filter": "properties/stationName eq '臺南'",
            "$expand": "Datastreams($filter=name eq 'PM2.5';$expand=Observations($top=1;$orderby=phenomenonTime desc))"
        }
        iot_res = requests.get(iot_url, params=iot_params, timeout=5).json()
        
        if 'value' in iot_res and len(iot_res['value']) > 0:
            datastreams = iot_res['value'].get('Datastreams', list())
            if datastreams:
                observations = datastreams.get('Observations', list())
                if observations:
                    pm25_value = observations['result']
    except Exception:
        pass 

    return weather_res, pm25_value

# --- 核心演算法：計算火燒雲機率 ---
def calculate_burn_probability(weather_data, pm25, target_hour):
    try:
        idx = target_hour
        hourly = weather_data['hourly']
        
        if idx >= len(hourly['cloud_cover_low']):
            idx = 0
            
        low = hourly['cloud_cover_low'][idx]
        mid = hourly['cloud_cover_mid'][idx]
        high = hourly['cloud_cover_high'][idx]
        humidity = hourly['relative_humidity_2m'][idx]
        vis = hourly['visibility'][idx]
        
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
        if vis > 20000: score += 10
            
        final_score = max(0, min(100, score))
        return final_score, {"low": low, "mid": mid, "high": high, "pm2.5": pm25}
    except Exception:
        return 0, {}

# --- 輔助函式：估算日落方位角 ---
def estimate_sunset_azimuth():
    day_of_year = datetime.now().timetuple().tm_yday
    azimuth = 270 + 25 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
    return azimuth

# ==========================================
#  網頁主介面
# ==========================================

st.title("🌅 永康火燒雲預報")

col1, col2 = st.columns([1, 2])
with col1:
    st.info("觀測點：台南市永康區")
with col2:
    loc = streamlit_geolocation()

lat, lon = 23.02, 120.22
if loc and loc.get('latitude'):
    lat = loc['latitude']
    lon = loc['longitude']
    st.success("已定位")

with st.spinner('📡 正在分析大氣數據...'):
    weather_data, pm25 = get_data(lat, lon)

if weather_data and 'daily' in weather_data:
    # 資料處理
    sunset_list = weather_data['daily']['sunset']
    sunset_str = sunset_list.pop(0)
    
    sunset_dt = datetime.fromisoformat(sunset_str)
    sunset_time = sunset_dt.strftime("%H:%M")
    sunset_hour = sunset_dt.hour
    
    prob, details = calculate_burn_probability(weather_data, pm25, sunset_hour)
    
    # 顯示結果
    st.markdown("---")
    st.metric("🔥 火燒雲機率", f"{prob}%", delta=f"預測時間 {sunset_time}")
    
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
    #  互動式地圖模組
    # ==========================================
    st.markdown("---")
    st.markdown("### 🗺️ 火燒雲戰情地圖")
    
    layers_selected = st.multiselect(
        "選擇顯示圖層：",
        ["📍 現在位置", "☁️ 低雲分布", "🌥️ 中雲分布", "🔥 高雲分布", "☀️ 日落方位線"],
        default=["📍 現在位置", "🔥 高雲分布", "☀️ 日落方位線"]
    )

    # ★ 使用 list() 函式，避開中括號顯示問題 ★
    deck_layers = list()

    # 1. 太陽方位線圖層
    if "☀️ 日落方位線" in layers_selected:
        try:
            hourly_azimuth = weather_data['hourly'].get('sun_azimuth', list())
            if len(hourly_azimuth) > sunset_hour:
                azimuth = hourly_azimuth[sunset_hour]
            else:
                azimuth = estimate_sunset_azimuth()

            line_len_km = 0.05 
            angle_rad = math.radians(90 - azimuth)
            end_lon = lon + line_len_km * math.cos(angle_rad)
            end_lat = lat + line_len_km * math.sin(angle_rad)

            layer_sun = pdk.Layer(
                "LineLayer",
                data=[{"start": [lon, lat], "end": [end_lon, end_lat], "name": "Sunset"}],
                get_source_position="start",
                get_target_position="end",
                get_color=COLOR_GOLD,  # ★ 使用變數
                get_width=5,
                pickable=True,
            )
            deck_layers.append(layer_sun)
        except Exception:
            pass

    # 2. 雲層分布圖層
    cloud_cfgs = {
        "☁️ 低雲分布": {"val": details.get('low', 0), "col": COLOR_GRAY, "r": 3000},
        "🌥️ 中雲分布": {"val": details.get('mid', 0), "col": COLOR_ORANGE, "r": 2000},
        "🔥 高雲分布": {"val": details.get('high', 0), "col": COLOR_RED, "r": 1000}
    }
    
    for layer_name, config in cloud_cfgs.items():
        if layer_name in layers_selected:
            op = int((config["val"] / 100) * 200) + 50 
            # 將 tuple 轉為 list 並加上透明度
            final_color = list(config["col"])
            final_color.append(op)
            
            layer_cloud = pdk.Layer(
                "ScatterplotLayer",
                data=[{"position": [lon, lat], "name": f"{layer_name}: {config['val']}%"}],
                get_position="position",
                get_color=final_color,
                get_radius=config["r"],
                pickable=True,
                stroked=True,
                filled=True,
                line_width_min_pixels=1,
            )
            deck_layers.append(layer_cloud)

    # 3. 現在位置圖層
    if "📍 現在位置" in layers_selected:
        layer_user = pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lon, lat], "name": "You are here"}],
            get_position="position",
            get_color=COLOR_BLUE, # ★ 使用變數
            get_radius=200,
            pickable=True,
        )
        deck_layers.append(layer_user)

    # 繪製地圖
    view_state = pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=11,
        pitch=45,
    )

    st.pydeck_chart(pdk.Deck(
        layers=deck_layers,
        initial_view_state=view_state,
        tooltip={"text": "{name}"}
    ))

else:
    st.error("⚠️ 無法連線氣象伺服器，請檢查網路或稍後再試。")