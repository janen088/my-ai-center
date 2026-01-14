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
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* 全局字体 */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    
    /* 标题压制 */
    .stMarkdown h1 { font-size: 16px !important; font-weight: 700 !important; margin: 10px 0 !important; }
    .stMarkdown h2 { font-size: 15px !important; font-weight: 600 !important; margin: 8px 0 !important; }
    
    /* 界面去噪 */
    header, footer {visibility: hidden;} 
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    
    /* 按钮优化 */
    div.stButton > button { background-color: #FFF; border: 1px solid #D1D1D1; color: #333; border-radius: 4px; font-size: 13px; }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* 侧边栏按钮紧凑化 */
    div[data-testid="column"] { padding: 0px 2px; }
    
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

# --- 侧边栏 ---
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

# >>>>>>>>>> 场景 B: 项目模式 (侧边栏直接管理) <<<<<<<<<<
else:
    if "curr_id" not in st.session_state: st.session_state.curr_id = None
    roles, roles_sha = load_data("roles.json")
    chats, chats_sha = load_data("chats.json")

    # === 左侧栏：列表 + 管理 ===
    with st.sidebar:
        if st.button("＋ New Project", type="primary", use_container_width=True):
            st.session_state.curr_id = None; st.rerun()
        
        st.caption("History")
        if chats:
            # 倒序遍历所有对话
            for cid in list(chats.keys())[::-1]:
                c_data = chats[cid]
                title = c_data.get('title', 'Untitled')
                
                # 使用两列布局：左边是大按钮(进入)，右边是小按钮(管理)
                col1, col2 = st.columns([5, 1])
                
                with col1:
                    # 选中状态高亮
                    btype = "primary" if st.session_state.curr_id == cid else "secondary"
                    if st.button(title, key=f"open_{cid}", use_container_width=True, type=btype):
                        st.session_state.curr_id = cid
                        st.rerun()
                
                with col2:
                    # 弹出式菜单 (Popover)
                    with st.popover("⋮", use_container_width=True):
                        st.markdown("**Manage**")
                        # 1. 改名
                        new_name = st.text_input("Name", value=title, key=f"name_{cid}")
                        if st.button("Save", key=f"save_{cid}", use_container_width=True):
                            if new_name != title:
                                chats[cid]['title'] = new_name
                                save_data("chats.json", chats, chats_sha)
                                st.rerun()
                        
                        st.divider()
                        # 2. 删除
                        if st.button("Delete", key=f"del_{cid}", type="primary", use_container_width=True):
                            del chats[cid]
                            save_data("chats.json", chats, chats_sha)
                            # 如果删的是当前正在看的，就退回到新建页
                            if st.session_state.curr_id == cid:
                                st.session_state.curr_id = None
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
            
            # 顶部简单信息
            st.markdown(f"**{curr.get('title')}** <span style='color:#888; font-size:12px; margin-left:10px'>{curr.get('role')} · {curr.get('model')}</span>", unsafe_allow_html=True)
            st.divider()

            # 聊天内容
            for msg in msgs:
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
                    with st.status("Thinking...", expanded=True) as status:
                        try:
                            model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                            chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]])
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
