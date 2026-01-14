import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 基础配置 =================
st.set_page_config(page_title="我的 AI Studio (Pro)", page_icon="🧠", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥！请检查 Secrets")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. 核心功能函数 =================

# --- A. 自动获取模型 (融合回来了！) ---
@st.cache_data(ttl=3600)
def get_available_models():
    """自动侦测 Google 所有可用模型"""
    try:
        model_list = []
        # 优先展示这几个（包括你会思考的那个）
        priority_models = [
            "gemini-2.0-flash-thinking-exp-1219", # 思考模型
            "gemini-1.5-pro",                     # 稳定免费旗舰
            "gemini-2.0-flash-exp"                # 极速版
        ]
        
        # 去 Google 进货
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name:
                clean_name = m.name.replace("models/", "")
                if clean_name not in priority_models:
                    model_list.append(clean_name)
        
        # 合并：优先 + 自动抓取的其他(比如3.0)
        return priority_models + sorted(model_list, reverse=True)
    except:
        return ["gemini-1.5-pro", "gemini-2.0-flash-exp"]

# --- B. GitHub 数据库读写 ---
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

# ================= 3. 页面逻辑 =================

# 初始化状态
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

# 加载数据
roles_data, roles_sha = load_data("roles.json")
chats_data, chats_sha = load_data("chats.json")
available_models = get_available_models() # 获取模型列表

# --- 侧边栏：历史列表 ---
with st.sidebar:
    st.title("🗂️ 我的对话")
    
    if st.button("➕ 新建对话", type="primary", use_container_width=True):
        st.session_state.current_chat_id = None
        st.rerun()
    
    st.divider()
    
    # 历史记录列表 (倒序)
    if chats_data:
        # 排序：把最近更新的放在最上面 (如果有 timestamp 更好，这里简单用 key 顺序)
        chat_ids = list(chats_data.keys())[::-1]
        for chat_id in chat_ids:
            chat_info = chats_data[chat_id]
            title = chat_info.get('title', '未命名对话')
            # 选中状态高亮
            if st.button(f"📝 {title}", key=chat_id, use_container_width=True, 
                         type="secondary" if st.session_state.current_chat_id != chat_id else "primary"):
                st.session_state.current_chat_id = chat_id
                st.rerun()
    else:
        st.caption("暂无历史，快去新建一个吧")

    st.divider()
    with st.expander("⚙️ 角色库管理"):
        new_role_name = st.text_input("新角色名")
        new_role_prompt = st.text_area("设定内容")
        if st.button("保存新角色"):
            if new_role_name and new_role_prompt:
                roles_data[new_role_name] = new_role_prompt
                save_data("roles.json", roles_data, roles_sha)
                st.success("已保存")
                st.rerun()

# --- 主界面 ---

# 场景 A: 新建对话向导
if st.session_state.current_chat_id is None:
    st.header("✨ 开启新会话")
    
    if not roles_data:
        st.warning("请先在左下角添加一个角色！")
    else:
        col1, col2 = st.columns(2)
        with col1:
            selected_role = st.selectbox("1. 选择 AI 伙伴", list(roles_data.keys()))
            st.info(f"设定预览：{roles_data[selected_role][:100]}...")
        with col2:
            # 这里使用了自动获取的模型列表！
            st.success(f"已联网检测到 {len(available_models)} 个模型")
            model_name = st.selectbox("2. 选择大脑", available_models)
            if "thinking" in model_name:
                st.caption("💡 这是一个会展示思考过程的模型")
        
        st.divider()
        if st.button("开始聊天 🚀", type="primary", use_container_width=True):
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

# 场景 B: 聊天界面
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

    # 顶部信息栏
    with st.container():
        c1, c2, c3 = st.columns([6, 2, 1])
        with c1: st.subheader(f"正在与【{role_name}】对话")
        with c2: st.caption(f"🧠 模型: {model_ver}")
        with c3: 
            if st.button("🗑️ 删除"):
                del chats_data[chat_id]
                save_data("chats.json", chats_data, chats_sha)
                st.session_state.current_chat_id = None
                st.rerun()
    st.divider()

    # 显示记录
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    if user_input := st.chat_input("输入你的指令..."):
        with st.chat_message("user"):
            st.markdown(user_input)
        
        messages.append({"role": "user", "content": user_input})
        if len(messages) == 1: current_chat["title"] = user_input[:10]
        
        # 调用 AI
        try:
            model = genai.GenerativeModel(model_ver, system_instruction=role_prompt)
            
            # 转换历史
            history_gemini = []
            for m in messages[:-1]:
                role = "user" if m["role"] == "user" else "model"
                history_gemini.append({"role": role, "parts": [m["content"]]})
            
            chat = model.start_chat(history=history_gemini)
            
            with st.chat_message("assistant"):
                placeholder = st.empty()
                full_response = ""
                # 开启流式 stream=True
                stream = chat.send_message(user_input, stream=True)
                
                for chunk in stream:
                    if chunk.text:
                        full_response += chunk.text
                        placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response)
            
            messages.append({"role": "assistant", "content": full_response})
            
            # 保存
            current_chat["messages"] = messages
            chats_data[chat_id] = current_chat
            
            # 异步保存提示
            with st.empty():
                st.caption("☁️ 正在同步到 GitHub...")
                save_data("chats.json", chats_data, chats_sha, message=f"Chat {chat_id}")
                st.caption("") # 消失
            
        except Exception as e:
            st.error(f"出错: {e}")
