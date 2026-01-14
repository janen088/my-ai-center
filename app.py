import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 系统配置 & 核弹级 CSS =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="▪️", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* --- 全局字体基准 --- */
    html, body, [class*="css"] { 
        font-family: 'Inter', 'Roboto', sans-serif; 
        color: #1a1a1a; 
        font-size: 14px; 
    }

    /* --- 标题暴力压制 (针对所有层级，包括嵌套) --- */
    /* 使用通配符强制覆盖所有 Markdown 标题 */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, 
    .stMarkdown h4, .stMarkdown h5, .stMarkdown h6,
    .stMarkdown strong { 
        font-size: 15px !important; 
        font-weight: 600 !important; 
        margin: 8px 0 !important;
        line-height: 1.5 !important;
    }
    
    /* 特别处理 H1 稍微大一丢丢，但绝不许大过 16px */
    .stMarkdown h1 { font-size: 16px !important; border-bottom: 1px solid #eee; padding-bottom: 5px; }
    
    /* 列表和正文强制 14px */
    .stMarkdown p, .stMarkdown li { font-size: 14px !important; line-height: 1.6 !important; }

    /* --- 界面去噪 --- */
    header, footer {visibility: hidden;} 
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    
    /* --- 按钮优化 --- */
    div.stButton > button { background-color: #FFF; border: 1px solid #D1D1D1; color: #333; border-radius: 4px; font-size: 13px; }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* --- 侧边栏列表紧凑化 --- */
    div[data-testid="column"] { padding: 0px 2px; }
    
    /* --- 聊天气泡 --- */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { background-color: #F0F0F0 !important; color: #000 !important; }
    
    /* --- 右侧导航栏样式 --- */
    .nav-header { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 后端服务 =================

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")
if not api_key: st.stop()
genai.configure(api_key=api_key)

@st.cache_data(ttl=3600)
def get_available_models():
    try:
        # 你的要求：全部模型，不隐藏
        model_list = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                model_list.append(m.name.replace("models/", ""))
        return sorted(model_list, reverse=True)
    except: return ["gemini-1.5-pro", "gemini-1.5-flash"]

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
    except: return False

# ================= 3. 业务逻辑 =================

available_models = get_available_models()

# --- 左侧边栏 (导航 + 管理) ---
with st.sidebar:
    st.markdown("**AI Studio**")
    app_mode = st.radio("Mode", ["☁️ Project", "⚡ Flash"], label_visibility="collapsed")
    st.divider()

# >>>>>>>>>> 场景 A: 闪电模式 <<<<<<<<<<
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

# >>>>>>>>>> 场景 B: 项目模式 (双栏布局 + 左侧管理) <<<<<<<<<<
else:
    if "curr_id" not in st.session_state: st.session_state.curr_id = None
    roles, roles_sha = load_data("roles.json")
    chats, chats_sha = load_data("chats.json")

    # === 左侧栏：列表 (带直接管理功能) ===
    with st.sidebar:
        if st.button("＋ New Project", type="primary", use_container_width=True):
            st.session_state.curr_id = None; st.rerun()
        
        st.caption("History")
        if chats:
            for cid in list(chats.keys())[::-1]:
                c_data = chats[cid]
                title = c_data.get('title', 'Untitled')
                
                # 左右布局：左边进入，右边管理
                col1, col2 = st.columns([5, 1])
                with col1:
                    btype = "primary" if st.session_state.curr_id == cid else "secondary"
                    if st.button(title, key=f"open_{cid}", use_container_width=True, type=btype):
                        st.session_state.curr_id = cid; st.rerun()
                with col2:
                    # 弹出式菜单
                    with st.popover("⋮", use_container_width=True):
                        st.markdown("**Manage**")
                        nn = st.text_input("Name", value=title, key=f"n_{cid}")
                        if st.button("Save", key=f"s_{cid}"):
                            chats[cid]['title']=nn; save_data("chats.json", chats, chats_sha); st.rerun()
                        st.divider()
                        if st.button("Delete", key=f"d_{cid}", type="primary"):
                            del chats[cid]; save_data("chats.json", chats, chats_sha)
                            if st.session_state.curr_id == cid: st.session_state.curr_id = None
                            st.rerun()
        else:
            st.info("No chats.")
            
        st.divider()
        with st.expander("Manage Roles"):
            rn = st.text_input("Role Name"); rp = st.text_area("Prompt")
            if st.button("Save"):
                if rn and rp: roles[rn]=rp; save_data("roles.json", roles, roles_sha); st.rerun()

    # === 主界面 ===
    if st.session_state.curr_id is None:
        st.markdown("#### New Project")
        if not roles: st.warning("Create a role in sidebar.")
        else:
            with st.container(border=True):
                c1, c2 = st.columns(2)
                with c1: sr = st.selectbox("Role", list(roles.keys()))
                with c2: sm = st.selectbox("Model", available_models)
                if st.button("Start Chat", type="primary"):
                    nid = str(uuid.uuid4())
                    chats[nid] = {"title": "New Chat", "role": sr, "model": sm, "messages": []}
                    save_data("chats.json", chats, chats_sha)
                    st.session_state.curr_id = nid; st.rerun()
    else:
        cid = st.session_state.curr_id
        if cid in chats:
            curr = chats[cid]
            msgs = curr.get("messages", [])
            
            # === 核心布局：3:1 分栏 (右侧时光机回归) ===
            col_chat, col_nav = st.columns([3, 1])
            
            # --- 右侧：时光机 (Time Machine) ---
            with col_nav:
                st.markdown("<div class='nav-header'>Context Navigation</div>", unsafe_allow_html=True)
                
                # 信息展示
                st.caption(f"Role: **{curr.get('role')}**")
                st.caption(f"Model: {curr.get('model')}")
                st.divider()
                
                # 滑动导航逻辑
                total_turns = len(msgs) // 2
                focus_idx = None
                
                if total_turns > 0:
                    # 模式切换
                    view_mode = st.radio("View Mode", ["Full History", "Focus Turn"], horizontal=True)
                    
                    if view_mode == "Focus Turn":
                        # 滑块
                        focus_idx = st.slider("Select Turn", 1, total_turns, total_turns)
                        
                        # 预览
                        try:
                            q = msgs[(focus_idx-1)*2]["content"]
                            st.info(f"Q: {q[:50]}...")
                        except: pass
                    else:
                        st.caption(f"Showing all {total_turns} turns.")

            # --- 左侧：聊天区 ---
            with col_chat:
                # 顶部标题
                st.markdown(f"**{curr.get('title')}**")
                
                # 消息筛选
                if focus_idx:
                    start = (focus_idx - 1) * 2
                    show_msgs = msgs[start : start+2]
                    st.warning(f"👀 Viewing Turn {focus_idx} / {total_turns}")
                else:
                    show_msgs = msgs

                # 渲染消息
                for msg in show_msgs:
                    avatar = "▪️" if msg["role"] == "user" else "▫️"
                    with st.chat_message(msg["role"], avatar=avatar):
                        st.markdown(msg["content"])
                        if msg["role"] == "assistant":
                            with st.expander("Copy"): st.code(msg["content"], language=None)

                # 输入框
                if prompt := st.chat_input("Type..."):
                    if focus_idx: st.toast("Switched to Full View")
                    
                    with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
                    msgs.append({"role": "user", "content": prompt})
                    if len(msgs)==1: curr["title"] = prompt[:10]
                    
                    with st.chat_message("assistant", avatar="▫️"):
                        ph = st.empty()
                        with st.status("Thinking...", expanded=True) as status:
                            try:
                                model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                                # 发送完整历史 (不受 Focus 影响)
                                hist = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]]
                                chat = model.start_chat(history=hist)
                                full = ""
                                for chunk in chat.send_message(prompt, stream=True):
                                    if chunk.text: full+=chunk.text; ph.markdown(full + "▌")
                                ph.markdown(full)
                                
                                status.update(label="Saving...", state="running")
                                msgs.append({"role": "assistant", "content": full})
                                curr["messages"] = msgs; chats[cid] = curr
                                
                                if save_data("chats.json", chats, chats_sha, message=f"Chat {cid}"):
                                    status.update(label="Done", state="complete", expanded=False)
                                else: status.update(label="Save Failed", state="error")
                            except Exception as e:
                                status.update(label="Error", state="error"); st.error(f"{e}")
                    time.sleep(0.5); st.rerun()
