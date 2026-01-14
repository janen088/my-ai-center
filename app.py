import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 基础配置 & 强力 CSS (地毯式修复字号) =================
st.set_page_config(page_title="AI Studio", page_icon="▪️", layout="wide")

st.markdown("""
<style>
    /* --- 全局字体基准 --- */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Roboto', sans-serif;
        color: #1a1a1a;
        font-size: 14px; /* 正文基准 */
    }

    /* --- 暴力压制所有标题 (H1-H6) --- */
    /* 无论层级多深，最大不超过 16px，最小不低于 13px */
    .stMarkdown h1 { font-size: 16px !important; font-weight: 700 !important; margin: 12px 0 8px 0 !important; }
    .stMarkdown h2 { font-size: 15px !important; font-weight: 600 !important; margin: 10px 0 6px 0 !important; }
    .stMarkdown h3 { font-size: 14px !important; font-weight: 600 !important; margin: 8px 0 4px 0 !important; }
    .stMarkdown h4 { font-size: 14px !important; font-weight: 500 !important; font-style: italic; margin: 6px 0 2px 0 !important; }
    .stMarkdown h5, .stMarkdown h6 { font-size: 13px !important; font-weight: 500 !important; color: #555 !important; }
    
    /* --- 修复列表和正文的间距 --- */
    .stMarkdown p { font-size: 14px !important; line-height: 1.6 !important; margin-bottom: 8px !important; }
    .stMarkdown li { font-size: 14px !important; line-height: 1.6 !important; }
    
    /* --- 界面去噪 --- */
    header, #MainMenu, footer {visibility: hidden;}
    
    /* --- 侧边栏 --- */
    section[data-testid="stSidebar"] { 
        background-color: #FAFAFA; 
        border-right: 1px solid #E0E0E0; 
        width: 250px !important; 
    }
    
    /* --- 按钮 (黑白灰) --- */
    div.stButton > button { 
        background-color: #FFF; border: 1px solid #D1D1D1; color: #333; 
        border-radius: 4px; font-size: 13px; padding: 4px 10px; 
    }
    div.stButton > button:hover { border-color: #000; color: #000; background-color: #F5F5F5; }
    div.stButton > button[kind="primary"] { background-color: #000; color: #FFF; border: 1px solid #000; }
    
    /* --- 聊天气泡 (透明+紧凑) --- */
    .stChatMessage { background-color: transparent !important; border: none !important; padding: 0px !important; }
    div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] { 
        background-color: #F0F0F0 !important; color: #000 !important; 
    }
    
    /* --- 状态栏 (Thinking) --- */
    .stStatusWidget { background-color: #fff !important; border: 1px solid #eee !important; }
    
    /* --- 复制框 (Expander) --- */
    .streamlit-expanderHeader { font-size: 12px !important; color: #666 !important; background-color: transparent !important; }
</style>
""", unsafe_allow_html=True)

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key: st.stop()
genai.configure(api_key=api_key)

# ================= 2. 核心逻辑 =================

@st.cache_data(ttl=3600)
def get_available_models():
    try:
        model_list = []
        priority_models = ["gemini-2.0-flash-thinking-exp-1219", "gemini-1.5-pro", "gemini-2.0-flash-exp"]
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                clean_name = m.name.replace("models/", "")
                if clean_name not in priority_models:
                    model_list.append(clean_name)
        return priority_models + sorted(model_list, reverse=True)
    except:
        return ["gemini-1.5-pro"]

def load_data(filename):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents(filename)
            return json.loads(contents.decoded_content.decode()), contents.sha
        except: return {}, None
    except: return {}, None

def save_data(filename, data, sha, message="Update"):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        content_str = json.dumps(data, indent=2, ensure_ascii=False)
        if sha: repo.update_file(filename, message, content_str, sha)
        else: repo.create_file(filename, "Init", content_str)
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

# ================= 3. 界面逻辑 =================

available_models = get_available_models()

with st.sidebar:
    st.markdown("**AI Studio**")
    app_mode = st.radio("Mode", ["☁️ Project (Auto-Save)", "⚡ Flash (No Save)"], label_visibility="collapsed")
    st.markdown("---")

