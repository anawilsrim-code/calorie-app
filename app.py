import os
import streamlit as st
import pandas as pd
from datetime import date

import analyzer as an

st.set_page_config(page_title="Thai Meal Calorie Analyzer", page_icon="🍚", layout="wide")

# ---------- state ----------
if "diary" not in st.session_state:
    st.session_state.diary = []      # list of dict rows (already scaled)import hashlib
import os
import time
import streamlit as st
import pandas as pd
from datetime import date

import analyzer as an

st.set_page_config(page_title="Thai Meal Calorie Analyzer", page_icon="🍚", layout="wide")

# ---------- state ----------
if "diary" not in st.session_state:
    st.session_state.diary = []      # list of dict rows (already scaled)
if "current" not in st.session_state:
    st.session_state.current = None  # items from the latest analysis

db = an.load_db()

# ---------- sidebar ----------
with st.sidebar:
    st.header("ตั้งค่า")
    try:
        default_key = st.secrets["GEMINI_API_KEY"]
    except Exception:  # no secrets.toml on a local machine
        default_key = os.getenv("GEMINI_API_KEY", "")
    # The server-side key is never shown in the page (visitors could reveal it).
    typed_key = st.text_input("Gemini API Key", type="password",
                              placeholder="ว่างไว้ได้ ถ้าตั้งคีย์ไว้ที่เซิร์ฟเวอร์แล้ว" if default_key else "")
    api_key = typed_key or default_key
    goal = st.number_input("เป้าหมายแคลอรีต่อวัน (kcal)", 1000, 4000, 2000, 50)
    meals_left = st.number_input("เหลืออีกกี่มื้อวันนี้", 0, 5, 2)
    st.divider()
    st.caption("ค่าที่ได้เป็นการประมาณการเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์ "
               "หากมีโรคประจำตัวหรือต้องควบคุมอาหารเป็นพิเศษ ควรปรึกษาแพทย์หรือนักกำหนดอาหาร")

st.title("วิเคราะห์แคลอรีจากรูปอาหาร")
st.write("ถ่ายรูปอาหาร ระบบจะระบุเมนู ประเมินปริมาณ และบันทึกลงไดอารี่วันนี้")

tab_scan, tab_diary = st.tabs(["วิเคราะห์อาหาร", "ไดอารี่วันนี้"])

