import streamlit as st
import google.generativeai as genai
from github import Github
import json
import uuid
import time

# ================= 1. 基础配置 =================
st.set_page_config(page_title="我的 AI Studio", page_icon="🧠", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥！请检查 Secrets")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. GitHub 数据库 (读写角色 + 读写聊天记录) =================
def load_data(filename):
    """通用读取函数"""
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
    """通用保存函数"""
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

# --- 初始化数据 ---
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

# 读取 GitHub 上的数据
roles_data, roles_sha = load_data("roles.json")
chats_data, chats_sha = load_data("chats.json")

# --- 侧边栏：历史记录与新建 ---
with st.sidebar:
    st.title("🗂️ 对话列表")
    
    # 新建对话按钮
    if st.button("➕ 新建对话", type="primary", use_container_width=True):
        st.session_state.current_chat_id = None # 设为 None 表示进入新建页面
        st.rerun()
    
    st.divider()
    
    # 列出历史对话 (按时间倒序，这里简单处理)
    # chats_data 结构: { "uuid": { "title": "标题", "role": "角色名", "messages": [...] } }
    if chats_data:
        for chat_id, chat_info in list(chats_data.items())[::-1]:
            label = f"📝 {chat_info.get('title', '未命名对话')}"
            if st.button(label, key=chat_id, use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()
    else:
        st.caption("暂无历史记录")

    st.divider()
    # 底部：角色管理入口
    with st.expander("⚙️ 角色库管理"):
        new_role_name = st.text_input("新角色名")
        new_role_prompt = st.text_area("设定内容")
        if st.button("保存新角色"):
            if new_role_name and new_role_prompt:
                roles_data[new_role_name] = new_role_prompt
                save_data("roles.json", roles_data, roles_sha)
                st.success("已保存")
                st.rerun()

# --- 主界面区域 ---

# 场景 A: 新建对话向导
if st.session_state.current_chat_id is None:
    st.header("✨ 开启一个新的会话")
    
    if not roles_data:
        st.warning("请先在左下角【⚙️ 角色库管理】中添加一个角色！")
    else:
        # 1. 选角色
        selected_role = st.selectbox("选择一位 AI 伙伴：", list(roles_data.keys()))
        st.info(f"当前设定：{roles_data[selected_role]}")
        
        # 2. 选模型
        model_name = st.selectbox("选择大脑：", ["gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-2.0-flash-thinking-exp-1219"])
        
        # 3. 开始按钮
        if st.button("开始聊天 🚀"):
            # 生成新 ID
            new_id = str(uuid.uuid4())
            # 初始化数据结构
            chats_data[new_id] = {
                "title": "新对话",
                "role": selected_role,
                "model": model_name,
                "messages": []
            }
            # 保存到 GitHub
            save_data("chats.json", chats_data, chats_sha)
            # 切换状态
            st.session_state.current_chat_id = new_id
            st.rerun()

# 场景 B: 聊天界面 (类似 AI Studio)
else:
    chat_id = st.session_state.current_chat_id
    
    # 容错：如果 ID 不在数据里（比如刚删了）
    if chat_id not in chats_data:
        st.session_state.current_chat_id = None
        st.rerun()
        
    current_chat = chats_data[chat_id]
    role_name = current_chat.get("role", "默认")
    role_prompt = roles_data.get(role_name, "") # 获取最新的角色设定
    messages = current_chat.get("messages", [])
    model_ver = current_chat.get("model", "gemini-1.5-pro")

    # 标题栏
    col1, col2 = st.columns([5, 1])
    with col1:
        st.subheader(f"正在与【{role_name}】对话")
    with col2:
        if st.button("🗑️ 删除", type="primary"):
            del chats_data[chat_id]
            save_data("chats.json", chats_data, chats_sha)
            st.session_state.current_chat_id = None
            st.rerun()

    # 显示聊天记录
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    if user_input := st.chat_input("继续追问..."):
        # 1. 显示用户输入
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # 更新本地数据
        messages.append({"role": "user", "content": user_input})
        
        # 如果是第一句话，自动更新标题
        if len(messages) == 1:
            current_chat["title"] = user_input[:10] + "..."

        # 2. 调用 AI
        try:
            # 构造带 System Prompt 的历史
            # Gemini API 的 system_instruction 参数最好在 model 初始化时传入，或者拼在第一条
            # 这里我们用最稳妥的方式：拼在 history 的最前面，或者作为 system_instruction
            
            model = genai.GenerativeModel(
                model_ver,
                system_instruction=role_prompt # 关键：让它永远记得设定
            )
            
            # 转换历史格式
            history_gemini = []
            for m in messages[:-1]: # 不包含最新这条，因为 send_message 会发
                role = "user" if m["role"] == "user" else "model"
                history_gemini.append({"role": role, "parts": [m["content"]]})
            
            chat = model.start_chat(history=history_gemini)
            
            # 流式输出
            with st.chat_message("assistant"):
                placeholder = st.empty()
                full_response = ""
                stream = chat.send_message(user_input, stream=True)
                
                for chunk in stream:
                    if chunk.text:
                        full_response += chunk.text
                        placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response)
            
            # 3. 保存 AI 回复
            messages.append({"role": "assistant", "content": full_response})
            
            # 4. 同步回 GitHub (持久化保存！)
            # 更新内存数据
            current_chat["messages"] = messages
            chats_data[chat_id] = current_chat
            
            # 显示保存状态
            with st.status("正在保存记忆...", expanded=False) as status:
                save_data("chats.json", chats_data, chats_sha, message=f"Chat {chat_id}")
                status.update(label="记忆已同步到云端", state="complete", expanded=False)
            
        except Exception as e:
            st.error(f"出错: {e}")
