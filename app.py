import streamlit as st
import pandas as pd
from scanner import scan_universe

st.set_page_config(
    page_title="ตูด หัว ตูด+ต้นรอบ Scanner",
    page_icon="📊",
    layout="wide",
)

# ── โหลด Symbol Lists ─────────────────────────────────────────────────────────
def load_symbols_from_csv(path: str) -> list:
    try:
        df = pd.read_csv(path)
        return df.iloc[:, 0].dropna().str.strip().tolist()
    except Exception:
        return []

SET_SYMBOLS    = load_symbols_from_csv("SET.csv")
SET100_SYMBOLS = load_symbols_from_csv("SET100.csv")
SP500_SYMBOLS  = load_symbols_from_csv("SP500.csv")
US_SYMBOLS     = load_symbols_from_csv("US_Stock.csv")

UNIVERSE_MAP = {
    "SET":      SET_SYMBOLS,
    "SET100":   SET100_SYMBOLS,
    "SP500":    SP500_SYMBOLS,
    "US Stock": US_SYMBOLS,
}

# ── Symbol → TradingView format ───────────────────────────────────────────────
def symbol_to_tradingview(sym: str) -> str:
    """
    แปลง Yahoo-style symbol เป็น TradingView watchlist format
      .BK  -> SET:XXX      (ไทย)
      .HK  -> HKEX:XXX      (ฮ่องกง, ตัด leading zero ออก)
      อื่น ๆ -> คงเดิม        (US — ไม่มี suffix บอกตลาด)
    """
    s = sym.strip().upper()
    if s.endswith(".BK"):
        return f"SET:{s[:-3]}"
    if s.endswith(".HK"):
        code = s[:-3].lstrip("0") or "0"
        return f"HKEX:{code}"
    # US: Yahoo ใช้ "-" คั่น class ของหุ้น (เช่น BRK-B) แต่ TradingView ใช้ "."
    return s.replace("-", ".")


def build_tradingview_list(rows) -> str:
    """รับ list ของ result dict คืนเป็น text หนึ่ง symbol ต่อบรรทัด (TradingView import format)"""
    seen = []
    for r in rows:
        tv_sym = symbol_to_tradingview(r.get("symbol", ""))
        if tv_sym and tv_sym not in seen:
            seen.append(tv_sym)
    return "\n".join(seen)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 ตูด หัว ตูด+ต้นรอบ")
    st.caption("ระบบ ViVi Investor — VITALi")
    st.divider()

    st.subheader("เลือกรายชื่อหุ้น")
    input_mode = st.radio(
        "วิธีเลือก",
        options=["พิมพ์เอง", "SET", "SET100", "SP500", "US Stock", "อัปโหลด CSV"],
        index=0,
        horizontal=False,
    )

    symbols = []

    if input_mode == "พิมพ์เอง":
        symbols_input = st.text_area(
            "ใส่ชื่อหุ้น (บรรทัดละตัว)",
            value="PTT.BK\nADVANC.BK\nKBANK.BK\nSCC.BK\nCPALL.BK",
            height=180,
        )
        symbols = [s.strip().upper() for s in symbols_input.splitlines() if s.strip()]

    elif input_mode in UNIVERSE_MAP:
        sym_list = UNIVERSE_MAP[input_mode]
        if sym_list:
            st.success(f"โหลด {input_mode} ได้ {len(sym_list)} ตัว")
            symbols = sym_list
        else:
            st.warning(f"ไม่พบไฟล์ {input_mode}.csv")

    elif input_mode == "อัปโหลด CSV":
        uploaded = st.file_uploader("อัปโหลดไฟล์ CSV (คอลัมน์แรก = ชื่อหุ้น)", type=["csv"])
        if uploaded:
            try:
                uploaded_df = pd.read_csv(uploaded)
                symbols = uploaded_df.iloc[:, 0].dropna().str.strip().str.upper().tolist()
                st.success(f"โหลดได้ {len(symbols)} ตัว")
            except Exception as e:
                st.error(f"อ่านไฟล์ไม่ได้: {e}")

    st.divider()

    scan_days = st.slider(
        "ย้อนหลังกี่วัน (หา ATL)",
        min_value=30,
        max_value=180,
        value=90,
        step=10,
        help="Default 90 วัน ตามระบบ ViVi"
    )

    downtrend_months = st.slider(
        "ขาลงก่อน ตูด 1 (เดือน)",
        min_value=1,
        max_value=12,
        value=3,
        step=1,
        help="ย้อนซ้ายจาก ตูด 1 ตรวจว่าอยู่ใต้ EMA200 มาแล้วกี่เดือน (default 3)"
    )

    st.divider()

    st.subheader("กลุ่มจ่อ Breakout")
    st.caption("เลือกว่าจะดูหุ้นที่พร้อมแค่ไหน")
    readiness_min = st.selectbox(
        "แสดงตั้งแต่ระดับ",
        options=[1, 2, 3, 4],
        index=0,
        format_func=lambda x: {
            1: "1 — รอสัญญาณ (ทุกตัว)",
            2: "2 — เริ่มส่งสัญญาณ",
            3: "3 — สัญญาณชัด",
            4: "4 — จวนจะระเบิด 🔥",
        }[x]
    )

    st.divider()

    st.subheader("กลุ่ม Breakout แล้ว")
    st.caption("เลือกว่า Break มานานแค่ไหน")
    break_lv_show = st.multiselect(
        "เพิ่งทะลุมาไม่เกิน",
        options=["LV4", "LV3", "LV2", "LV1"],
        default=["LV4", "LV3", "LV2", "LV1"],
        format_func=lambda x: {
            "LV4": "LV4 — 1-2 วัน (ร้อนแรงที่สุด)",
            "LV3": "LV3 — 3-5 วัน",
            "LV2": "LV2 — 6-10 วัน",
            "LV1": "LV1 — 10 วันขึ้นไป",
        }[x]
    )

    st.divider()
    run_btn = st.button("🔍 สแกนเลย!", use_container_width=True, type="primary")


