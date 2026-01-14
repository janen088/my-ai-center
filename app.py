import streamlit as st
import google.generativeai as genai

# ================= 配置区域 =================
# 页面基础设置
st.set_page_config(page_title="我的私人AI指挥台", page_icon="🤖", layout="wide")

# 获取API Key
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    st.error("⚠️ 还没有配置 API Key，请去 Streamlit 后台配置！")
    st.stop()

# 配置 Gemini
genai.configure(api_key=api_key)

# ================= 侧边栏：角色与记忆管理 =================
with st.sidebar:
    st.title("🎛️ 指挥中心")
    
    # 1. 定义你的角色库 (如果你想加新角色，就在这里改代码，或者在下方临时修改)
    default_roles = {
        "默认助手": "你是一个乐于助人的AI助手，回答简洁明了。",
        
        "Python 专家": """
        你是一个资深的 Python 程序员。
        1. 你的代码必须符合 PEP8 规范。
        2. 只要代码，不要废话。
        3. 记住我喜欢用 snake_case 命名变量。
        """,
        
        "英语私教": """
        你是一个严格的英语老师。
        1. 请纠正我发送的所有句子的语法错误。
        2. 用中文解释我错在哪里。
        3. 给我列出3个相关的生词。
        """,
        
        "知心朋友": """
        你是我认识多年的老朋友。
        1. 语气轻松、幽默，不要像个机器人。
        2. 无论我说什么，先站在我的角度表示理解。
        3. 记住我最近工作压力很大，多鼓励我。
        """
    }
    
    # 2. 选择角色
    selected_role = st.selectbox("当前对话角色", list(default_roles.keys()))
    
    # 3. 记忆/设定微调 (这是你最想要的功能)
    st.info("👇 在下方修改设定，让它更懂你 (当前即时生效)")
    system_prompt = st.text_area(
        "角色核心记忆/指令：", 
        value=default_roles[selected_role], 
        height=250
    )
    
    # 4. 模型选择
 model_version = st.selectbox(
        "选择大脑版本", 
        ["gemini-3.0-pro-001", "gemini-3.0-flash", "gemini-2.0-flash"]
    )    
    # 5. 清除历史按钮
    if st.button("🗑️ 清空当前对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ================= 主界面：聊天区域 =================

st.header(f"正在与【{selected_role}】对话")

# 初始化历史记录
if "messages" not in st.session_state:
    st.session_state.messages = []

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 处理用户输入
if user_input := st.chat_input("输入你的指令..."):
    # 1. 显示用户消息
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 2. 呼叫 Gemini
    try:
        # 拼接系统指令和历史记录
        # 注意：为了让它时刻记得设定，我们把 system_prompt 放在最前面
        
        # 转换历史记录格式
        history_for_gemini = []
        for m in st.session_state.messages[:-1]:
            role = "user" if m["role"] == "user" else "model"
            history_for_gemini.append({"role": role, "parts": [m["content"]]})

        # 启动聊天会话
        model = genai.GenerativeModel(model_version)
        chat = model.start_chat(history=history_for_gemini)
        
        # 发送带有“强力指令”的消息
        # 我们把设定拼在最后一次提示词里，确保它不会忘
        final_prompt = f"【系统核心指令(必须遵守)】：\n{system_prompt}\n\n【用户输入】：\n{user_input}"
        
        response = chat.send_message(final_prompt)
        
        # 3. 显示 AI 回复
        with st.chat_message("assistant"):
            st.markdown(response.text)
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        
    except Exception as e:
        st.error(f"出错了: {e}")
