import streamlit as st
from github import Github
import json

st.set_page_config(page_title="Debug Mode", layout="wide")

st.title("🛠️ 连接诊断模式")

# 1. 检查密钥是否存在
st.subheader("1. 检查 Secrets 配置")
try:
    token = st.secrets.get("GITHUB_TOKEN")
    repo_name = st.secrets.get("REPO_NAME")
    
    if not token:
        st.error("❌ GITHUB_TOKEN 未找到！请检查 Streamlit Secrets。")
        st.stop()
    else:
        # 只显示前几位，防止泄露
        st.success(f"✅ Token 已读取: {token[:4]}...{token[-4:]}")
        
    if not repo_name:
        st.error("❌ REPO_NAME 未找到！")
        st.stop()
    else:
        st.success(f"✅ 目标仓库: {repo_name}")

except Exception as e:
    st.error(f"❌ 读取 Secrets 失败: {e}")
    st.stop()

# 2. 测试 GitHub 连接
st.subheader("2. 测试 GitHub API 连接")
g = Github(token)

try:
    user = g.get_user()
    login = user.login
    st.success(f"✅ Token 有效！登录身份: {login}")
except Exception as e:
    st.error(f"❌ Token 无效 (401 Unauthorized): {e}")
    st.info("💡 解决办法：Token 可能过期或权限不足。请重新生成 Token 并勾选 'repo' 权限。")
    st.stop()

# 3. 测试仓库读取
st.subheader("3. 测试仓库读取")
try:
    repo = g.get_repo(repo_name)
    st.success(f"✅ 仓库连接成功: {repo.full_name}")
except Exception as e:
    st.error(f"❌ 找不到仓库 (404 Not Found): {e}")
    st.info(f"💡 解决办法：请检查 REPO_NAME 是否正确？当前填的是: '{repo_name}'。确保它是 '用户名/仓库名' 的格式，且 Token 有权访问它。")
    st.stop()

# 4. 测试文件读取
st.subheader("4. 测试 chats.json 读取")
target_file = "chats.json"
try:
    contents = repo.get_contents(target_file)
    file_content = contents.decoded_content.decode()
    st.success(f"✅ 文件读取成功！大小: {len(file_content)} 字符")
    
    # 尝试解析 JSON
    try:
        json_data = json.loads(file_content)
        count = len(json_data.keys())
        st.success(f"✅ JSON 解析成功！包含 {count} 条对话记录。")
        st.json(json_data) # 展示具体数据
    except json.JSONDecodeError:
        st.error("❌ 文件内容不是有效的 JSON！数据可能损坏。")
        st.text(file_content) # 展示原始内容
        
except Exception as e:
    st.error(f"❌ 读取 chats.json 失败: {e}")
    st.warning("💡 如果显示 404，说明仓库里没有 chats.json 文件。")
