import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time
import base64

# ================= 1. 系统配置 =================
st.set_page_config(
    page_title="AI Studio", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="auto"
)

st.markdown("""
<style>
    /* 全局字体 */
    html, body, [class*="css"] { font-family: 'Inter', 'Roboto', sans-serif; color: #1a1a1a; font-size: 14px; }
    /* 标题压制 */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { font-size: 16px !important; font-weight: 700 !important; margin: 10px 0 !important; }
    /* 界面去噪 */
    footer {visibility: hidden;} 
    .stDeployButton, div[data-testid="stDecoration"] {display:none;}
    section[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #E0E0E0; }
    /* 按钮优化 */
    div.stButton > button { 
        background-color: #FFF; border: 1px solid #D1D1D1; color: #333; 
        border-radius: 6px; font-size: 14px; padding: 8px 12px; min-height: 40px; width: 100%;
    }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    /* 聊天气泡 */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 5px 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { background-color: #F0F0F0 !important; color: #000 !important; }
    /* 导航链接 */
    .nav-link { display: block; padding: 6px 10px; margin-bottom: 4px; text-decoration: none; color: #555; background-color: #f8f9fa; border-radius: 4px; border-left: 3px solid #ddd; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .nav-link:hover { background-color: #e8f0fe; border-left-color: #1a73e8; color: #1a73e8; }
    @media (max-width: 768px) { div[data-testid="column"]:nth-of-type(2) { display: none; } }
</style>
""", unsafe_allow_html=True)

# ================= 2. 后端服务 (修复版) =================

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")
if not api_key: st.stop()
genai.configure(api_key=api_key)

@st.cache_data(ttl=3600)
def get_available_models():
    try:
        priority = ["gemini-1.5-flash", "gemini-2.0-flash-exp"]
        others = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                name = m.name.replace("models/", "")
                if name not in priority: others.append(name)
        return priority + sorted(others, reverse=True)
    except: return ["gemini-1.5-flash", "gemini-1.5-pro"]

# === 核心修复：更强健的数据读取 ===
def load_data(filename):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            # 1. 获取文件对象
            content_file = repo.get_contents(filename)
            
            # 2. 尝试标准解码
            if content_file.encoding == "base64":
                raw_data = base64.b64decode(content_file.content).decode('utf-8')
            elif content_file.encoding == "none":
                # 如果 GitHub 说 encoding 是 none，通常意味着文件太大，或者已经是纯文本
                # 这种情况下，content_file.content 可能已经是解码后的字符串，或者需要直接用 decoded_content
                try:
                    raw_data = content_file.decoded_content.decode('utf-8')
                except:
                    # 兜底：如果上面失败，尝试直接读取 blob
                    blob = repo.get_git_blob(content_file.sha)
                    raw_data = base64.b64decode(blob.content).decode('utf-8')
            else:
                # 其他情况，尝试直接解码
                raw_data = content_file.decoded_content.decode('utf-8')

            return json.loads(raw_data), content_file.sha
            
        except Exception as e:
            print(f"Load Error for {filename}: {e}")
            return {}, None
    except: return {}, None

def save_data_with_retry(filename, data, sha, message="Update", max_retries=3):
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    c_str = json.dumps(data, indent=2, ensure_ascii=False)
    for attempt in range(max_retries):
        try:
            if sha: commit = repo.update_file(filename, message, c_str, sha)
            else: commit = repo.create_file(filename, "Init", c_str)
            return True, commit['content'].sha
        except Exception as e:
            time.sleep(1)
            if attempt == max_retries - 1: return False, sha
    return False, sha

# ================= 3. 状态初始化 =================

if "data_loaded" not in st.session_state:
    with st.spinner("Loading Data (Large File Support)..."):
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
    
    with st.expander("💸 Cost Saver", expanded=True):
        context_limit = st.slider("Context Limit", 5, 50, 20, help="Only send recent N turns.")
    
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
                if ok: st.session_state.roles_sha = new_sha; st.success("Saved!"); time.sleep(0.5); st.rerun()
    
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

if st.session_state.curr_id == "NEW":
    if st.button("⬅️ Back"): st.session_state.curr_id = None; st.rerun()
    st.markdown("#### New Chat")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1: sr = st.selectbox("Role", list(roles.keys()) if roles else ["Default"])
        with c2: 
            sm = st.selectbox("Model", available_models, index=0)
            if "pro" in sm: st.warning("⚠️ Pro is expensive!")
            
        if st.button("Start", type="primary", use_container_width=True):
            nid = str(uuid.uuid4())
            chats[nid] = {"title": "New Chat", "role": sr, "model": sm, "messages": []}
            ok, new_sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
            if ok: st.session_state.chats_sha = new_sha; st.session_state.curr_id = nid; st.rerun()

