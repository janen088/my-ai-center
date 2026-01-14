import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid

# ================= 1. 基础配置 & CSS 美化 =================
st.set_page_config(page_title="Lee's AI Studio", page_icon="✨", layout="wide")

# 注入自定义 CSS，强制改变 Streamlit 的丑模样
st.markdown("""
<style>
    /* 1. 隐藏 Streamlit 默认的汉堡菜单和页脚 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 2. 调整整体字体，更像现代 App */
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    
    /* 3. 侧边栏美化 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa; /* 极淡的灰，像 Notion */
        padding-top: 20px;
    }
    
    /* 4. 按钮样式优化 */
    .stButton>button {
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        box-shadow: none;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        border-color: #4285f4; /* Google Blue */
        color: #4285f4;
    }
    
    /* 5. 标题字体改小 */
    h1 { font-size: 1.5rem !important; font-weight: 600; color: #333; }
    h2 { font-size: 1.2rem !important; font-weight: 500; }
    h3 { font-size: 1.0rem !important; font-weight: 500; }
    
    /* 6. 聊天气泡优化 */
    .stChatMessage {
        padding: 10px;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 读取密钥
api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥，请检查 Secrets")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. 核心逻辑 (保持不变) =================

@st.cache_data(ttl=3600)
def get_available_models():
    try:
        model_list = []
        priority_models = [
            "gemini-2.0-flash-thinking-exp-1219", 
            "gemini-1.5-pro",
            "gemini-2.0-flash-exp"
        ]
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
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False

# ================= 3. 极简界面布局 =================

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

roles_data, roles_sha = load_data("roles.json")
chats_data, chats_sha = load_data("chats.json")
available_models = get_available_models()

# --- 侧边栏 (极简风) ---
with st.sidebar:
    st.markdown("### Lee's AI Studio") # 小标题
    
    if st.button("+ 新建对话", type="primary", use_container_width=True):
        st.session_state.current_chat_id = None
        st.rerun()
    
    st.markdown("---")
    st.caption("历史记录")
    
    if chats_data:
        chat_ids = list(chats_data.keys())[::-1]
        for chat_id in chat_ids:
            chat_info = chats_data[chat_id]
            title = chat_info.get('title', '未命名对话')
            # 只有简单的文字，去掉 Emoji
            if st.button(title, key=chat_id, use_container_width=True, 
                         type="secondary" if st.session_state.current_chat_id != chat_id else "primary"):
                st.session_state.current_chat_id = chat_id
                st.rerun()
    else:
        st.caption("暂无记录")

    st.markdown("---")
    with st.expander("设置 & 角色"):
        new_role_name = st.text_input("角色名")
        new_role_prompt = st.text_area("Prompt")
        if st.button("保存角色"):
            if new_role_name and new_role_prompt:
                roles_data[new_role_name] = new_role_prompt
                save_data("roles.json", roles_data, roles_sha)
                st.rerun()

# --- 主界面 ---

# 场景 A: 新建对话 (干净的卡片式布局)
if st.session_state.current_chat_id is None:
    st.markdown("#### 👋 欢迎回来，Lee")
    st.markdown("今天想聊点什么？")
    
    if not roles_data:
        st.warning("请先在左侧添加一个角色")
    else:
        # 使用容器把选择区包起来，显得更整洁
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                selected_role = st.selectbox("选择角色", list(roles_data.keys()))
            with c2:
                model_name = st.selectbox("选择模型", available_models)
            
            st.caption(f"设定预览: {roles_data[selected_role][:60]}...")
            
            if st.button("开始对话", type="primary"):
                new_id = str(uuid.uuid4())
                chats_data[new_id] = {
                    "title": "新对话",
                    "role": selected_role,
                    "model": model_name,
                    "messages": []
                }
                save_data("chats.json", chats_data, chats_sha)
                st.session_state.current_chat_id = new_id
                st.rerun()

# 场景 B: 聊天界面 (沉浸式)
else:
    chat_id = st.session_state.current_chat_id
    if chat_id not in chats_data:
        st.session_state.current_chat_id = None
        st.rerun()
        
    current_chat = chats_data[chat_id]
    role_name = current_chat.get("role", "默认")
    role_prompt = roles_data.get(role_name, "")
    messages = current_chat.get("messages", [])
    model_ver = current_chat.get("model", "gemini-1.5-pro")

    # 顶部极简导航栏
    c1, c2, c3 = st.columns([6, 2, 1])
    with c1:
        # 只有名字，没有大标题
        st.markdown(f"**{role_name}**")
    with c2:
        st.caption(f"{model_ver}")
    with c3:
        if st.button("删除", key="del"):
            del chats_data[chat_id]
            save_data("chats.json", chats_data, chats_sha)
            st.session_state.current_chat_id = None
            st.rerun()
    
    st.divider()

    # 聊天记录
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    if user_input := st.chat_input("输入消息..."):
        with st.chat_message("user"):
            st.markdown(user_input)
        
        messages.append({"role": "user", "content": user_input})
        if len(messages) == 1: current_chat["title"] = user_input[:12]
        
        try:
            model = genai.GenerativeModel(model_ver, system_instruction=role_prompt)
            history_gemini = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in messages[:-1]]
            chat = model.start_chat(history=history_gemini)
            
            with st.chat_message("assistant"):
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
            
            # 静默保存 (不弹大框，只在右上角转圈)
            save_data("chats.json", chats_data, chats_sha, message=f"Chat {chat_id}")
            
        except Exception as e:
            st.error(f"Error: {e}")
