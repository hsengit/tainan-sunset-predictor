def calculate_fci(low, mid, high, pm25, hum, vis):
    """
    計算火燒雲指數 (Fire Cloud Index, FCI)
    範圍: 0-100
    """
    score = 0
    
    # 1. 雲層結構 (權重最大)
    # 中高雲是畫布，30%-80% 最適合反射紅光
    total_high_mid = mid + high
    if 30 <= total_high_mid <= 80:
        score += 50
    elif 10 <= total_high_mid < 30 or 80 < total_high_mid <= 90:
        score += 30
    else:
        score += 10 # 雲太少或太厚
        
    # 2. 低雲阻擋 (扣分項)
    # 低雲會在西邊地平線擋住夕陽
    if low < 30:
        score += 20
    elif low > 60:
        score -= 40 # 嚴重扣分
    else:
        score += 0

    # 3. 空氣品質 PM2.5 (散射介質)
    # 適量的懸浮微粒(15-35)有助於米氏散射，讓紅光更豔麗
    if 15 <= pm25 <= 35:
        score += 20
    elif pm25 > 50:
        score -= 10 # 太髒，天空會灰暗
    else:
        score += 10 # 太乾淨，顏色可能偏淡

    # 4. 輔助修正 (濕度與能見度)
    if hum > 85:
        score -= 10 # 濕氣太重容易有霧霾
    if vis > 20000:
        score += 10 # 能見度好，光線通透

    return max(0, min(100, int(score)))

def get_advice(score):
    if score >= 80:
        return "🔥 大景警報！", "極高機率出現火燒雲，建議立刻帶著相機衝去河堤！"
    elif score >= 60:
        return "📷 值得一試", "有機會出現不錯的色溫，可以去碰碰運氣。"
    elif score >= 40:
        return "☁️ 普通晚霞", "雲層條件一般，可能只有淡淡的顏色。"
    else:
        return "💤 早點回家", "雲層太厚或下雨，出景機率極低。"