# >>>>>>>>>> 模式一：闪电模式 (Flash) <<<<<<<<<<
if app_mode == "⚡ Flash (No Save)":
    st.markdown("#### ⚡ Flash Chat")
    model_name = st.selectbox("Model", available_models, label_visibility="collapsed")
    
    if "flash_messages" not in st.session_state: st.session_state.flash_messages = []
    if st.button("Clear"): st.session_state.flash_messages = []; st.rerun()
    st.divider()

    for msg in st.session_state.flash_messages:
        avatar = "▪️" if msg["role"] == "user" else "⚡"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                with st.expander("📄 Copy"): st.code(msg["content"], language=None)

    if user_input := st.chat_input("Ask..."):
        with st.chat_message("user", avatar="▪️"): st.markdown(user_input)
        st.session_state.flash_messages.append({"role": "user", "content": user_input})
        
        with st.chat_message("assistant", avatar="⚡"):
            placeholder = st.empty()
            start_time = time.time()
            # 状态反馈
            with st.status("Thinking...", expanded=True) as status:
                try:
                    model = genai.GenerativeModel(model_name)
                    history = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.flash_messages[:-1]]
                    chat = model.start_chat(history=history)
                    
                    full = ""
                    for chunk in chat.send_message(user_input, stream=True):
                        if chunk.text: full += chunk.text; placeholder.markdown(full + "▌")
                    placeholder.markdown(full)
                    
                    status.update(label=f"Done ({time.time()-start_time:.2f}s)", state="complete", expanded=False)
                    st.session_state.flash_messages.append({"role": "assistant", "content": full})
                except Exception as e:
                    status.update(label="Error", state="error")
                    st.error(f"{e}")

# >>>>>>>>>> 模式二：项目模式 (Project) <<<<<<<<<<
else:
    if "current_chat_id" not in st.session_state: st.session_state.current_chat_id = None
    roles_data, roles_sha = load_data("roles.json")
    chats_data, chats_sha = load_data("chats.json")

    with st.sidebar:
        if st.button("＋ New Project", type="primary", use_container_width=True):
            st.session_state.current_chat_id = None; st.rerun()
        if chats_data:
            for cid in list(chats_data.keys())[::-1]:
                title = chats_data[cid].get('title', 'Untitled')
                btype = "primary" if st.session_state.current_chat_id == cid else "secondary"
                if st.button(title, key=cid, use_container_width=True, type=btype):
                    st.session_state.current_chat_id = cid; st.rerun()
        st.markdown("---")
        with st.expander("Roles"):
            nn = st.text_input("Name"); np = st.text_area("Prompt")
            if st.button("Save"):
                if nn and np: roles_data[nn]=np; save_data("roles.json", roles_data, roles_sha); st.rerun()

    if st.session_state.current_chat_id is None:
        st.markdown("#### New Project")
        if not roles_data: st.info("Create a role first.")
        else:
            with st.container(border=True):
                c1, c2 = st.columns(2)
                with c1: sr = st.selectbox("Role", list(roles_data.keys()))
                with c2: sm = st.selectbox("Model", available_models)
                if st.button("Start", type="primary"):
                    nid = str(uuid.uuid4())
                    chats_data[nid] = {"title": "New Chat", "role": sr, "model": sm, "messages": []}
                    save_data("chats.json", chats_data, chats_sha)
                    st.session_state.current_chat_id = nid; st.rerun()
    else:
        cid = st.session_state.current_chat_id
        if cid in chats_data:
            curr = chats_data[cid]
            msgs = curr.get("messages", [])
            st.markdown(f"<div style='border-bottom:1px solid #eee; padding-bottom:10px; margin-bottom:10px'><b>{curr.get('role')}</b> <span style='color:#999;font-size:12px'>{curr.get('model')}</span></div>", unsafe_allow_html=True)
            
            for msg in msgs:
                avatar = "▪️" if msg["role"] == "user" else "▫️"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        with st.expander("📄 Copy"): st.code(msg["content"], language=None)

            if user_input := st.chat_input("Type..."):
                with st.chat_message("user", avatar="▪️"): st.markdown(user_input)
                msgs.append({"role": "user", "content": user_input})
                if len(msgs)==1: curr["title"] = user_input[:15]
                
                with st.chat_message("assistant", avatar="▫️"):
                    placeholder = st.empty()
                    start_time = time.time()
                    # 状态反馈
                    with st.status("Thinking...", expanded=True) as status:
                        try:
                            model = genai.GenerativeModel(curr.get("model"), system_instruction=roles_data.get(curr.get("role"), ""))
                            chat = model.start_chat(history=[{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in msgs[:-1]])
                            
                            full = ""
                            for chunk in chat.send_message(user_input, stream=True):
                                if chunk.text: full += chunk.text; placeholder.markdown(full + "▌")
                            placeholder.markdown(full)
                            
                            status.update(label="Saving...", state="running")
                            msgs.append({"role": "assistant", "content": full})
                            curr["messages"] = msgs
                            chats_data[cid] = curr
                            
                            if save_data("chats.json", chats_data, chats_sha, message=f"Chat {cid}"):
                                status.update(label=f"Done ({time.time()-start_time:.2f}s)", state="complete", expanded=False)
                            else:
                                status.update(label="Save Error", state="error")
                        except Exception as e:
                            status.update(label="Error", state="error")
                            st.error(f"{e}")
