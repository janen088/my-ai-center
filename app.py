import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 基础配置 (移除隐藏菜单的 CSS) =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="▪️", 
    layout="wide", 
    initial_sidebar_state="expanded" # 强制展开
)

st.markdown("""
<style>
    /* 全局字体优化 */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    
    /* 标题压制 */
    .stMarkdown h1 { font-size: 16px !important; font-weight: 700 !important; margin: 10px 0 !important; }
    .stMarkdown h2 { font-size: 15px !important; font-weight: 600 !important; margin: 8px 0 !important; }
    
    /* --- 关键修改：不再隐藏 header，确保你能看到展开按钮 --- */
    /* header {visibility: hidden;}  <-- 这行被我删了 */
    footer {visibility: hidden;}
    
    /* 侧边栏背景 */
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    
    /* 按钮与输入框 */
    div.stButton > button { background-color: #FFF; border: 1px solid #D1D1D1; color: #333; border-radius: 4px; font-size: 13px; }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* 聊天气泡 */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { background-color: #F0F0F0 !important; color: #000 !important; }
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

# --- 左侧边栏 ---
with st.sidebar:
    st.markdown("### AI Studio")
    # 默认选中 Project 模式，这样你一进来就能看到双栏
    app_mode = st.radio("Mode", ["☁️ Project", "⚡ Flash"], index=0) 
    st.divider()

# >>>>>>>>>> 场景 A: 闪电模式 <<<<<<<<<<
if app_mode == "⚡ Flash":
    st.info("⚡ Flash Mode: No Sidebar, No History.")
    model_name = st.selectbox("Model", available_models)
    if "flash_msgs" not in st.session_state: st.session_state.flash_msgs = []
    if st.button("Clear"): st.session_state.flash_msgs = []; st.rerun()
    
    for msg in st.session_state.flash_msgs:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if prompt := st.chat_input("Ask..."):
        st.session_state.flash_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            ph = st.empty()
            model = genai.GenerativeModel(model_name)
            chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.flash_msgs[:-1]])
            full = ""
            for chunk in chat.send_message(prompt, stream=True):
                if chunk.text: full+=chunk.text; ph.markdown(full)
            st.session_state.flash_msgs.append({"role": "assistant", "content": full})

# >>>>>>>>>> 场景 B: 项目模式 (双栏) <<<<<<<<<<
else:
    if "curr_id" not in st.session_state: st.session_state.curr_id = None
    roles, roles_sha = load_data("roles.json")
    chats, chats_sha = load_data("chats.json")

    # 左侧栏内容
    with st.sidebar:
        if st.button("＋ New Project", type="primary", use_container_width=True):
            st.session_state.curr_id = None; st.rerun()
        
        st.caption("History")
        if chats:
            for cid in list(chats.keys())[::-1]:
                title = chats[cid].get('title', 'Untitled')
                btype = "primary" if st.session_state.curr_id == cid else "secondary"
                if st.button(title, key=cid, use_container_width=True, type=btype):
                    st.session_state.curr_id = cid; st.rerun()
        else:
            st.warning("No chats found.")
            
        st.divider()
        with st.expander("Roles"):
            rn = st.text_input("Role Name"); rp = st.text_area("Prompt")
            if st.button("Save"):
                if rn and rp: roles[rn]=rp; save_data("roles.json", roles, roles_sha); st.rerun()

    # 主界面
    if st.session_state.curr_id is None:
        st.markdown("#### New Project")
        if not roles: st.info("Create a role in sidebar.")
        else:
            c1, c2 = st.columns(2)
            with c1: sr = st.selectbox("Role", list(roles.keys()))
            with c2: sm = st.selectbox("Model", available_models)
            if st.button("Start", type="primary"):
                nid = str(uuid.uuid4())
                chats[nid] = {"title": "New Chat", "role": sr, "model": sm, "messages": []}
                save_data("chats.json", chats, chats_sha)
                st.session_state.curr_id = nid; st.rerun()
    else:
        cid = st.session_state.curr_id
        if cid in chats:
            curr = chats[cid]
            msgs = curr.get("messages", [])
            
            # === 双栏布局 ===
            col_chat, col_ctrl = st.columns([3, 1])
            
            # 右侧控制台
            with col_ctrl:
                st.markdown("**Control**")
                nt = st.text_input("Title", value=curr.get('title',''))
                if st.button("Rename"):
                    curr['title'] = nt; chats[cid] = curr; save_data("chats.json", chats, chats_sha); st.rerun()
                if st.button("Delete"):
                    del chats[cid]; save_data("chats.json", chats, chats_sha); st.session_state.curr_id = None; st.rerun()
                st.divider()
                st.info(f"Role: {curr.get('role')}")
                
            # 左侧聊天
            with col_chat:
                for msg in msgs:
                    avatar = "▪️" if msg["role"] == "user" else "▫️"
                    with st.chat_message(msg["role"], avatar=avatar):
                        st.markdown(msg["content"])
                
                if prompt := st.chat_input("Type..."):
                    msgs.append({"role": "user", "content": prompt})
                    if len(msgs)==1: curr["title"] = prompt[:10]
                    with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
                    
                    with st.chat_message("assistant", avatar="▫️"):
                        ph = st.empty()
                        model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                        chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]])
                        full = ""
                        for chunk in chat.send_message(prompt, stream=True):
                            if chunk.text: full+=chunk.text; ph.markdown(full)
                        msgs.append({"role": "assistant", "content": full})
                        curr["messages"] = msgs; chats[cid] = curr
                        save_data("chats.json", chats, chats_sha)
