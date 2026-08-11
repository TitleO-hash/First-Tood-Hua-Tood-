import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_ema(series: pd.Series, period: int = 200) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def fetch_data(symbol: str, lookback_days: int = 270) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=lookback_days)
    df = yf.download(symbol, start=start, end=end,
                     auto_adjust=False, progress=False)
    if df.empty:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    df["RSI"] = calc_rsi(df["Close"])
    df["EMA200"] = calc_ema(df["Close"], 200)
    return df


def validate_downtrend_before_tood1(
    df: pd.DataFrame,
    tood1_idx,
    lookback_months: int = 3,
    min_days: int = 30,
    max_pct_above_ema: float = 0.05,
) -> bool:
    """
    ย้อนซ้ายจาก tood1_idx ไป lookback_months เดือน
    ตรวจว่าทุกวันใน window นั้น Close <= EMA200 * (1 + max_pct_above_ema)

    - ถ้าข้อมูลน้อยกว่า min_days → False (ตัดทิ้ง)
    - ถ้ามีวันไหน Close > EMA200 * 1.05 → False
    - ผ่านทั้งหมด → True
    """
    tood1_pos = df.index.get_loc(tood1_idx)

    # คำนวณ cutoff ย้อนหลัง lookback_months เดือน
    tood1_date = df.index[tood1_pos]
    cutoff_date = tood1_date - pd.DateOffset(months=lookback_months)

    # window ซ้ายมือก่อน tood1
    window = df.iloc[:tood1_pos]
    window = window[window.index >= cutoff_date]

    # ตรวจจำนวนวันขั้นต่ำ
    if len(window) < min_days:
        return False

    # ตรวจว่าทุกวัน Close <= EMA200 * (1 + max_pct_above_ema)
    ema200 = window["EMA200"]
    close = window["Close"]

    # ถ้า EMA200 มี NaN ให้ข้ามวันนั้น (ช่วงต้นที่ EMA ยังไม่ stable)
    valid_mask = ema200.notna()
    if valid_mask.sum() < min_days:
        return False

    above_limit = close[valid_mask] > ema200[valid_mask] * (1 + max_pct_above_ema)
    if above_limit.any():
        return False

    return True


