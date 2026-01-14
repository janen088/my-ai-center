import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid

# ================= 1. 基础配置 & 工业风 CSS =================
st.set_page_config(page_title="AI Studio", page_icon="▪️", layout="wide")

st.markdown("""
<style>
    /* --- 全局字体强制 --- */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Roboto', sans-serif;
        color: #1a1a1a;
    }

    /* --- 暴力压制 Markdown 里的标题字号 --- */
    /* 无论 AI 输出什么大标题，全部按住头压小 */
    .stMarkdown h1 { font-size: 16px !important; font-weight: 700 !important; margin-top: 10px !important; }
    .stMarkdown h2 { font-size: 15px !important; font-weight: 600 !important; margin-top: 10px !important; }
    .stMarkdown h3 { font-size: 14px !important; font-weight: 600 !important; margin-top: 5px !important; }
    .stMarkdown p  { font-size: 14px !important; line-height: 1.6 !important; }
    .stMarkdown li { font-size: 14px !important; }
    
    /* --- 界面去噪 --- */
    header {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* --- 侧边栏：纯粹的灰白 --- */
    section[data-testid="stSidebar"] {
        background-color: #FAFAFA;
        border-right: 1px solid #E0E0E0;
        width: 250px !important;
    }
    
    /* --- 按钮：黑白灰风格 --- */
    div.stButton > button {
        background-color: #FFFFFF;
        border: 1px solid #D1D1D1;
        color: #333333;
        border-radius: 4px; /* 直角微圆，更硬朗 */
        font-size: 13px;
        padding: 4px 10px;
        box-shadow: none;
    }
    div.stButton > button:hover {
        border-color: #000000; /* 悬停变黑 */
        color: #000000;
        background-color: #F5F5F5;
    }
    /* 主按钮：纯黑实心 */
    div.stButton > button[kind="primary"] {
        background-color: #000000;
        color: #FFFFFF;
        border: 1px solid #000000;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #333333;
    }

    /* --- 聊天气泡：完全透明，纯文字流 --- */
    .stChatMessage {
        background-color: transparent !important;
        border: none !important;
        padding: 0px !important;
        margin-bottom: 10px !important;
    }
    /* 头像去色 */
    div[data-testid="stChatMessageAvatarUser"], 
    div[data-testid="stChatMessageAvatarAssistant"] {
        background-color: #F0F0F0 !important;
        color: #000000 !important;
    }

    /* --- 输入框：极细灰线 --- */
    .stChatInputContainer {
        border-radius: 6px !important;
        border: 1px solid #E0E0E0 !important;
    }
    
    /* --- 顶部导航栏微调 --- */
    .top-nav {
        font-size: 14px;
        border-bottom: 1px solid #E0E0E0;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# 读取密钥
api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ Secrets Error")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. 核心逻辑 (不变) =================

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

# ================= 3. 黑白极简界面 =================

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

roles_data, roles_sha = load_data("roles.json")
chats_data, chats_sha = load_data("chats.json")
available_models = get_available_models()

# --- 侧边栏 ---
with st.sidebar:
    st.markdown("**AI Studio**") # 纯黑加粗小字
    
    if st.button("＋ New Chat", type="primary", use_container_width=True):
        st.session_state.current_chat_id = None
        st.rerun()
    
    st.markdown("---")
    
    if chats_data:
        chat_ids = list(chats_data.keys())[::-1]
        for chat_id in chat_ids:
            chat_info = chats_data[chat_id]
            title = chat_info.get('title', 'Untitled')
            # 选中状态：黑色实心；未选中：灰色文字
            btn_type = "primary" if st.session_state.current_chat_id == chat_id else "secondary"
            if st.button(title, key=chat_id, use_container_width=True, type=btn_type):
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

# 场景 A: 新建页
if st.session_state.current_chat_id is None:
    st.markdown("#### New Session")
    
    if not roles_data:
        st.info("Create a prompt in sidebar.")
    else:
        with st.container(border=True):
            c1, c2 = st.columns([1,1])
            with c1:
                selected_role = st.selectbox("System Prompt", list(roles_data.keys()))
            with c2:
                model_name = st.selectbox("Model", available_models)
            
            st.caption(f"Preview: {roles_data[selected_role][:80]}...")
            st.markdown("")
            
            if st.button("Start", type="primary"):
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

# 场景 B: 聊天页
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

    # 顶部极简信息条 (手写 HTML 模拟导航栏)
    st.markdown(f"""
    <div class="top-nav">
        <b>{role_name}</b> <span style="color:#666; margin-left:10px;">{model_ver}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # 删除按钮独立放右上角太难对齐，直接放到底部或者作为小功能
    # 这里为了极致简洁，我们把删除放在侧边栏或者新建时处理，或者在底部放一个小小的文本按钮
    
    # 聊天流
    for msg in messages:
        # 纯黑白头像
        avatar = "▪️" if msg["role"] == "user" else "▫️"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # 输入框
    if user_input := st.chat_input("Type a message..."):
        with st.chat_message("user", avatar="▪️"):
            st.markdown(user_input)
        
        messages.append({"role": "user", "content": user_input})
        if len(messages) == 1: current_chat["title"] = user_input[:15]
        
        try:
            model = genai.GenerativeModel(model_ver, system_instruction=role_prompt)
            history_gemini = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in messages[:-1]]
            chat = model.start_chat(history=history_gemini)
            
            with st.chat_message("assistant", avatar="▫️"):
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
    
    # 底部极简删除
    if st.button("Delete Chat", key="del_bottom"):
        del chats_data[chat_id]
        save_data("chats.json", chats_data, chats_sha)
        st.session_state.current_chat_id = None
        st.rerun()
