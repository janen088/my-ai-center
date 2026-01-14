import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 系统配置与 CSS (UI 层) =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="▪️", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* --- 全局重置 --- */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    
    /* --- 标题暴力压制 (H1-H6) --- */
    .stMarkdown h1 { font-size: 16px !important; font-weight: 700 !important; margin: 10px 0 !important; }
    .stMarkdown h2 { font-size: 15px !important; font-weight: 600 !important; margin: 8px 0 !important; }
    .stMarkdown h3, .stMarkdown h4, .stMarkdown h5 { font-size: 14px !important; font-weight: 600 !important; margin: 6px 0 !important; }
    
    /* --- 界面去噪 --- */
    header {visibility: hidden;} 
    footer {visibility: hidden;}
    
    /* --- 侧边栏优化 --- */
    section[data-testid="stSidebar"] { 
        background-color: #FAFAFA; 
        border-right: 1px solid #E0E0E0; 
    }
    
    /* --- 按钮风格 (黑白灰) --- */
    div.stButton > button { 
        background-color: #FFF; border: 1px solid #D1D1D1; color: #333; 
        border-radius: 4px; font-size: 13px; padding: 4px 10px; 
    }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* --- 聊天气泡 (透明化) --- */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { 
        background-color: #F0F0F0 !important; color: #000 !important; 
    }
    
    /* --- 状态栏与输入框 --- */
    .stStatusWidget { background-color: #fff !important; border: 1px solid #eee !important; }
    .stChatInputContainer { border-radius: 6px !important; border: 1px solid #E0E0E0 !important; }
    
    /* --- 右侧控制栏容器 --- */
    div[data-testid="column"] { padding: 0px 10px; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 后端服务 (Service 层) =================

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")
if not api_key: st.stop()
genai.configure(api_key=api_key)

# === 核心修改：老实人模式 ===
@st.cache_data(ttl=3600)
def get_available_models():
    try:
        model_list = []
        # 直接问 Google：你有什么？
        for m in genai.list_models():
            # 条件1: 支持生成内容
            # 条件2: 名字里带 gemini
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                # 去掉前缀，只留纯名字
                clean_name = m.name.replace("models/", "")
                model_list.append(clean_name)
        
        # 纯字母倒序排列 (通常 2.0 > 1.5，所以数字大的会在前面)
        return sorted(model_list, reverse=True)
    except Exception as e:
        # 万一断网了，给个保底
        return ["gemini-1.5-pro", "gemini-1.5-flash"]

def load_data(filename):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            c = repo.get_contents(filename)
            return json.loads(c.decoded_content.decode()), c.sha
        except: return {}, None
    except: return {}, None

def save_data(filename, data, sha, message="Update"):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        c_str = json.dumps(data, indent=2, ensure_ascii=False)
        if sha: repo.update_file(filename, message, c_str, sha)
        else: repo.create_file(filename, "Init", c_str)
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

# ================= 3. 业务逻辑 (Controller 层) =================

available_models = get_available_models()

# --- 左侧边栏 (导航) ---
with st.sidebar:
    st.markdown("**AI Studio**")
    app_mode = st.radio("Mode", ["☁️ Project", "⚡ Flash"], label_visibility="collapsed")
    st.divider()

# >>>>>>>>>> 场景 A: 闪电模式 (无右侧栏) <<<<<<<<<<
if app_mode == "⚡ Flash":
    st.markdown("#### ⚡ Flash Chat")
    model_name = st.selectbox("Model", available_models, label_visibility="collapsed")
    
    if "flash_msgs" not in st.session_state: st.session_state.flash_msgs = []
    if st.button("Clear"): st.session_state.flash_msgs = []; st.rerun()
    st.divider()

    for msg in st.session_state.flash_msgs:
        avatar = "▪️" if msg["role"] == "user" else "⚡"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                with st.expander("Copy"): st.code(msg["content"], language=None)

    if prompt := st.chat_input("Ask..."):
        with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
        st.session_state.flash_msgs.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant", avatar="⚡"):
            ph = st.empty()
            with st.status("Thinking...", expanded=True) as status:
                try:
                    model = genai.GenerativeModel(model_name)
                    hist = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.flash_msgs[:-1]]
                    chat = model.start_chat(history=hist)
                    full = ""
                    for chunk in chat.send_message(prompt, stream=True):
                        if chunk.text: full += chunk.text; ph.markdown(full + "▌")
                    ph.markdown(full)
                    status.update(label="Done", state="complete", expanded=False)
                    st.session_state.flash_msgs.append({"role": "assistant", "content": full})
                except Exception as e:
                    status.update(label="Error", state="error"); st.error(f"{e}")

# >>>>>>>>>> 场景 B: 项目模式 (双栏布局) <<<<<<<<<<
else:
    if "curr_id" not in st.session_state: st.session_state.curr_id = None
    roles, roles_sha = load_data("roles.json")
    chats, chats_sha = load_data("chats.json")

    # 左侧栏：项目列表 & 角色管理
    with st.sidebar:
        if st.button("＋ New Project", type="primary", use_container_width=True):
            st.session_state.curr_id = None; st.rerun()
        
        if chats:
            st.caption("History")
            for cid in list(chats.keys())[::-1]:
                title = chats[cid].get('title', 'Untitled')
                btype = "primary" if st.session_state.curr_id == cid else "secondary"
                if st.button(title, key=cid, use_container_width=True, type=btype):
                    st.session_state.curr_id = cid; st.rerun()
        
        st.divider()
        with st.expander("Manage Roles"):
            rn = st.text_input("Role Name"); rp = st.text_area("Prompt")
            if st.button("Save Role"):
                if rn and rp: roles[rn]=rp; save_data("roles.json", roles, roles_sha); st.rerun()

    # 主界面逻辑
    if st.session_state.curr_id is None:
        st.markdown("#### New Project")
        if not roles: st.info("Create a role in sidebar first.")
        else:
            with st.container(border=True):
                c1, c2 = st.columns(2)
                with c1: sel_r = st.selectbox("Role", list(roles.keys()))
                with c2: sel_m = st.selectbox("Model", available_models)
                if st.button("Start Chat", type="primary"):
                    nid = str(uuid.uuid4())
                    chats[nid] = {"title": "New Chat", "role": sel_r, "model": sel_m, "messages": []}
                    save_data("chats.json", chats, chats_sha)
                    st.session_state.curr_id = nid; st.rerun()
    else:
        cid = st.session_state.curr_id
        if cid in chats:
            curr = chats[cid]
            msgs = curr.get("messages", [])
            
            # === 布局核心：3:1 分栏 ===
            col_chat, col_ctrl = st.columns([3, 1])
            
            # --- 右侧控制台 ---
            with col_ctrl:
                st.markdown("**Control Panel**")
                
                # 重命名
                new_t = st.text_input("Title", value=curr.get('title',''), label_visibility="collapsed")
                if st.button("Update Title", use_container_width=True):
                    if new_t != curr.get('title'):
                        curr['title'] = new_t; chats[cid] = curr
                        save_data("chats.json", chats, chats_sha); st.rerun()
                
                # 删除
                if st.button("🗑️ Delete Chat", use_container_width=True):
                    del chats[cid]; save_data("chats.json", chats, chats_sha)
                    st.session_state.curr_id = None; st.rerun()
                
                st.divider()
                st.caption(f"Role: {curr.get('role')}")
                st.caption(f"Model: {curr.get('model')}")
                
                # 时光机
                st.markdown("**History Focus**")
                total = len(msgs) // 2
                focus_idx = None
                if total > 0:
                    view_mode = st.radio("View", ["Full", "Focus"], horizontal=True, label_visibility="collapsed")
                    if view_mode == "Focus":
                        focus_idx = st.slider("Turn", 1, total, total)
                        try:
                            q = msgs[(focus_idx-1)*2]["content"]
                            st.info(f"Q: {q[:30]}...")
                        except: pass

            # --- 左侧聊天区 ---
            with col_chat:
                if focus_idx:
                    start = (focus_idx - 1) * 2
                    show_msgs = msgs[start : start+2]
                    st.warning(f"👀 Viewing Turn {focus_idx} / {total}")
                else:
                    show_msgs = msgs

                for msg in show_msgs:
                    avatar = "▪️" if msg["role"] == "user" else "▫️"
                    with st.chat_message(msg["role"], avatar=avatar):
                        st.markdown(msg["content"])
                        if msg["role"] == "assistant":
                            with st.expander("Copy"): st.code(msg["content"], language=None)

                if prompt := st.chat_input("Type a message..."):
                    if focus_idx: st.toast("Switched to Full View for new message")
                    
                    with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
                    msgs.append({"role": "user", "content": prompt})
                    if len(msgs)==1: curr["title"] = prompt[:15]
                    
                    with st.chat_message("assistant", avatar="▫️"):
                        ph = st.empty()
                        t0 = time.time()
                        with st.status("Thinking...", expanded=True) as status:
                            try:
                                model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                                hist = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]]
                                chat = model.start_chat(history=hist)
                                full = ""
                                for chunk in chat.send_message(prompt, stream=True):
                                    if chunk.text: full += chunk.text; ph.markdown(full + "▌")
                                ph.markdown(full)
                                
                                status.update(label="Saving...", state="running")
                                msgs.append({"role": "assistant", "content": full})
                                curr["messages"] = msgs; chats[cid] = curr
                                
                                if save_data("chats.json", chats, chats_sha, message=f"Chat {cid}"):
                                    status.update(label=f"Done ({time.time()-t0:.2f}s)", state="complete", expanded=False)
                                else: status.update(label="Save Failed", state="error")
                            except Exception as e:
                                status.update(label="Error", state="error"); st.error(f"{e}")
                    time.sleep(0.5); st.rerun()
