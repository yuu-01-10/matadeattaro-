import streamlit as st
import pandas as pd
from datetime import datetime
from difflib import SequenceMatcher

import gspread
from google.oauth2.service_account import Credentials

# --------------------
# Googleスプレッドシート設定
# --------------------

SPREADSHEET_NAME = "また出会ったろー"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

COLUMNS = ["user_id", "password", "word", "meaning", "count", "created_at", "updated_at"]


# --------------------
# Google Sheets 接続
# --------------------

@st.cache_resource
def connect_sheet():
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    gc = gspread.authorize(credentials)
    sh = gc.open(SPREADSHEET_NAME)
    worksheet = sh.sheet1
    return worksheet


def load_all_data():
    worksheet = connect_sheet()
    records = worksheet.get_all_records()

    if not records:
        df = pd.DataFrame(columns=COLUMNS)
    else:
        df = pd.DataFrame(records)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["user_id"] = df["user_id"].fillna("").astype(str)
    df["password"] = df["password"].fillna("").astype(str)
    df["word"] = df["word"].fillna("").astype(str)
    df["meaning"] = df["meaning"].fillna("").astype(str)
    df["count"] = df["count"].fillna(1).astype(int)
    df["created_at"] = df["created_at"].fillna("").astype(str)
    df["updated_at"] = df["updated_at"].fillna("").astype(str)

    return df


def save_all_data(df):
    worksheet = connect_sheet()

    df = df[COLUMNS].copy()
    df["count"] = df["count"].fillna(1).astype(int)

    values = [COLUMNS] + df.astype(str).values.tolist()

    worksheet.clear()
    worksheet.update(values)


# --------------------
# 共通関数
# --------------------

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_user_df(all_df, user_id, password):
    user_df = all_df[
        (all_df["user_id"] == user_id) &
        (all_df["password"] == password)
    ].copy()

    return user_df


def get_suggestions(query, dataframe):
    suggestions = []

    if not query.strip() or dataframe.empty:
        return suggestions

    query_lower = query.lower()

    for i, row in dataframe.iterrows():
        word = str(row["word"])
        word_lower = word.lower()

        is_partial_match = query_lower in word_lower or word_lower in query_lower
        score = similarity(query_lower, word_lower)

        # サジェストを厳しめにする
        if is_partial_match or score >= 0.55:
            suggestions.append((i, word, score))

    suggestions = sorted(suggestions, key=lambda x: x[2], reverse=True)
    return suggestions[:5]


def get_sorted_df(dataframe, sort_mode):
    if sort_mode == "確認回数が多い順":
        return dataframe.sort_values(
            ["count", "word"],
            ascending=[False, True],
            key=lambda col: col.str.lower() if col.name == "word" else col
        )
    else:
        return dataframe.sort_values(
            "word",
            key=lambda col: col.str.lower()
        )


def open_word(index, edit=False):
    st.session_state["active_index"] = int(index)
    st.session_state["edit_open"] = edit


def update_row(all_df, index, word, meaning, count):
    all_df.loc[index, "word"] = word.strip()
    all_df.loc[index, "meaning"] = meaning.strip()
    all_df.loc[index, "count"] = int(count)
    all_df.loc[index, "updated_at"] = now_text()
    save_all_data(all_df)


def delete_row(all_df, index):
    all_df = all_df.drop(index).reset_index(drop=True)
    save_all_data(all_df)


def add_word(all_df, user_id, password, word, meaning):
    new_row = {
        "user_id": user_id,
        "password": password,
        "word": word.strip(),
        "meaning": meaning.strip(),
        "count": 1,
        "created_at": now_text(),
        "updated_at": now_text()
    }

    all_df = pd.concat([all_df, pd.DataFrame([new_row])], ignore_index=True)
    save_all_data(all_df)


def increment_count(all_df, index):
    all_df.loc[index, "count"] = int(all_df.loc[index, "count"]) + 1
    all_df.loc[index, "updated_at"] = now_text()
    save_all_data(all_df)


# --------------------
# UI関数
# --------------------

def show_edit_form(all_df, index):
    st.markdown("### 編集")

    edited_word = st.text_input(
        "単語",
        value=all_df.loc[index, "word"],
        key=f"edit_word_{index}"
    )

    edited_meaning = st.text_area(
        "意味",
        value=all_df.loc[index, "meaning"],
        key=f"edit_meaning_{index}"
    )

    edited_count = st.number_input(
        "確認回数",
        min_value=0,
        step=1,
        value=int(all_df.loc[index, "count"]),
        key=f"edit_count_{index}"
    )

    if st.button("編集内容を保存する", key=f"save_edit_{index}"):
        if edited_word.strip() and edited_meaning.strip():
            update_row(all_df, index, edited_word, edited_meaning, edited_count)
            st.session_state["edit_open"] = False
            st.success("編集内容を保存しました。")
            st.rerun()
        else:
            st.warning("単語と意味は空欄にできません。")

    delete_check = st.checkbox("この単語を削除する", key=f"delete_check_{index}")

    if delete_check:
        if st.button("本当に削除する", key=f"delete_{index}"):
            delete_row(all_df, index)
            st.session_state.pop("active_index", None)
            st.session_state["edit_open"] = False
            st.success("削除しました。")
            st.rerun()


