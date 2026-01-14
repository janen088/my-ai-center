import streamlit as st
import google.generativeai as genai
from github import Github, GithubException
import json

# ================= 1. 基础配置 =================
st.set_page_config(page_title="我的私人AI指挥台", page_icon="🧠", layout="wide")

# 读取密钥
api_key = st.secrets.get("GEMINI_API_KEY")
github_token = st.secrets.get("GITHUB_TOKEN")
repo_name = st.secrets.get("REPO_NAME")

if not api_key or not github_token or not repo_name:
    st.error("⚠️ 缺少密钥！请检查 Streamlit Secrets 配置")
    st.stop()

genai.configure(api_key=api_key)

# ================= 2. GitHub 数据读写 (智能容错版) =================
def get_roles():
    """读取角色列表"""
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        # 尝试读取文件
        try:
            contents = repo.get_contents("roles.json")
            return json.loads(contents.decoded_content.decode()), contents.sha
        except:
            # 如果文件不存在，返回空字典和 None
            return {}, None
    except Exception as e:
        st.error(f"连接 GitHub 仓库失败: {e}\n请检查 Secrets 里的 REPO_NAME 是否写对 (格式: 用户名/仓库名)")
        return {}, None

def save_roles(roles, sha):
    """保存角色列表 (自动判断新建还是更新)"""
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        content_str = json.dumps(roles, indent=2, ensure_ascii=False)
        
        if sha:
            # 如果有 SHA，说明文件存在，进行更新
            repo.update_file(
                path="roles.json",
                message="Update via App",
                content=content_str,
                sha=sha
            )
        else:
            # 如果没有 SHA，说明文件不存在，直接创建
            repo.create_file(
                path="roles.json",
                message="Create roles.json (Init)",
                content=content_str
            )
        return True
    except Exception as e:
        st.error(f"保存失败详细原因: {e}")
        return False

# ================= 3. 页面布局 =================
st.title("🤖 我的私人 AI 助理")

# 读取数据
roles_data, file_sha = get_roles()

# 使用 Tab 标签页
tab1, tab2 = st.tabs(["💬 开始对话", "⚙️ 角色管理 (增删改名)"])

# ================= Tab 1: 聊天区域 =================
with tab1:
    if not roles_data:
        st.info("👋 欢迎！目前还没有角色。请点击上方的【⚙️ 角色管理】去新建一个吧！")
    else:
        with st.sidebar:
            st.header("🧠 大脑设置")
            model_version = st.selectbox(
                "选择模型", 
                ["gemini-3.0-pro", "gemini-3.0-flash", "gemini-2.0-flash"]
            )
            if st.button("🧹 清空聊天记录"):
                st.session_state.messages = []
                st.rerun()

        # 确保选中的角色还在列表里
        role_names = list(roles_data.keys())
        selected_role_name = st.selectbox("👉 选择你要对话的角色：", role_names)
        
        if selected_role_name:
            current_prompt = roles_data[selected_role_name]
            with st.expander(f"查看【{selected_role_name}】的记忆设定"):
                st.info(current_prompt)

            # 聊天逻辑
            if "messages" not in st.session_state:
                st.session_state.messages = []

            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            if user_input := st.chat_input("说点什么..."):
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

# ================= Tab 2: 管理区域 =================
with tab2:
    st.header("🛠️ 管理你的角色库")
    
    action = st.radio("你想做什么？", ["➕ 新建一个角色", "✏️ 编辑/改名/删除现有角色"], horizontal=True)
    st.divider()

    if action == "➕ 新建一个角色":
        new_name = st.text_input("给新角色起个名字 (例如: 健身教练)")
        new_prompt = st.text_area("输入它的记忆和设定", height=200)
        
        if st.button("保存新角色", type="primary"):
            if new_name and new_prompt:
                if new_name in roles_data:
                    st.error("这个名字已经有了，请换一个！")
                else:
                    roles_data[new_name] = new_prompt
                    # 这里会调用智能保存逻辑
                    if save_roles(roles_data, file_sha):
                        st.success(f"成功创建：{new_name}")
                        st.rerun()
            else:
                st.warning("名字和内容不能为空")

    else: # 编辑模式
        if not roles_data:
            st.warning("还没有角色，先去新建一个吧")
        else:
            edit_target = st.selectbox("选择要编辑的角色", list(roles_data.keys()))
            if edit_target:
                old_prompt = roles_data[edit_target]
                
                col1, col2 = st.columns(2)
                with col1:
                    edited_name = st.text_input("角色名称 (修改这里即可改名)", value=edit_target)
                with col2:
                    edited_prompt = st.text_area("角色设定", value=old_prompt, height=150)
                
                c1, c2 = st.columns([1, 4])
                with c1:
                    if st.button("💾 保存修改", type="primary"):
                        if edited_name != edit_target:
                            del roles_data[edit_target]
                            roles_data[edited_name] = edited_prompt
                        else:
                            roles_data[edit_target] = edited_prompt
                        
                        if save_roles(roles_data, file_sha):
                            st.toast("✅ 修改已保存！")
                            st.rerun()
                
                with c2:
                    if st.button("🗑️ 删除这个角色"):
                        del roles_data[edit_target]
                        if save_roles(roles_data, file_sha):
                            st.toast("🗑️ 已删除")
                            st.rerun()