# ── Helper Functions ──────────────────────────────────────────────────────────
def render_table(rows):
    df_show = pd.DataFrame(rows)
    html = df_show.to_html(escape=False, index=False)
    html = html.replace("<table", "<table class='sticky-table'")
    sticky_html = """
    <div style="overflow-x:auto; max-height:600px; overflow-y:auto;">
        <style>
            .sticky-table { border-collapse: collapse; width: 100%; }
            .sticky-table th {
                position: sticky;
                top: 0;
                background: #1e1e2e;
                color: #fff;
                z-index: 1;
                padding: 8px 12px;
                border-bottom: 2px solid #444;
                white-space: nowrap;
                font-size: 13px;
            }
            .sticky-table td {
                padding: 8px 12px;
                border-bottom: 1px solid #333;
                font-size: 13px;
                white-space: nowrap;
            }
            .sticky-table tr:hover td { background: rgba(255,255,255,0.05); }
        </style>
    """ + html + """
    </div>
    """
    st.write(sticky_html, unsafe_allow_html=True)


def priority_badge(pg):
    m = {
        4: ("#fff3cd", "#856404", "จวนจะระเบิด 🔥🔥🔥🔥"),
        3: ("#fde8d8", "#7d3200", "สัญญาณชัด 🔥🔥🔥"),
        2: ("#e8f4fd", "#0c4a7c", "เริ่มส่งสัญญาณ 🔥🔥"),
        1: ("#f0f0f0", "#444441", "รอสัญญาณ 🔥"),
        "break_lv4": ("#d1f7c4", "#1a5c02", "Break 1-2 วัน ✅✅✅✅"),
        "break_lv3": ("#d1f7c4", "#1a5c02", "Break 3-5 วัน ✅✅✅"),
        "break_lv2": ("#d1f7c4", "#1a5c02", "Break 6-10 วัน ✅✅"),
        "break_lv1": ("#e8f0e8", "#3b6d11", "Break 10+ วัน ✅"),
    }
    bg, fg, label = m.get(pg, ("#f0f0f0", "#444", str(pg)))
    return f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:12px;font-size:12px;font-weight:500;white-space:nowrap">{label}</span>'


def build_row_waiting(r):
    sym = r.get("symbol", "")
    gen = r.get("generation", 1)
    pg = r.get("priority_group")
    latest = r.get("latest_close", "-")
    tood1 = r.get("tood1_price")
    hua = r.get("hua_price")
    tood2c = r.get("tood2_candidate_price")
    pct = r.get("pct_from_hua")
    rdiff = r.get("pending_rsi_diff")

    return {
        "หุ้น": f"{sym}" + (f" <small style='color:gray'>Gen{gen}</small>" if gen > 1 else ""),
        "ระดับความพร้อม": priority_badge(pg),
        "ราคาล่าสุด": latest,
        "ตูด 1": f"{tood1:.2f}" if tood1 else "-",
        "หัว": f"{hua:.2f}" if hua else "-",
        "ว่าที่ตูด 2": f"{tood2c:.2f}" if tood2c else "-",
        "ห่างหัว %": f"{pct:.1f}%" if pct is not None else "-",
        "RSI Diff": f"{rdiff:.1f}" if rdiff is not None else "-",
    }


def build_row_confirmed(r):
    sym = r.get("symbol", "")
    gen = r.get("generation", 1)
    pg = r.get("priority_group")
    latest = r.get("latest_close", "-")
    tood1 = r.get("tood1_price")
    hua = r.get("hua_price")
    tood2 = r.get("tood2_price")
    days = r.get("days_since_break")

    return {
        "หุ้น": f"{sym}" + (f" <small style='color:gray'>Gen{gen}</small>" if gen > 1 else ""),
        "ระดับความพร้อม": priority_badge(pg),
        "ราคาล่าสุด": latest,
        "ตูด 1": f"{tood1:.2f}" if tood1 else "-",
        "หัว": f"{hua:.2f}" if hua else "-",
        "ตูด 2": f"{tood2:.2f}" if tood2 else "-",
        "Break มาแล้ว": f"{days} วัน" if days is not None else "-",
    }


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("📊 ตูด หัว ตูด+ต้นรอบ Scanner")
st.caption("ระบบ ViVi Investor — VITALi | สแกนหาหุ้น Beginning of Trend ตาม Dow Theory + RSI Diff 8")
st.divider()