def detect_pattern(
    df: pd.DataFrame,
    scan_days: int = 90,
    downtrend_months: int = 3,
    min_downtrend_days: int = 30,
    skip_tood1_confirmation: bool = False,
) -> dict:
    """
    ไล่อ่านกราฟจากซ้ายไปขวา ทีละวัน เหมือนคนอ่านกราฟจริงๆ

    Param `skip_tood1_confirmation`:
      - False (ค่าเริ่มต้น, ใช้กับ Gen 1) : ตูด 1 ต้องรอ RSI Diff >= 8
        จาก ATL ก่อนถึงจะยืนยัน แล้วเริ่มไล่ตามว่าที่หัวจากจุดนั้น
      - True (ใช้กับ Gen 2 ขึ้นไป) : ตูด 1 ของ Gen ใหม่ = ตูด 2 ของ Gen
        ก่อนหน้า (จุด breakout) ซึ่งรู้อยู่แล้วโดยไม่ต้องยืนยันซ้ำ
        → เริ่มไล่ตามว่าที่หัวได้ทันทีจากจุดนั้นเลย

    State: FIND_B  (เฉพาะตอน skip_tood1_confirmation=False)
    - ว่าที่ A = ATL 90 วัน
    - ตรวจขาลงก่อน ตูด 1: ย้อนซ้าย 3 เดือน Close <= EMA200 * 1.05
    - ไล่ขวา ทีละวัน
    - ถ้า RSI Diff (วันนั้น - ว่าที่ A) >= 8
      → A ยืนยัน (ตูด 1 confirmed), ราคาวันนั้น = ว่าที่ B (เริ่มไล่ตามหัว)
      → เปลี่ยนไป State: CONFIRM_B

    State: CONFIRM_B  (ไล่ตามว่าที่หัว — "หัว" ยังไม่ confirm)
    - ไล่ขวา ทีละวัน
    - ถ้าราคาปิดสูงกว่า ว่าที่ B
      → ยกเลิก ว่าที่ B เดิม, ว่าที่ B ใหม่ = ราคาวันนี้ (ยังไม่ confirm)
    - ถ้าราคาย่อลงจน RSI Diff (ว่าที่ B - วันนั้น) >= 8
      → B ยืนยัน (หัว confirmed) → head_confirmed = True
      → นี่คือจุดเดียวที่ระบบควรสลับการแสดงผลจาก Gen เดิม → Gen ใหม่
      → เปลี่ยนไป State: CONFIRM_C

    State: CONFIRM_C
    - ไล่ขวา ทีละวัน
    - ถ้าราคาปิดต่ำกว่า A → ล้างไพ่
    - ถ้าราคาปิดสูงกว่า B → C ยืนยัน (ตูด 2 confirmed) + Breakout พร้อมกัน = Signal BUY!
    - ถ้ายังไม่เกิดทั้งสอง → จ่อ Break (ติดตาม Low ใหม่เป็น ว่าที่ C)
    """

    result = {
        "state": "no_pattern",
        "head_confirmed": False,
        "tood1_idx": None, "tood1_price": None, "tood1_rsi": None,
        "hua_idx": None, "hua_price": None, "hua_rsi": None,
        "tood2_idx": None, "tood2_price": None,
        "tood2_candidate_price": None, "tood2_candidate_idx": None,
        "breakout_idx": None, "breakout_price": None,
        "pending_rsi_diff": None,
        "pct_from_hua": None,
        "days_since_break": None,
        "priority_group": None,
    }

    # ── ว่าที่ A = ATL ใน scan_days ──────────────────────────────────────
    if scan_days <= 365:
        cutoff = df.index[-1] - pd.Timedelta(days=scan_days)
        window = df[df.index >= cutoff]
    else:
        window = df
    if len(window) < 10:
        return result

    atl_idx = window["Close"].idxmin()
    atl_price = float(df.loc[atl_idx, "Close"])
    atl_rsi = float(df.loc[atl_idx, "RSI"])
    if pd.isna(atl_rsi):
        return result

    # ── ตรวจขาลงก่อน ตูด 1 (เฉพาะ Gen 1 — downtrend_months > 0) ────────
    if downtrend_months > 0:
        if not validate_downtrend_before_tood1(
            df,
            tood1_idx=atl_idx,
            lookback_months=downtrend_months,
            min_days=min_downtrend_days,
        ):
            return {**result, "state": "no_downtrend"}

    # ── ไล่ขวาจาก ATL ────────────────────────────────────────────────────
    atl_pos = df.index.get_loc(atl_idx)
    scan = df.iloc[atl_pos + 1:]

    if skip_tood1_confirmation:
        # Gen 2 ขึ้นไป: ตูด 1 คือจุด breakout เดิม รู้อยู่แล้วไม่ต้องยืนยันซ้ำ
        # เริ่มไล่ตามว่าที่หัวได้ทันทีจากราคา ณ จุดตูด 1 นี้เลย
        current_state = "CONFIRM_B"
        b_price = atl_price
        b_rsi = atl_rsi
        b_idx = atl_idx
    else:
        current_state = "FIND_B"
        b_price = None
        b_rsi = None
        b_idx = None

    c_price = None
    c_idx = None

    for idx, row in scan.iterrows():
        close = float(row["Close"])
        rsi_val = row["RSI"]
        if pd.isna(rsi_val):
            continue
        rsi = float(rsi_val)

        # ══════════════════════════════════════════════════════════════════
        # State: FIND_B  (ยืนยันตูด 1 ด้วย RSI Diff 8 — เฉพาะ Gen 1)
        # ══════════════════════════════════════════════════════════════════
        if current_state == "FIND_B":
            diff = rsi - atl_rsi
            if diff >= 8:
                b_price = close
                b_rsi = rsi
                b_idx = idx
                current_state = "CONFIRM_B"

        # ══════════════════════════════════════════════════════════════════
        # State: CONFIRM_B  (ไล่ตามว่าที่หัว — ยังไม่ confirm)
        # ══════════════════════════════════════════════════════════════════
        elif current_state == "CONFIRM_B":
            if close > b_price:
                b_price = close
                b_rsi = rsi
                b_idx = idx
            else:
                diff = b_rsi - rsi
                if diff >= 8:
                    c_price = close
                    c_idx = idx
                    current_state = "CONFIRM_C"
                    # ✨ จุดยืนยันหัวจริง — สัญญาณให้สลับแสดงผล Gen ใหม่
                    result["head_confirmed"] = True

        # ══════════════════════════════════════════════════════════════════
        # State: CONFIRM_C
        # ══════════════════════════════════════════════════════════════════
        elif current_state == "CONFIRM_C":
            if close < atl_price:
                return {**result, "state": "cancelled", "head_confirmed": True}

            if close <= c_price:
                c_price = close
                c_idx = idx

            if close > b_price:
                result["tood1_idx"] = atl_idx
                result["tood1_price"] = atl_price
                result["tood1_rsi"] = atl_rsi
                result["hua_idx"] = b_idx
                result["hua_price"] = b_price
                result["hua_rsi"] = b_rsi
                result["tood2_idx"] = c_idx
                result["tood2_price"] = c_price
                result["tood2_candidate_price"] = c_price
                result["tood2_candidate_idx"] = c_idx
                result["breakout_idx"] = idx
                result["breakout_price"] = close
                result["state"] = "confirmed"
                today = df.index[-1]
                result["days_since_break"] = (today - idx).days
                d = result["days_since_break"]
                if d <= 2:
                    result["priority_group"] = "break_lv4"
                elif d <= 5:
                    result["priority_group"] = "break_lv3"
                elif d <= 10:
                    result["priority_group"] = "break_lv2"
                else:
                    result["priority_group"] = "break_lv1"
                break

    # ── ยังไม่ Breakout = จ่อ Break ──────────────────────────────────────
    if result["state"] == "no_pattern" and current_state in ("CONFIRM_B", "CONFIRM_C"):
        result["tood1_idx"] = atl_idx
        result["tood1_price"] = atl_price
        result["tood1_rsi"] = atl_rsi
        result["hua_idx"] = b_idx
        result["hua_price"] = b_price
        result["hua_rsi"] = b_rsi
        result["tood2_candidate_price"] = c_price
        result["tood2_candidate_idx"] = c_idx

        latest = df.iloc[-1]
        latest_close = float(latest["Close"])

        tood2_rsi = None
        if c_idx is not None and not pd.isna(df.loc[c_idx, "RSI"]):
            tood2_rsi = float(df.loc[c_idx, "RSI"])

        pending_diff = (b_rsi - tood2_rsi) if tood2_rsi else 0
        result["pending_rsi_diff"] = round(pending_diff, 2)
        result["pct_from_hua"] = round(
            (b_price - latest_close) / b_price * 100, 2
        ) if b_price else None

        if current_state == "CONFIRM_C":
            if pending_diff >= 8 and result["pct_from_hua"] is not None and result["pct_from_hua"] <= 3:
                result["priority_group"] = 4
            elif pending_diff >= 8:
                result["priority_group"] = 3
            elif pending_diff >= 4:
                result["priority_group"] = 2
            else:
                result["priority_group"] = 1
        else:
            result["priority_group"] = 1

        result["state"] = "จ่อ_break"

    return result