# ---------- tab 1: analyze ----------
with tab_scan:
    left, right = st.columns([1, 1.2], gap="large")

    with left:
        src = st.radio("ที่มาของรูป", ["อัปโหลดไฟล์", "ถ่ายจากกล้อง"], horizontal=True)
        img = st.file_uploader("เลือกรูปอาหาร", type=["jpg", "jpeg", "png", "webp"]) \
            if src == "อัปโหลดไฟล์" else st.camera_input("ถ่ายรูปอาหาร")
        if img:
            st.image(img, use_container_width=True)
        go = st.button("วิเคราะห์รูปนี้", type="primary", disabled=img is None)

    if go and img:
        if not api_key:
            st.error("ใส่ Gemini API Key ที่แถบด้านซ้ายก่อน")
        else:
            try:
                data = img.getvalue()
                key = hashlib.md5(data).hexdigest()
                cache = st.session_state.setdefault("cache", {})
                t0 = time.time()
                if key in cache:  # same photo analysed before: instant, no API call
                    st.session_state.current = cache[key]
                else:
                    with st.spinner("กำลังวิเคราะห์... (ปกติ 5–15 วินาที)"):
                        client = an.get_client(api_key)
                        st.session_state.current = an.analyze_customized(
                            client, data, img.type or "image/jpeg", db)
                    cache[key] = st.session_state.current
                st.session_state.last_seconds = time.time() - t0
            except Exception as e:
                st.session_state.current = None
                st.error(f"วิเคราะห์ไม่สำเร็จ: {e}. ลองถ่ายรูปใหม่ให้เห็นอาหารชัดขึ้น หรือตรวจสอบ API Key")

    with right:
        items = st.session_state.current
        if items is None:
            st.info("อัปโหลดรูปแล้วกด \"วิเคราะห์รูปนี้\" ผลจะแสดงตรงนี้")
        elif not items:
            st.warning("ไม่พบอาหารในรูปนี้ ลองถ่ายใหม่ให้เห็นอาหารชัดขึ้น")
        else:
            st.subheader("ผลการวิเคราะห์ (แก้ไขได้)")
            if "last_seconds" in st.session_state:
                st.caption(f"ใช้เวลาวิเคราะห์ {st.session_state.last_seconds:.1f} วินาที")
            edited = []
            for i, it in enumerate(items):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    options = db["menu"].tolist() + ["อื่นๆ (กรอกเอง)"]
                    idx = options.index(it["menu"]) if it["menu"] in options else len(options) - 1
                    menu = c1.selectbox("เมนู", options, index=idx, key=f"menu{i}")
                    portion = c2.select_slider("ปริมาณ (เท่าของ 1 เสิร์ฟ)",
                                               [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                                               value=min([0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                                                         key=lambda x: abs(x - it["portion"])),
                                               key=f"por{i}")
                    if menu in set(db["menu"]):
                        row = db[db["menu"] == menu].iloc[0]
                        base = {k: float(row[k]) for k in ("kcal", "protein_g", "carb_g", "fat_g")}
                    else:
                        st.caption(f"AI เห็น: {it.get('note') or it['menu']} (ไม่มีในฐานข้อมูล กรอกค่าเอง)")
                        base = {"kcal": st.number_input("kcal ต่อ 1 เสิร์ฟ", 0, 3000, 0, key=f"k{i}"),
                                "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
                    e = {"menu": menu, "portion": portion, "confidence": it["confidence"], **base}
                    s = an.scaled(e)
                    st.caption(f"ความมั่นใจของ AI {it['confidence']:.0%} · "
                               f"{s['kcal']:.0f} kcal · โปรตีน {s['protein_g']:.0f} g · "
                               f"คาร์บ {s['carb_g']:.0f} g · ไขมัน {s['fat_g']:.0f} g")
                    edited.append({"menu": menu, "portion": portion, **s})

            total = sum(r["kcal"] for r in edited)
            st.metric("รวมมื้อนี้", f"{total:.0f} kcal")
            meal = st.selectbox("มื้อ", ["เช้า", "กลางวัน", "เย็น", "ของว่าง"])
            if st.button("บันทึกลงไดอารี่"):
                for r in edited:
                    st.session_state.diary.append({"วันที่": date.today().isoformat(), "มื้อ": meal, **r})
                st.session_state.current = None
                st.success("บันทึกแล้ว ดูที่แท็บ \"ไดอารี่วันนี้\"")
                st.rerun()

# ---------- tab 2: diary ----------
with tab_diary:
    if not st.session_state.diary:
        st.info("ยังไม่มีรายการ วิเคราะห์รูปอาหารแล้วกด \"บันทึกลงไดอารี่\"")
    else:
        df = pd.DataFrame(st.session_state.diary)
        df = df.rename(columns={"menu": "เมนู", "portion": "ปริมาณ(เท่า)", "kcal": "kcal",
                                "protein_g": "โปรตีน(g)", "carb_g": "คาร์บ(g)", "fat_g": "ไขมัน(g)"})
        st.dataframe(df, use_container_width=True, hide_index=True)

        tot = {k: df[c].sum() for k, c in
               [("kcal", "kcal"), ("protein_g", "โปรตีน(g)"), ("carb_g", "คาร์บ(g)"), ("fat_g", "ไขมัน(g)")]}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("พลังงานรวม", f"{tot['kcal']:.0f} kcal", f"{tot['kcal'] - goal:+.0f} จากเป้าหมาย", delta_color="inverse")
        m2.metric("โปรตีน", f"{tot['protein_g']:.0f} g")
        m3.metric("คาร์โบไฮเดรต", f"{tot['carb_g']:.0f} g")
        m4.metric("ไขมัน", f"{tot['fat_g']:.0f} g")
        st.progress(min(tot["kcal"] / goal, 1.0), text=f"{tot['kcal'] / goal:.0%} ของเป้าหมายวันนี้")
        if tot["kcal"] > goal:
            st.warning("วันนี้กินเกินเป้าหมายแคลอรีที่ตั้งไว้แล้ว")

        st.bar_chart(df.groupby("มื้อ")["kcal"].sum())

        c1, c2 = st.columns(2)
        if c1.button("แนะนำมื้อถัดไป"):
            if not api_key:
                st.error("ใส่ Gemini API Key ที่แถบด้านซ้ายก่อน")
            else:
                with st.spinner("กำลังคิดเมนู..."):
                    st.markdown(an.suggest_next_meal(an.get_client(api_key), tot, goal, meals_left))
        if c2.button("ล้างไดอารี่"):
            st.session_state.diary = []
            st.rerun()
        st.download_button("ดาวน์โหลด CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           "food_diary.csv", "text/csv")

if "current" not in st.session_state:
    st.session_state.current = None  # items from the latest analysis

db = an.load_db()

# ---------- sidebar ----------
with st.sidebar:
    st.header("ตั้งค่า")
    try:
        default_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        default_key = os.getenv("GEMINI_API_KEY", "")
    api_key = st.text_input("Gemini API Key", type="password", value=default_key)
    goal = st.number_input("เป้าหมายแคลอรีต่อวัน (kcal)", 1000, 4000, 2000, 50)
    meals_left = st.number_input("เหลืออีกกี่มื้อวันนี้", 0, 5, 2)
    st.divider()
    st.caption("ค่าที่ได้เป็นการประมาณการเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์ "
               "หากมีโรคประจำตัวหรือต้องควบคุมอาหารเป็นพิเศษ ควรปรึกษาแพทย์หรือนักกำหนดอาหาร")

st.title("วิเคราะห์แคลอรีจากรูปอาหาร")
st.write("ถ่ายรูปอาหาร ระบบจะระบุเมนู ประเมินปริมาณ และบันทึกลงไดอารี่วันนี้")

tab_scan, tab_diary = st.tabs(["วิเคราะห์อาหาร", "ไดอารี่วันนี้"])

# ---------- tab 1: analyze ----------
with tab_scan:
    left, right = st.columns([1, 1.2], gap="large")

    with left:
        src = st.radio("ที่มาของรูป", ["อัปโหลดไฟล์", "ถ่ายจากกล้อง"], horizontal=True)
        img = st.file_uploader("เลือกรูปอาหาร", type=["jpg", "jpeg", "png", "webp"]) \
            if src == "อัปโหลดไฟล์" else st.camera_input("ถ่ายรูปอาหาร")
        if img:
            st.image(img, use_container_width=True)
        go = st.button("วิเคราะห์รูปนี้", type="primary", disabled=img is None)

    if go and img:
        if not api_key:
            st.error("ใส่ Gemini API Key ที่แถบด้านซ้ายก่อน")
        else:
            try:
                with st.spinner("กำลังวิเคราะห์..."):
                    client = an.get_client(api_key)
                    st.session_state.current = an.analyze_customized(
                        client, img.getvalue(), img.type or "image/jpeg", db)
            except Exception as e:
                st.session_state.current = None
                st.error(f"วิเคราะห์ไม่สำเร็จ: {e}. ลองถ่ายรูปใหม่ให้เห็นอาหารชัดขึ้น หรือตรวจสอบ API Key")

    with right:
        items = st.session_state.current
        if items is None:
            st.info("อัปโหลดรูปแล้วกด \"วิเคราะห์รูปนี้\" ผลจะแสดงตรงนี้")
        elif not items:
            st.warning("ไม่พบอาหารในรูปนี้ ลองถ่ายใหม่ให้เห็นอาหารชัดขึ้น")
        else:
            st.subheader("ผลการวิเคราะห์ (แก้ไขได้)")
            edited = []
            for i, it in enumerate(items):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    options = db["menu"].tolist() + ["อื่นๆ (กรอกเอง)"]
                    idx = options.index(it["menu"]) if it["menu"] in options else len(options) - 1
                    menu = c1.selectbox("เมนู", options, index=idx, key=f"menu{i}")
                    portion = c2.select_slider("ปริมาณ (เท่าของ 1 เสิร์ฟ)",
                                               [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                                               value=min([0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
                                                         key=lambda x: abs(x - it["portion"])),
                                               key=f"por{i}")
                    if menu in set(db["menu"]):
                        row = db[db["menu"] == menu].iloc[0]
                        base = {k: float(row[k]) for k in ("kcal", "protein_g", "carb_g", "fat_g")}
                    else:
                        st.caption(f"AI เห็น: {it.get('note') or it['menu']} (ไม่มีในฐานข้อมูล กรอกค่าเอง)")
                        base = {"kcal": st.number_input("kcal ต่อ 1 เสิร์ฟ", 0, 3000, 0, key=f"k{i}"),
                                "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
                    e = {"menu": menu, "portion": portion, "confidence": it["confidence"], **base}
                    s = an.scaled(e)
                    st.caption(f"ความมั่นใจของ AI {it['confidence']:.0%} · "
                               f"{s['kcal']:.0f} kcal · โปรตีน {s['protein_g']:.0f} g · "
                               f"คาร์บ {s['carb_g']:.0f} g · ไขมัน {s['fat_g']:.0f} g")
                    edited.append({"menu": menu, "portion": portion, **s})

            total = sum(r["kcal"] for r in edited)
            st.metric("รวมมื้อนี้", f"{total:.0f} kcal")
            meal = st.selectbox("มื้อ", ["เช้า", "กลางวัน", "เย็น", "ของว่าง"])
            if st.button("บันทึกลงไดอารี่"):
                for r in edited:
                    st.session_state.diary.append({"วันที่": date.today().isoformat(), "มื้อ": meal, **r})
                st.session_state.current = None
                st.success("บันทึกแล้ว ดูที่แท็บ \"ไดอารี่วันนี้\"")
                st.rerun()

# ---------- tab 2: diary ----------
with tab_diary:
    if not st.session_state.diary:
        st.info("ยังไม่มีรายการ วิเคราะห์รูปอาหารแล้วกด \"บันทึกลงไดอารี่\"")
    else:
        df = pd.DataFrame(st.session_state.diary)
        df = df.rename(columns={"menu": "เมนู", "portion": "ปริมาณ(เท่า)", "kcal": "kcal",
                                "protein_g": "โปรตีน(g)", "carb_g": "คาร์บ(g)", "fat_g": "ไขมัน(g)"})
        st.dataframe(df, use_container_width=True, hide_index=True)

        tot = {k: df[c].sum() for k, c in
               [("kcal", "kcal"), ("protein_g", "โปรตีน(g)"), ("carb_g", "คาร์บ(g)"), ("fat_g", "ไขมัน(g)")]}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("พลังงานรวม", f"{tot['kcal']:.0f} kcal", f"{tot['kcal'] - goal:+.0f} จากเป้าหมาย", delta_color="inverse")
        m2.metric("โปรตีน", f"{tot['protein_g']:.0f} g")
        m3.metric("คาร์โบไฮเดรต", f"{tot['carb_g']:.0f} g")
        m4.metric("ไขมัน", f"{tot['fat_g']:.0f} g")
        st.progress(min(tot["kcal"] / goal, 1.0), text=f"{tot['kcal'] / goal:.0%} ของเป้าหมายวันนี้")
        if tot["kcal"] > goal:
            st.warning("วันนี้กินเกินเป้าหมายแคลอรีที่ตั้งไว้แล้ว")

        st.bar_chart(df.groupby("มื้อ")["kcal"].sum())

        c1, c2 = st.columns(2)
        if c1.button("แนะนำมื้อถัดไป"):
            if not api_key:
                st.error("ใส่ Gemini API Key ที่แถบด้านซ้ายก่อน")
            else:
                with st.spinner("กำลังคิดเมนู..."):
                    st.markdown(an.suggest_next_meal(an.get_client(api_key), tot, goal, meals_left))
        if c2.button("ล้างไดอารี่"):
            st.session_state.diary = []
            st.rerun()
        st.download_button("ดาวน์โหลด CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           "food_diary.csv", "text/csv")