def show_detail(all_df, index):
    st.subheader(all_df.loc[index, "word"])

    st.write("**意味：**")
    st.write(all_df.loc[index, "meaning"])

    st.write(f"**確認回数：** {int(all_df.loc[index, 'count'])} 回")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("カウント", key=f"count_{index}"):
            increment_count(all_df, index)
            st.success("確認回数を1増やしました。")
            st.rerun()

    with col2:
        if st.button("編集", key=f"toggle_edit_{index}"):
            current = st.session_state.get("edit_open", False)
            st.session_state["edit_open"] = not current
            st.rerun()

    if st.session_state.get("edit_open", False):
        show_edit_form(all_df, index)


# --------------------
# アプリ本体
# --------------------

st.title("また出会ったろー")
st.write("自分専用の英語辞書です。")

st.divider()

# --------------------
# ログイン
# --------------------

# 未ログインならログイン画面を出す
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.subheader("ログイン")

    login_user_id = st.text_input("ユーザーID")
    login_password = st.text_input("パスワード", type="password")

    if st.button("ログイン"):
        if login_user_id.strip() and login_password.strip():
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = login_user_id.strip()
            st.session_state["password"] = login_password.strip()
            st.rerun()
        else:
            st.warning("ユーザーIDとパスワードを入力してください。")

    st.stop()

# ログイン済みならここから先に進む
user_id = st.session_state["user_id"]
password = st.session_state["password"]

all_df = load_all_data()
user_df = get_user_df(all_df, user_id, password)

col_login1, col_login2 = st.columns([4, 1])

with col_login1:
    st.caption(f"{user_id} としてログイン中")

with col_login2:
    if st.button("ログアウト"):
        st.session_state.clear()
        st.rerun()

st.divider()

# --------------------
# 検索・登録
# --------------------

word_input = st.text_input("単語・熟語を入力してください").strip()

if word_input:
    user_df = get_user_df(all_df, user_id, password)

    suggestions = get_suggestions(word_input, user_df)
    matched = user_df[user_df["word"].str.lower() == word_input.lower()]

    search_changed = st.session_state.get("last_search_word") != word_input

    if search_changed:
        st.session_state["last_search_word"] = word_input

        if not matched.empty:
            index = matched.index[0]
            open_word(index, edit=False)

    if not matched.empty:
        st.info("登録済みの単語です。")

    else:
        st.info("完全一致する単語はありません。")

        if suggestions:
            st.subheader("入力中の候補")

            for i, word, score in suggestions:
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.write(f"**{word}**")
                    st.write(user_df.loc[i, "meaning"])
                    st.write(f"確認回数：{int(user_df.loc[i, 'count'])} 回")

                with col2:
                    if st.button("これを表示", key=f"suggest_show_{i}"):
                        open_word(i, edit=False)
                        st.rerun()

        st.divider()

        st.subheader("新規登録")

        meaning_input = st.text_area("意味を入力してください")

        if st.button("新規登録する"):
            if meaning_input.strip():
                add_word(all_df, user_id, password, word_input, meaning_input)
                st.success(f"{word_input} を登録しました。")
                st.rerun()
            else:
                st.warning("意味を入力してください。")


# --------------------
# 上部の単語詳細表示
# --------------------

if "active_index" in st.session_state:
    active_index = st.session_state["active_index"]

    if active_index in all_df.index:
        # 念のため、ログイン中のユーザーの単語だけ表示
        if (
            all_df.loc[active_index, "user_id"] == user_id and
            all_df.loc[active_index, "password"] == password
        ):
            show_detail(all_df, active_index)

st.divider()


# --------------------
# 一覧
# --------------------

st.subheader("登録済み単語一覧")

user_df = get_user_df(all_df, user_id, password)

if user_df.empty:
    st.write("まだ単語が登録されていません。")

else:
    sort_mode = st.radio(
        "並び替え",
        ["アルファベット順", "確認回数が多い順"],
        horizontal=True
    )

    sorted_user_df = get_sorted_df(user_df, sort_mode)

    for display_no, row in enumerate(sorted_user_df.itertuples(), start=1):
        original_index = row.Index

        if sort_mode == "確認回数が多い順" and display_no in [1, 2, 3]:
            if display_no == 1:
                medal = "🥇"
                bg = "#fff3b0"
                border = "#d4af37"
                size = "22px"
            elif display_no == 2:
                medal = "🥈"
                bg = "#eeeeee"
                border = "#c0c0c0"
                size = "20px"
            else:
                medal = "🥉"
                bg = "#f3d0a4"
                border = "#cd7f32"
                size = "20px"

            st.markdown(
                f"""
                <div style="
                    background-color:{bg};
                    padding:16px;
                    border-radius:12px;
                    margin-bottom:10px;
                    border:2px solid {border};
                    font-size:{size};
                ">
                    <b>{medal} {display_no}位　{row.word}</b><br>
                    <span>確認回数：{int(row.count)} 回</span><br>
                    <span>{row.meaning}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button("表示", key=f"show_top_{original_index}"):
                    open_word(original_index, edit=False)
                    st.rerun()

            with col2:
                if st.button("編集", key=f"edit_top_{original_index}"):
                    open_word(original_index, edit=True)
                    st.rerun()

            st.divider()

        else:
            col1, col2, col3, col4, col5, col6 = st.columns([0.5, 2.5, 4, 1, 1, 1])

            with col1:
                st.write(display_no)

            with col2:
                st.write(f"**{row.word}**")

            with col3:
                st.write(row.meaning)

            with col4:
                st.write(f"{int(row.count)} 回")

            with col5:
                if st.button("表示", key=f"show_list_{original_index}"):
                    open_word(original_index, edit=False)
                    st.rerun()

            with col6:
                if st.button("編集", key=f"edit_list_{original_index}"):
                    open_word(original_index, edit=True)
                    st.rerun()

            st.divider()