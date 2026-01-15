import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
# from streamlit_geolocation import streamlit_geolocation  <-- 暫時註解掉

# 設定網頁標題與圖示
st.set_page_config(page_title="台南永康火燒雲預報", page_icon="🌅", layout="centered")

# --- 核心函式：取得氣象與空品資料 ---
def get_data(lat, lon):
    # 1. 取得 Open-Meteo 氣象預報
    try:
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,relative_humidity_2m",
            "daily": "sunset",
            "timezone": "Asia/Taipei",
            "forecast_days": 1
        }
        weather_res = requests.get(weather_url, params=weather_params).json()
    except Exception as e:
        st.error(f"氣象資料獲取失敗: {e}")
        return None, None

    # 2. 取得民生公共物聯網空氣品質 (PM2.5)
    pm25_value = 25 # 預設值
    try:
        iot_url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_EPAIoT/v1.1/Things"
        iot_params = {
            "$filter": "properties/stationName eq '臺南'",
            "$expand": "Datastreams($filter=name eq 'PM2.5';$expand=Observations($top=1;$orderby=phenomenonTime desc))"
        }
        iot_res = requests.get(iot_url, params=iot_params).json()
        
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
        times = weather_data['hourly']['time']
        target_idx = 0
        for i, t in enumerate(times):
            if f"T{target_hour:02d}:" in t: # 確保格式對齊 (如 T17:)
                target_idx = i
                break
        
        low = weather_data['hourly']['cloud_cover_low'][target_idx]
        mid = weather_data['hourly']['cloud_cover_mid'][target_idx]
        high = weather_data['hourly']['cloud_cover_high'][target_idx]
        humidity = weather_data['hourly']['relative_humidity_2m'][target_idx]
        visibility = weather_data['hourly']['visibility'][target_idx]
        
        score = 0
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
        if visibility > 20000: score += 10
            
        final_score = max(0, min(100, score))
        return final_score, {"low": low, "mid": mid, "high": high, "pm2.5": pm25}
    except Exception:
        return 0, {}

# --- 網頁介面顯示 ---
st.title("🌅 台南永康火燒雲預報")
st.markdown("結合 **Open-Meteo** 與 **民生公共物聯網**")

col1, col2 = st.columns([1, 2])
with col1:
    st.write("觀測點：台南市永康區 (暫時關閉自動定位)")
with col2:
    # 手動指定永康座標
    loc = {'latitude': 23.02, 'longitude': 120.22}

lat, lon = 23.02, 120.22

with st.spinner('正在分析大氣資料...'):
    weather_data, pm25 = get_data(lat, lon)

if weather_data and 'daily' in weather_data:
    # --- 修正點：加上  取出清單中的第一筆資料 ---
    sunset_str = weather_data[daily][sunset]
                                     
    sunset_dt = datetime.fromisoformat(sunset_str)
    sunset_time = sunset_dt.strftime("%H:%M")
    sunset_hour = sunset_dt.hour
    
    prob, details = calculate_burn_probability(weather_data, pm25, sunset_hour)
    
    st.markdown("---")
    st.header(f"🔥 今日火燒雲機率：{prob}%")
    st.caption(f"預測目標時間 (日落)：{sunset_time}")
    
    if prob >= 80: st.error("📸 大景警報！建議立刻出門！")
    elif prob >= 60: st.warning("📷 有機會出景，值得碰運氣。")
    elif prob >= 40: st.info("☁️ 普通，可能只有淡淡顏色。")
    else: st.write("💤 機率偏低，在家休息吧。")

    st.markdown("### 📊 詳細參數")
    c1, c2, c3 = st.columns(3)
    c1.metric("高空卷雲", f"{details.get('high', 0)}%")
    c2.metric("低空雲量", f"{details.get('low', 0)}%")
    c3.metric("PM2.5", f"{details.get('pm2.5', 0)}")
    
    st.map(pd.DataFrame({'lat': [lat], 'lon': [lon]}))
else:
    st.error("無法連線氣象伺服器，請稍後再試。")