elif st.session_state.curr_id is None:
    c1, c2 = st.columns([3, 1])
    with c1: st.markdown("### 💬 All Chats")
    with c2: 
        if st.button("＋ New Chat", key="main_new_btn", type="primary", use_container_width=True):
            st.session_state.curr_id = "NEW"
            st.rerun()
    st.divider()
    if not chats: st.info("No history.")
    else:
        for cid in list(chats.keys())[::-1]:
            c = chats[cid]
            label = f"**{c.get('title')}**\n\n{c.get('role')} · {len(c.get('messages',[]))//2} turns"
            if st.button(label, key=f"h_{cid}", use_container_width=True):
                st.session_state.curr_id = cid
                st.rerun()

else:
    cid = st.session_state.curr_id
    if cid in chats:
        curr = chats[cid]
        msgs = curr.get("messages", [])
        
        c_back, c_info, c_menu = st.columns([1, 6, 1])
        with c_back:
            if st.button("⬅️", use_container_width=True): st.session_state.curr_id = None; st.rerun()
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

        col_chat, col_nav = st.columns([3, 1])
        with col_nav:
            st.markdown("**📌 Outline**")
            if msgs:
                for i in range(0, len(msgs), 2):
                    if msgs[i]['role'] == 'user':
                        q_text = msgs[i]['content']
                        short_text = (q_text[:20] + '..') if len(q_text) > 20 else q_text
                        st.markdown(f"<a href='#turn_{i}' class='nav-link' target='_self'>{i//2 + 1}. {short_text}</a>", unsafe_allow_html=True)

        with col_chat:
            for i, msg in enumerate(msgs):
                if msg['role'] == 'user': st.markdown(f"<div id='turn_{i}' style='height:0px; margin-top:-10px;'></div>", unsafe_allow_html=True)
                avatar = "▪️" if msg["role"] == "user" else "▫️"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        with st.expander("Copy"): st.code(msg["content"], language=None)

            if prompt := st.chat_input("Type..."):
                with st.chat_message("user", avatar="▪️"): st.markdown(prompt)
                
                with st.status("Saving input...", expanded=False) as s1:
                    msgs.append({"role": "user", "content": prompt})
                    if len(msgs)==1: curr["title"] = prompt[:10]
                    curr["messages"] = msgs; chats[cid] = curr; st.session_state.chats = chats
                    ok1, sha1 = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                    if ok1: st.session_state.chats_sha = sha1; s1.update(label="Input saved", state="complete")
                    else: s1.update(label="Input save failed", state="error"); st.stop()

                with st.chat_message("assistant", avatar="▫️"):
                    ph = st.empty()
                    status = st.status("Processing...", expanded=True)
                    try:
                        status.update(label="Connecting...", state="running")
                        
                        limit_count = context_limit * 2
                        history_to_send = msgs[:-1]
                        if len(history_to_send) > limit_count:
                            history_to_send = history_to_send[-limit_count:]
                            if history_to_send and history_to_send[0]['role'] == 'model': history_to_send.pop(0)
                        
                        formatted = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in history_to_send]
                        
                        model = genai.GenerativeModel(curr.get("model"), system_instruction=roles.get(curr.get("role"),""))
                        chat = model.start_chat(history=formatted)
                        
                        full = ""
                        max_gen_retries = 2
                        for gen_attempt in range(max_gen_retries):
                            try:
                                current_timeout = 60 * (gen_attempt + 1)
                                full = ""
                                for chunk in chat.send_message(prompt, stream=True, request_options={'timeout': current_timeout}):
                                    if chunk.text: full+=chunk.text; ph.markdown(full+"▌")
                                if full: break 
                            except Exception as e:
                                if gen_attempt == max_gen_retries - 1: raise e
                                status.update(label=f"Network busy (504), retrying...", state="running")
                                time.sleep(2)
                        
                        ph.markdown(full)
                        if not full: raise Exception("Empty response")

                        status.update(label="Saving response...", state="running")
                        msgs.append({"role": "assistant", "content": full})
                        curr["messages"] = msgs; chats[cid] = curr; st.session_state.chats = chats
                        
                        ok2, sha2 = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                        if ok2:
                            st.session_state.chats_sha = sha2
                            status.update(label="✅ Saved!", state="complete", expanded=False)
                        else:
                            status.update(label="❌ Save Failed", state="error", expanded=True)
                            st.error("Copy text manually.")
                            
                    except Exception as e:
                        status.update(label="Error", state="error")
                        st.error(f"{e}")
                        if st.button("💾 Force Save"):
                            ok, new_sha = save_data_with_retry("chats.json", chats, st.session_state.chats_sha)
                            if ok: st.session_state.chats_sha = new_sha; st.success("Saved!"); time.sleep(1); st.rerun()
