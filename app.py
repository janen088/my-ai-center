import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 系统配置 =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="▪️", 
    layout="wide",
    initial_sidebar_state="collapsed" # 手机上默认收起侧边栏，因为我们有主页列表了
)

st.markdown("""
<style>
    /* --- 全局字体 --- */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    
    /* --- 标题压制 --- */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { font-size: 16px !important; font-weight: 600 !important; margin: 10px 0 !important; }
    
    /* --- 暴力隐藏 Streamlit 官方水印和按钮 (防误触) --- */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display:none;} /* 隐藏右上角 Deploy 按钮 */
    div[data-testid="stDecoration"] {display:none;} /* 隐藏顶部彩条 */
    
    /* --- 界面优化 --- */
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    
    /* --- 按钮优化 (手机上更好点) --- */
    div.stButton > button { 
        background-color: #FFF; border: 1px solid #D1D1D1; color: #333; 
        border-radius: 8px; /* 更圆润 */
        font-size: 14px; 
        padding: 10px 15px; /* 更大的点击区域 */
        min-height: 45px;   /* 手机手指好点 */
        width: 100%;
    }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* --- 聊天气泡 --- */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { background-color: #F0F0F0 !important; color: #000 !important; }
    
    /* --- 列表卡片样式 --- */
    .chat-card {
        padding: 15px;
        border: 1px solid #eee;
        border-radius: 10px;
        margin-bottom: 10px;
        background: white;
        cursor: pointer;
    }
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
        model_list = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                model_list.append(m.name.replace("models/", ""))
        return sorted(model_list, reverse=True)
    except: return ["gemini-1.5-pro", "gemini-1.5-flash"]

# GitHub 读写
def load_data_from_github(filename):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            c = repo.get_contents(filename)
            return json.loads(c.decoded_content.decode()), c.sha
        except: return {}, None
    except: return {}, None

def sync_to_github(filename, data, sha, message="Update"):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        c_str = json.dumps(data, indent=2, ensure_ascii=False)
        if sha:
            commit = repo.update_file(filename, message, c_str, sha)
            return True, commit['content'].sha
        else:
            commit = repo.create_file(filename, "Init", c_str)
            return True, commit['content'].sha
    except: return False, sha

# ================= 3. 状态管理 =================

if "data_loaded" not in st.session_state:
    with st.spinner("Loading..."):
        r_data, r_sha = load_data_from_github("roles.json")
        c_data, c_sha = load_data_from_github("chats.json")
        st.session_state.roles = r_data if r_data else {}
        st.session_state.roles_sha = r_sha
        st.session_state.chats = c_data if c_data else {}
        st.session_state.chats_sha = c_sha
        st.session_state.data_loaded = True
        st.session_state.unsaved_count = 0 

available_models = get_available_models()

def auto_save_trigger(force=False):
    SAVE_THRESHOLD = 3
    should_save = force or (st.session_state.unsaved_count >= SAVE_THRESHOLD)
    if should_save:
        st.toast("☁️ Syncing...", icon="⏳")
        ok, new_sha = sync_to_github("chats.json", st.session_state.chats, st.session_state.chats_sha)
        if ok:
            st.session_state.chats_sha = new_sha
            st.session_state.unsaved_count = 0
            st.toast("Saved", icon="✅")

# ================= 4. 界面逻辑 =================

# 侧边栏只保留最基础的“全局设置”，平时不需要打开
with st.sidebar:
    st.markdown("**Global Settings**")
    if st.button("Force Sync Now"):
        auto_save_trigger(force=True)
    st.divider()
    with st.expander("Manage Roles"):
        rn = st.text_input("Role Name"); rp = st.text_area("Prompt")
        if st.button("Save Role"):
            if rn and rp: 
                st.session_state.roles[rn]=rp
                sync_to_github("roles.json", st.session_state.roles, st.session_state.roles_sha)
                st.rerun()

# 初始化当前 ID
if "curr_id" not in st.session_state: st.session_state.curr_id = None
roles = st.session_state.roles
chats = st.session_state.chats

# >>>>>>>>>> 核心逻辑：主页即列表 (Lobby) <<<<<<<<<<

if st.session_state.curr_id is None:
    # === 首页视图 (类似微信列表) ===
    
    # 顶部：新建按钮
    c1, c2 = st.columns([3, 1])
    with c1: st.markdown("### 💬 Chats")
    with c2: 
        if st.button("＋ New", type="primary", use_container_width=True):
            # 进入新建流程
            st.session_state.curr_id = "NEW_CREATION_MODE"
            st.rerun()
    
    st.divider()

    # 列表区域
    if not chats:
        st.info("No history. Start a new chat!")
    else:
        # 倒序显示，最近的在最上面
        for cid in list(chats.keys())[::-1]:
            c_data = chats[cid]
            title = c_data.get('title', 'Untitled')
            role = c_data.get('role', 'Default')
            model = c_data.get('model', 'Gemini')
            msg_count = len(c_data.get('messages', [])) // 2
            
            # 使用一个大按钮作为卡片
            # 显示格式：标题 (角色 · 5条对话)
            label = f"{title}\n[{role} · {msg_count} turns]"
            
            if st.button(label, key=f"card_{cid}", use_container_width=True):
                st.session_state.curr_id = cid
                st.rerun()

elif st.session_state.curr_id == "NEW_CREATION_MODE":
    # === 新建页面 ===
    st.button("⬅️ Back", on_click=lambda: setattr(st.session_state, 'curr_id', None))
    st.markdown("#### Start New Chat")
    
    with st.container(border=True):
        sel_r = st.selectbox("Role", list(roles.keys()) if roles else ["Default"])
        sel_m = st.selectbox("Model", available_models)
        
        if st.button("Start Chat", type="primary", use_container_width=True):
            if not roles:
                st.error("Please create a role in Sidebar first!")
            else:
                nid = str(uuid.uuid4())
                chats[nid] = {"title": "New Chat", "role": sel_r, "model": sel_m, "messages": []}
                # 立即保存一次，防止新建后刷新丢失
                auto_save_trigger(force=True)
                st.session_state.curr_id = nid
                st.rerun()

else:
    # === 对话详情页 (Chat View) ===
    cid = st.session_state.curr_id
    if cid in chats:
        curr = chats[cid]
        msgs = curr.get("messages", [])
        
        # 顶部导航栏：返回按钮 + 标题 + 菜单
        c_back, c_title, c_menu = st.columns([1, 4, 1])
        with c_back:
            if st.button("⬅️", use_container_width=True):
                # 返回首页前，强制保存
                auto_save_trigger(force=True)
                st.session_state.curr_id = None
                st.rerun()
        
        with c_title:
            st.markdown(f"<div style='text-align:center; font-weight:bold; padding-top:10px'>{curr.get('title')}</div>", unsafe_allow_html=True)
            
        with c_menu:
            with st.popover("⚙️", use_container_width=True):
                new_t = st.text_input("Rename", value=curr.get('title',''))
                if st.button("Save"):
                    curr['title'] = new_t; auto_save_trigger(force=True); st.rerun()
                st.divider()
                if st.button("Delete", type="primary"):
                    del chats[cid]; auto_save_trigger(force=True)
                    st.session_state.curr_id = None; st.rerun()

        # 布局：在手机上会自动堆叠，在电脑上分栏
        # 但为了手机体验，我们把时光机折叠起来
        with st.expander("History Navigation (Time Machine)"):
            total = len(msgs) // 2
            if total > 0:
                focus_idx = st.slider("Jump to Turn", 1, total, total)
                try:
                    q = msgs[(focus_idx-1)*2]["content"]
                    st.caption(f"Q: {q[:50]}...")
                except: pass
            else:
                focus_idx = None
                st.caption("No history yet.")

        # 聊天区域
        if focus_idx and total > 0:
            start = (focus_idx - 1) * 2
            show_msgs = msgs[start : start+2]
            st.info(f"Viewing Turn {focus_idx}")
        else:
            show_msgs = msgs

        for msg in show_msgs:
            avatar = "▪️" if msg["role"] == "user" else "▫️"
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])
                if msg["role"] == "assistant":
                    with st.expander("Copy"): st.code(msg["content"], language=None)

        # 输入框
        if prompt := st.chat_input("Type..."):
            with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
            msgs.append({"role": "user", "content": prompt})
            if len(msgs)==1: curr["title"] = prompt[:10]
            
            with st.chat_message("assistant", avatar="▫️"):
                ph = st.empty()
                try:
                    model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                    chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]])
                    full = ""
                    for chunk in chat.send_message(prompt, stream=True):
                        if chunk.text: full+=chunk.text; ph.markdown(full + "▌")
                    ph.markdown(full)
                    
                    msgs.append({"role": "assistant", "content": full})
                    curr["messages"] = msgs; chats[cid] = curr
                    
                    # 缓存逻辑
                    st.session_state.chats = chats
                    st.session_state.unsaved_count += 1
                    auto_save_trigger(force=False)
                    
                except Exception as e:
                    st.error(f"{e}")
            st.rerun()
