import requests
import streamlit as st

def get_weather_data(lat, lon):
    """從 Open-Meteo 取得氣象預報"""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,relative_humidity_2m",
            "daily": "sunset",
            "timezone": "Asia/Taipei",
            "forecast_days": 1
        }
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Weather API Error: {e}")
        return None

def get_aqi_data(station_name="臺南"):
    """從民生公共物聯網取得 PM2.5 (預設台南測站)"""
    try:
        url = "https://sta.ci.taiwan.gov.tw/STA_AirQuality_EPAIoT/v1.1/Things"
        params = {
            "$filter": f"properties/stationName eq '{station_name}'",
            "$expand": "Datastreams($filter=name eq 'PM2.5';$expand=Observations($top=1;$orderby=phenomenonTime desc))"
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        # 解析複雜的 JSON 結構
        if 'value' in data and len(data['value']) > 0:
            datastream = data['value'].get('Datastreams',)
            if datastream:
                obs = datastream.get('Observations',)
                if obs:
                    return obs['result']
    except Exception as e:
        print(f"AQI API Error: {e}")
    
    return 25.0 # 若失敗回傳預設值