# กด "สแกนเลย!" แล้วเก็บผลไว้ใน session_state
# (สำคัญ: ถ้าไม่เก็บไว้ พอกดปุ่มดาวน์โหลด Streamlit จะ rerun แล้ว run_btn
#  กลับเป็น False ทันที ทำให้ผลสแกนหายและหน้าจอรีเซ็ตกลับไปหน้าเริ่มต้น)
if run_btn:
    if not symbols:
        st.warning("กรุณาเลือกหรือใส่รายชื่อหุ้นก่อนครับ")
        st.stop()

    progress_bar = st.progress(0)
    status_text = st.empty()
    results = []

    from scanner import fetch_data, detect_nested
    total = len(symbols)

    for i, sym in enumerate(symbols):
        status_text.text(f"กำลังสแกน {sym} ({i+1}/{total})")
        progress_bar.progress((i + 1) / total)
        try:
            df = fetch_data(sym, lookback_days=scan_days + 365)  # เผื่อ downtrend window
            if df.empty or len(df) < 30:
                continue
            state = detect_nested(
                df,
                scan_days=scan_days,
                downtrend_months=downtrend_months,
                min_downtrend_days=30,
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

    # Sort
    vol_order = {"LV4": 0, "LV3": 1, "LV2": 2, "LV1": 3, None: 4}
    group_order = {4: 0, 3: 1, 2: 2, 1: 3,
                   "break_lv4": 4, "break_lv3": 5,
                   "break_lv2": 6, "break_lv1": 7}

    def sort_key(r):
        pg = group_order.get(r.get("priority_group"), 99)
        vl = vol_order.get(r.get("volume_lv"), 4)
        pct = r.get("pct_from_hua") or 999
        return (pg, vl, pct)

    results.sort(key=sort_key)

    status_text.text(f"สแกนเสร็จแล้ว! พบ {len(results)} ตัว")
    progress_bar.progress(1.0)

    st.session_state["scan_results"] = results
    st.session_state["scan_symbols_count"] = len(symbols)

# แสดงผลจาก session_state เสมอ (ยืนหน้าเดิมได้แม้กดปุ่มดาวน์โหลดแล้ว rerun)
# หมายเหตุ: readiness_min / break_lv_show อ่านจาก sidebar สด ๆ ทุกรอบอยู่แล้ว
# ปรับ filter หลังสแกนเสร็จได้เลยโดยไม่ต้องกดสแกนใหม่
if "scan_results" in st.session_state:
    results = st.session_state["scan_results"]

    if not results:
        st.info("ไม่พบหุ้นที่ผ่านเงื่อนไขในขณะนี้")
    else:
        waiting = [r for r in results
                   if r.get("state") == "จ่อ_break"
                   and (r.get("priority_group") or 0) >= readiness_min]

        confirmed = [r for r in results
                     if r.get("state") == "confirmed"
                     and r.get("priority_group", "").replace("break_", "").upper() in break_lv_show]

        tab1, tab2 = st.tabs([
            f"🟡 จ่อ Breakout ({len(waiting)} ตัว)",
            f"🟢 Breakout แล้ว ({len(confirmed)} ตัว)",
        ])

        with tab1:
            if waiting:
                rows = [build_row_waiting(r) for r in waiting]
                render_table(rows)
                st.caption("เรียงลำดับ: ระดับความพร้อม → Volume → % ห่างหัว")
                st.download_button(
                    "⬇️ ดาวน์โหลด List หุ้นจ่อ Breakout (TradingView)",
                    data=build_tradingview_list(waiting),
                    file_name="watchlist_jor_breakout.txt",
                    mime="text/plain",
                    key="dl_waiting",
                )
            else:
                st.info("ไม่มีหุ้นในกลุ่มจ่อ Breakout ที่ตรงเงื่อนไข")

        with tab2:
            if confirmed:
                rows = [build_row_confirmed(r) for r in confirmed]
                render_table(rows)
                st.caption("เรียงลำดับ: วันที่ Break (น้อย = Priority สูง) → Volume")
                st.download_button(
                    "⬇️ ดาวน์โหลด List (TradingView)",
                    data=build_tradingview_list(confirmed),
                    file_name="watchlist_breakout_laew.txt",
                    mime="text/plain",
                    key="dl_confirmed",
                )
            else:
                st.info("ไม่มีหุ้น Breakout แล้วในเงื่อนไขที่เลือก")

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("สแกนทั้งหมด", f"{st.session_state['scan_symbols_count']} ตัว")
        c2.metric("ผ่านเงื่อนไข", f"{len(results)} ตัว")
        c3.metric("🟡 จ่อ Breakout", f"{len(waiting)} ตัว")
        c4.metric("🟢 Breakout แล้ว", f"{len(confirmed)} ตัว")

else:
    st.info("👈 เลือกหุ้นใน Sidebar แล้วกด สแกนเลย!")