def detect_nested(
    df: pd.DataFrame,
    scan_days: int = 90,
    downtrend_months: int = 3,
    min_downtrend_days: int = 30,
) -> dict:
    current_result = detect_pattern(
        df, scan_days,
        downtrend_months=downtrend_months,
        min_downtrend_days=min_downtrend_days,
    )
    current_result["generation"] = 1
    current_df = df
    gen = 1

    while (current_result.get("state") == "confirmed"
           and current_result.get("tood2_idx") is not None):
        tood2_pos = current_df.index.get_loc(current_result["tood2_idx"])
        next_df = current_df.iloc[tood2_pos:]
        if len(next_df) < 20:
            break
        # Gen 2+ : ตูด 1 = ตูด 2 ของ Gen ก่อนหน้า (breakout point) รู้อยู่แล้ว
        # ไม่ต้องเช็ค downtrend ซ้ำ และไม่ต้องรอ RSI Diff ยืนยันตูด 1 ซ้ำ
        next_result = detect_pattern(
            next_df, scan_days=999,
            downtrend_months=0,
            min_downtrend_days=0,
            skip_tood1_confirmation=True,
        )
        gen += 1
        next_result["generation"] = gen
        next_result["parent"] = current_result

        # ✨ สลับการแสดงผลไป Gen ใหม่ ก็ต่อเมื่อ "หัว" ของ Gen ใหม่ confirm
        # แล้วเท่านั้น (RSI Diff 8 ลงจากว่าที่หัว) — ไม่ใช่แค่เริ่มไล่ตามหัว
        if next_result.get("head_confirmed"):
            current_result = next_result
            current_df = next_df
        else:
            break

    return current_result


def scan_universe(
    symbols: list,
    scan_days: int = 90,
    downtrend_months: int = 3,
    min_downtrend_days: int = 30,
) -> list:
    results = []
    for sym in symbols:
        try:
            df = fetch_data(sym, lookback_days=scan_days + 180)
            if df.empty or len(df) < 30:
                continue
            state = detect_nested(
                df, scan_days=scan_days,
                downtrend_months=downtrend_months,
                min_downtrend_days=min_downtrend_days,
            )
            if state.get("state") in ("no_pattern", "searching", "cancelled", "no_data", "no_downtrend"):
                continue
            state["symbol"] = sym
            state["latest_close"] = round(float(df["Close"].iloc[-1]), 2)
            state["scan_date"] = df.index[-1].strftime("%Y-%m-%d")
            results.append(state)
        except Exception as e:
            print(f"Error {sym}: {e}")
            continue

    group_order = {4: 0, 3: 1, 2: 2, 1: 3,
                   "break_lv4": 4, "break_lv3": 5,
                   "break_lv2": 6, "break_lv1": 7}

    def sort_key(r):
        pg = group_order.get(r.get("priority_group"), 99)
        pct = r.get("pct_from_hua") or 999
        return (pg, pct)

    results.sort(key=sort_key)
    return results
