import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit_geolocation import streamlit_geolocation

# 設定網頁標題與圖示
st.set_page_config(page_title="台南永康火燒雲預報", page_icon="🌅", layout="centered")

# --- 核心函式：取得氣象與空品資料 ---
def get_data(lat, lon):
    # 1. 取得 Open-Meteo 氣象預報 (雲量、能見度、日落時間)
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

    # 2. 取得民生公共物聯網空氣品質 (PM2.5) - 鎖定台南測站
    pm25_value = 25 # 預設值 (若 API 失敗)
    try:
        # 使用 OGC SensorThings API 篩選台南測站的 PM2.5 最新一筆資料
        iot_url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_EPAIoT/v1.1/Things"
        iot_params = {
            "$filter": "properties/stationName eq '臺南'",
            "$expand": "Datastreams($filter=name eq 'PM2.5';$expand=Observations($top=1;$orderby=phenomenonTime desc))"
        }
        iot_res = requests.get(iot_url, params=iot_params).json()
        
        # 解析複雜的 JSON 結構
        if 'value' in iot_res and len(iot_res['value']) > 0:
            datastreams = iot_res['value'].get('Datastreams',)
            if datastreams:
                observations = datastreams.get('Observations',)
                if observations:
                    pm25_value = observations['result']
    except Exception:
        pass # 若失敗則使用預設值，避免程式崩潰

    return weather_res, pm25_value

# --- 核心演算法：計算火燒雲機率 ---
def calculate_burn_probability(weather_data, pm25, target_hour):
    # 取出指定時間(日落)的資料索引
    try:
        # 簡單映射：找到最接近日落小時的 index
        times = weather_data['hourly']['time']
        target_idx = 0
        for i, t in enumerate(times):
            if f"T{target_hour}:" in t:
                target_idx = i
                break
        
        low = weather_data['hourly']['cloud_cover_low'][target_idx]
        mid = weather_data['hourly']['cloud_cover_mid'][target_idx]
        high = weather_data['hourly']['cloud_cover_high'][target_idx]
        humidity = weather_data['hourly']['relative_humidity_2m'][target_idx]
        visibility = weather_data['hourly']['visibility'][target_idx]
        
        # --- 評分邏輯 (滿分 100) ---
        score = 0
        
        # 1. 中高雲 (畫布): 30%-70% 最佳
        mid_high_total = mid + high
        if 30 <= mid_high_total <= 80:
            score += 50
        elif 10 <= mid_high_total < 30:
            score += 30
        else:
            score += 10 # 太少或太多都扣分
            
        # 2. 低雲 (阻擋): 越少越好
        if low < 30:
            score += 20
        elif low > 60:
            score -= 30 # 嚴重扣分，擋光
            
        # 3. 空氣品質 (PM2.5): 適量微粒(15-35)有助散射紅光，太多(>50)會髒
        if 15 <= pm25 <= 40:
            score += 20
        elif pm25 > 60:
            score -= 10
        else:
            score += 10
            
        # 4. 濕度與能見度修正
        if humidity > 85:
            score -= 10 # 霧氣重
        if visibility > 20000: # 20km
            score += 10
            
        final_score = max(0, min(100, score))
        
        return final_score, {"low": low, "mid": mid, "high": high, "pm2.5": pm25}
        
    except Exception as e:
        return 0, {}

# --- 網頁介面顯示 ---
st.title("🌅 台南永康火燒雲預報")
st.markdown("結合 **Open-Meteo 氣象模型** 與 **民生公共物聯網** 即時數據")

# 1. 取得位置 (預設永康)
col1, col2 = st.columns([1, 2])
with col1:
    st.write("預設觀測點：台南市永康區")
with col2:
    loc = streamlit_geolocation()
    
lat, lon = 23.02, 120.22 # 永康預設座標
if loc and loc.get('latitude'):
    lat = loc['latitude']
    lon = loc['longitude']
    st.success("已使用您的即時位置！")

# 2. 執行分析
with st.spinner('正在分析大氣資料...'):
    weather_data, pm25 = get_data(lat, lon)

if weather_data:
    # 取得今日日落時間
    sunset_str = weather_data['daily']['sunset']
    sunset_dt = datetime.fromisoformat(sunset