import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 系统配置 & 样式 =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="▪️", 
    layout="wide",
    initial_sidebar_state="auto"
)

st.markdown("""
<style>
    /* --- 全局字体 --- */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    
    /* --- 标题压制 --- */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { font-size: 16px !important; font-weight: 700 !important; margin: 10px 0 !important; }
    
    /* --- 界面去噪 --- */
    header, footer {visibility: hidden;} 
    .stDeployButton, div[data-testid="stDecoration"] {display:none;}
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    
    /* --- 按钮优化 --- */
    div.stButton > button { 
        background-color: #FFF; border: 1px solid #D1D1D1; color: #333; 
        border-radius: 6px; font-size: 14px; padding: 8px 12px; min-height: 40px; width: 100%;
    }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* --- 聊天气泡 --- */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { background-color: #F0F0F0 !important; color: #000 !important; }
    
    /* --- 导航链接 --- */
    .nav-link {
        display: block; padding: 6px 10px; margin-bottom: 4px; text-decoration: none;
        color: #555; background-color: #f8f9fa; border-radius: 4px; border-left: 3px solid #ddd;
        font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .nav-link:hover { background-color: #e8f0fe; border-left-color: #1a73e8; color: #1a73e8; }
    
    @media (max-width: 768px) {
        div[data-testid="column"]:nth-of-type(2) { display: none; }
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 后端服务 (带重试机制) =================

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

def save_data_with_retry(filename, data, sha, message="Update", max_retries=3):
    """
    带重试机制的保存函数。
    如果失败，会自动重试 3 次。
    """
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    c_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    for attempt in range(max_retries):
        try:
            if sha:
                commit = repo.update_file(filename, message, c_str, sha)
            else:
                commit = repo.create_file(filename, "Init", c_str)
            return True, commit['content'].sha
        except Exception as e:
            time.sleep(1) # 等1秒再试
            if attempt == max_retries - 1:
                print(f"Final Save Error: {e}")
                return False, sha
    return False, sha

# ================= 3. 状态初始化 =================

if "data_loaded" not in st.session_state:
    with st.spinner("Syncing with Cloud..."):
        r_data, r_sha = load_data("roles.json")
        c_data, c_sha = load_data("chats.json")
        st.session_state.roles = r_data if r_data else {}
        st.session_state.roles_sha = r_sha
        st.session_state.chats = c_data if c_data else {}
        st.session_state.chats_sha = c_sha
        st.session_state.data_loaded = True

if "curr_id" not in st.session_state: st.session_state.curr_id = None
roles = st.session_state.roles
chats = st.session_state.chats
available_models = get_available_models()

# ================= 4. 侧边栏 =================
with st.sidebar:
    st.markdown("### AI Studio")
    if st.button("＋ New Chat", type="primary", use_container_width=True):
        st.session_state.curr_id = "NEW"
        st.rerun()
    st.divider()
    
    with st.expander("👤 Role Manager"):
        rn = st.text_input("Role Name")
        rp = st.text_area("Prompt")
        if st.button("Save Role"):
            if rn and rp: 
                st.session_state.roles[rn]=rp
                ok, new_sha = save_data_with_retry("roles.json", st.session_state.roles, st.session_state.roles_sha)
                if ok:
                    st.session_state.roles_sha = new_sha
                    st.success("Saved!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Save Failed!")
    
    st.divider()
    st.caption("History")
    if chats:
        for cid in list(chats.keys())[::-1]:
            title = chats[cid].get('title', 'Untitled')
            btype = "primary" if st.session_state.curr_id == cid else "secondary"
            if st.button(title, key=f"sb_{cid}", use_container_width=True, type=btype):
                st.session_state.curr_id = cid
                st.rerun()

# ================= 5. 主界面 =================

# >>> 场景 A: 新建 <<<
if st.session_state.curr_id == "NEW":
    if st.button("⬅️ Back"): st.session_state.curr_id = None; st.rerun()
    st.markdown("#### New Chat")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1: sr = st.selectbox("Role", list(roles.keys()) if roles else ["Default"])
        with c2: sm = st.selectbox("Model", available_models)
        if st.button("Start", type="primary", use_container_width=True):
            nid = str(uuid.uuid4())
            chats[nid] = {"title": "New Chat", "role": sr, "model": sm, "messages": []}
            # 立即保存
            ok, new_sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
            if ok:
                st.session_state.chats_sha = new_sha
                st.session_state.curr_id = nid
                st.rerun()
            else:
                st.error("Network Error: Could not create chat.")

# >>> 场景 B: 列表页 <<<
elif st.session_state.curr_id is None:
    st.markdown("### 💬 All Chats")
    if not chats: st.info("No history.")
    else:
        for cid in list(chats.keys())[::-1]:
            c = chats[cid]
            label = f"**{c.get('title')}**\n\n{c.get('role')} · {len(c.get('messages',[]))//2} turns"
            if st.button(label, key=f"h_{cid}", use_container_width=True):
                st.session_state.curr_id = cid
                st.rerun()

# >>> 场景 C: 对话详情页 <<<
else:
    cid = st.session_state.curr_id
    if cid in chats:
        curr = chats[cid]
        msgs = curr.get("messages", [])
        
        # 顶部栏
        c_back, c_info, c_menu = st.columns([1, 6, 1])
        with c_back:
            if st.button("⬅️", use_container_width=True):
                st.session_state.curr_id = None; st.rerun()
        with c_info:
            st.markdown(f"<div style='text-align:center;font-weight:bold;padding-top:8px'>{curr.get('title')}</div>", unsafe_allow_html=True)
        with c_menu:
            with st.popover("⚙️"):
                nt = st.text_input("Name", value=curr.get('title',''))
                if st.button("Save"):
                    curr['title']=nt
                    ok, sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                    if ok: st.session_state.chats_sha = sha; st.rerun()
                if st.button("Delete", type="primary"):
                    del chats[cid]
                    ok, sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                    if ok: st.session_state.chats_sha = sha; st.session_state.curr_id=None; st.rerun()
        st.divider()

        # === 布局 ===
        col_chat, col_nav = st.columns([3, 1])

        # --- 右侧：目录导航 ---
        with col_nav:
            st.markdown("**📌 Outline**")
            if not msgs:
                st.caption("No messages yet.")
            else:
                for i in range(0, len(msgs), 2):
                    if msgs[i]['role'] == 'user':
                        q_text = msgs[i]['content']
                        short_text = (q_text[:20] + '..') if len(q_text) > 20 else q_text
                        st.markdown(f"<a href='#turn_{i}' class='nav-link' target='_self'>{i//2 + 1}. {short_text}</a>", unsafe_allow_html=True)

        # --- 左侧：聊天流 ---
        with col_chat:
            for i, msg in enumerate(msgs):
                if msg['role'] == 'user':
                    st.markdown(f"<div id='turn_{i}' style='height:0px; margin-top:-10px;'></div>", unsafe_allow_html=True)
                
                avatar = "▪️" if msg["role"] == "user" else "▫️"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        with st.expander("Copy"): st.code(msg["content"], language=None)

            # 输入框
            if prompt := st.chat_input("Type..."):
                # 1. 立即显示用户输入
                with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
                msgs.append({"role": "user", "content": prompt})
                if len(msgs)==1: curr["title"] = prompt[:10]
                
                # 2. AI 生成
                with st.chat_message("assistant", avatar="▫️"):
                    ph = st.empty()
                    start_t = time.time()
                    
                    # 状态容器
                    status_container = st.status("Thinking...", expanded=True)
                    try:
                        model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                        chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]])
                        
                        full = ""
                        for chunk in chat.send_message(prompt, stream=True):
                            if chunk.text: full+=chunk.text; ph.markdown(full+"▌")
                        ph.markdown(full)
                        
                        # 3. 阻塞式保存 (Blocking Save)
                        # 生成完毕后，必须先存到 GitHub，再进行下一步
                        msgs.append({"role": "assistant", "content": full})
                        curr["messages"] = msgs
                        chats[cid] = curr
                        
                        status_container.update(label="Saving to Cloud (Do not close)...", state="running")
                        
                        # 调用带重试的保存函数
                        ok, new_sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                        
                        if ok:
                            st.session_state.chats_sha = new_sha
                            status_container.update(label=f"Saved! ({time.time()-start_t:.1f}s)", state="complete", expanded=False)
                            # 4. 保存成功后，强制刷新页面，确保多端同步
                            time.sleep(0.5) 
                            st.rerun()
                        else:
                            # 极少数情况：重试3次都失败
                            status_container.update(label="CRITICAL ERROR: Save Failed!", state="error", expanded=True)
                            st.error("Could not save to GitHub after 3 attempts. Please copy your chat manually.")
                            
                    except Exception as e:
                        status_container.update(label="Error", state="error")
                        st.error(f"{e}")
