import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid

# ================= 1. 基础配置 & 强力 CSS 注入 =================
st.set_page_config(page_title="Lee's AI Studio", page_icon="💠", layout="wide")

# 注入 CSS：这是改变气质的关键
st.markdown("""
<style>
    /* 1. 全局字体压缩：强制 14px，行高紧凑 */
    html, body, [class*="css"] {
        font-family: 'Roboto', 'Inter', sans-serif;
        font-size: 14px !important;
        line-height: 1.5 !important;
    }
    
    /* 2. 隐藏 Streamlit 自带的红条、菜单、页脚 */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 3. 侧边栏优化：去边框，极简 */
    section[data-testid="stSidebar"] {
        width: 260px !important; # 变窄一点
        border-right: 1px solid #E5E7EB;
    }
    
    /* 4. 按钮样式：Google 风格的圆角和蓝色文字 */
    div.stButton > button {
        background-color: transparent;
        border: 1px solid #DADCE0;
        color: #3C4043;
        border-radius: 4px;
        font-size: 13px;
        padding: 4px 12px;
        height: auto;
    }
    div.stButton > button:hover {
        border-color: #1A73E8;
        color: #1A73E8;
        background-color: #F1F3F4;
    }
    /* 主按钮实心蓝 */
    div.stButton > button[kind="primary"] {
        background-color: #1A73E8;
        color: white;
        border: none;
    }

    /* 5. 聊天气泡去色去框：像 AI Studio 一样沉浸 */
    .stChatMessage {
        background-color: transparent !important;
        border: none !important;
        padding: 5px 0px !important;
    }
    /* 用户头像背景 */
    div[data-testid="stChatMessageAvatarUser"] {
        background-color: #E8EAED !important;
    }
    /* AI 头像背景 */
    div[data-testid="stChatMessageAvatarAssistant"] {
        background-color: #E8F0FE !important;
    }

    /* 6. 输入框优化 */
    .stChatInputContainer {
        border-radius: 8px !important;
        border-color: #DADCE0 !important;
    }
    
    /* 7. 标题字号压制 */
    h1 { font-size: 18px !important; color: #202124; margin-bottom: 0px;}
    h2 { font-size: 16px !important; color: #202124; }
    h3 { font-size: 14px !important; font-weight: 600; }
    
    /* 8. 去掉顶部空白 */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }
</style>
""", unsafe_allow_html=True)

# 读取密钥
api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥")
    st.stop()

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
        except:
            return {}, None
    except:
        return {}, None

def save_data(filename, data, sha, message="Update"):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        content_str = json.dumps(data, indent=2, ensure_ascii=False)
        if sha:
            repo.update_file(filename, message, content_str, sha)
        else:
            repo.create_file(filename, "Init", content_str)
        return True
    except:
        return False

# ================= 3. 极简界面 =================

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

roles_data, roles_sha = load_data("roles.json")
chats_data, chats_sha = load_data("chats.json")
available_models = get_available_models()

# --- 侧边栏 ---
with st.sidebar:
    st.markdown("### Lee's AI Studio")
    
    if st.button("＋ New Chat", type="primary", use_container_width=True):
        st.session_state.current_chat_id = None
        st.rerun()
    
    st.markdown("---")
    
    if chats_data:
        chat_ids = list(chats_data.keys())[::-1]
        for chat_id in chat_ids:
            chat_info = chats_data[chat_id]
            title = chat_info.get('title', 'Untitled')
            # 极简按钮
            if st.button(title, key=chat_id, use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()
    else:
        st.caption("No history")

    st.markdown("---")
    with st.expander("System Prompts"):
        new_role_name = st.text_input("Name")
        new_role_prompt = st.text_area("Instructions")
        if st.button("Save"):
            if new_role_name and new_role_prompt:
                roles_data[new_role_name] = new_role_prompt
                save_data("roles.json", roles_data, roles_sha)
                st.rerun()

# --- 主界面 ---

# 场景 A: 新建页 (极简)
if st.session_state.current_chat_id is None:
    st.markdown("### Welcome back")
    
    if not roles_data:
        st.info("Please create a system prompt in the sidebar.")
    else:
        with st.container(border=True):
            c1, c2 = st.columns([1,1])
            with c1:
                selected_role = st.selectbox("System Prompt", list(roles_data.keys()))
            with c2:
                model_name = st.selectbox("Model", available_models)
            
            st.caption(f"Preview: {roles_data[selected_role][:80]}...")
            st.markdown("")
            
            if st.button("Run", type="primary"):
                new_id = str(uuid.uuid4())
                chats_data[new_id] = {
                    "title": "New Chat",
                    "role": selected_role,
                    "model": model_name,
                    "messages": []
                }
                save_data("chats.json", chats_data, chats_sha)
                st.session_state.current_chat_id = new_id
                st.rerun()

# 场景 B: 聊天页 (极简)
else:
    chat_id = st.session_state.current_chat_id
    if chat_id not in chats_data:
        st.session_state.current_chat_id = None
        st.rerun()
        
    current_chat = chats_data[chat_id]
    role_name = current_chat.get("role", "Default")
    role_prompt = roles_data.get(role_name, "")
    messages = current_chat.get("messages", [])
    model_ver = current_chat.get("model", "gemini-1.5-pro")

    # 顶部极简信息条
    c1, c2, c3 = st.columns([6, 2, 1])
    with c1:
        st.markdown(f"**{role_name}** <span style='color:gray; font-size:12px'>via {model_ver}</span>", unsafe_allow_html=True)
    with c3:
        if st.button("Del", key="del"):
            del chats_data[chat_id]
            save_data("chats.json", chats_data, chats_sha)
            st.session_state.current_chat_id = None
            st.rerun()
    
    st.divider()

    # 聊天流
    for msg in messages:
        # 自定义头像：用户用简单的圆点，AI用闪光
        avatar = "👤" if msg["role"] == "user" else "💠"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # 输入框
    if user_input := st.chat_input("Type a message..."):
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)
        
        messages.append({"role": "user", "content": user_input})
        if len(messages) == 1: current_chat["title"] = user_input[:15]
        
        try:
            model = genai.GenerativeModel(model_ver, system_instruction=role_prompt)
            history_gemini = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in messages[:-1]]
            chat = model.start_chat(history=history_gemini)
            
            with st.chat_message("assistant", avatar="💠"):
                placeholder = st.empty()
                full_response = ""
                stream = chat.send_message(user_input, stream=True)
                for chunk in stream:
                    if chunk.text:
                        full_response += chunk.text
                        placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response)
            
            messages.append({"role": "assistant", "content": full_response})
            current_chat["messages"] = messages
            chats_data[chat_id] = current_chat
            save_data("chats.json", chats_data, chats_sha, message=f"Chat {chat_id}")
            
        except Exception as e:
            st.error(f"Error: {e}")
