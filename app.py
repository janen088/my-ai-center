import streamlit as st
import google.generativeai as genai
from github import Github
import json

# ================= 1. 基础配置 =================
st.set_page_config(page_title="我的私人AI指挥台", page_icon="🧠", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥！请检查 Streamlit Secrets")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. GitHub 数据读写 =================
def get_roles():
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents("roles.json")
            return json.loads(contents.decoded_content.decode()), contents.sha
        except:
            return {}, None
    except:
        return {}, None

def save_roles(roles, sha):
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        content_str = json.dumps(roles, indent=2, ensure_ascii=False)
        if sha:
            repo.update_file("roles.json", "Update", content_str, sha)
        else:
            repo.create_file("roles.json", "Init", content_str)
        return True
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False

# ================= 3. 核心：自动获取所有可用模型 =================
@st.cache_data(ttl=3600) # 缓存1小时，避免每次都请求
def get_available_models():
    """直接问 Google 到底有哪些模型可用"""
    try:
        model_list = []
        for m in genai.list_models():
            # 只筛选支持生成的 Gemini 模型
            if 'generateContent' in m.supported_generation_methods:
                # 过滤掉老旧模型，只留 Gemini 系列
                if "gemini" in m.name:
                    # 去掉 'models/' 前缀，只留名字
                    clean_name = m.name.replace("models/", "")
                    model_list.append(clean_name)
        # 把最新的 3.0 排在前面 (倒序排列)
        model_list.sort(reverse=True)
        return model_list
    except Exception as e:
        st.error(f"获取模型列表失败: {e}")
        # 如果获取失败，返回保底列表
        return ["gemini-2.0-flash-exp", "gemini-1.5-pro"]

# ================= 4. 页面逻辑 =================
st.title("🤖 我的私人 AI 助理 (Gemini 3.0 Ready)")

roles_data, file_sha = get_roles()
available_models = get_available_models() # 获取真实模型列表

tab1, tab2 = st.tabs(["💬 开始对话", "⚙️ 角色管理"])

with tab1:
    if not roles_data:
        st.info("👋 请先去【角色管理】新建一个角色！")
    else:
        with st.sidebar:
            st.header("🧠 大脑设置")
            
            # === 这里是关键修改 ===
            # 下拉框直接使用从 Google 获取的真实列表
            st.success(f"已检测到 {len(available_models)} 个可用模型")
            model_version = st.selectbox(
                "选择模型 (已自动同步最新版)", 
                available_models,
                index=0 # 默认选第一个（通常是最新的）
            )
            
            if st.button("🧹 清空聊天"):
                st.session_state.messages = []
                st.rerun()

        selected_role = st.selectbox("👉 选择角色：", list(roles_data.keys()))
        current_prompt = roles_data[selected_role]
        
        with st.expander(f"查看设定"):
            st.info(current_prompt)

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_input := st.chat_input("输入..."):
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.messages.append({"role": "user", "content": user_input})

            try:
                history = [{"role": ("user" if m["role"]=="user" else "model"), "parts": [m["content"]]} for m in st.session_state.messages[:-1]]
                model = genai.GenerativeModel(model_version)
                chat = model.start_chat(history=history)
                response = chat.send_message(f"【系统指令】：{current_prompt}\n\n【用户】：{user_input}")
                
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"出错: {e}")

with tab2:
    st.header("🛠️ 角色库")
    action = st.radio("操作", ["➕ 新建", "✏️ 编辑"], horizontal=True)
    st.divider()

    if action == "➕ 新建":
        name = st.text_input("新角色名")
        prompt = st.text_area("设定", height=200)
        if st.button("保存", type="primary"):
            if name and prompt:
                roles_data[name] = prompt
                if save_roles(roles_data, file_sha):
                    st.success("成功")
                    st.rerun()
    else:
        if roles_data:
            target = st.selectbox("编辑对象", list(roles_data.keys()))
            old_prompt = roles_data[target]
            col1, col2 = st.columns(2)
            with col1: new_name = st.text_input("名称", value=target)
            with col2: new_prompt = st.text_area("设定", value=old_prompt, height=150)
            
            c1, c2 = st.columns([1,4])
            with c1:
                if st.button("💾 保存"):
                    if new_name != target: del roles_data[target]
                    roles_data[new_name] = new_prompt
                    save_roles(roles_data, file_sha)
                    st.rerun()
            with c2:
                if st.button("🗑️ 删除"):
                    del roles_data[target]
                    save_roles(roles_data, file_sha)
                    st.rerun()
