import os
import sys
import subprocess
import urllib.request


def patch_macos_proxy_issue():
    """
    终极环境修补：解决 macOS 系统代理导致 httpx 崩溃的深层 Bug
    """
    # 1. 修复终端中手动 export 但缺失 scheme 的环境变量
    proxy_vars = ['http_proxy', 'https_proxy', 'all_proxy',
                  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']
    for var in proxy_vars:
        val = os.environ.get(var)
        if val and not val.startswith(('http://', 'https://', 'socks')):
            os.environ[var] = f"http://{val}"
            print(f"🔧 [终端环境修补] 修正: {var}=http://{val}")

    # 2. 拦截 macOS 底层系统代理 (核心修复点)
    # urllib.request.getproxies() 会直接读取 Mac '系统设置->网络' 里的全局代理
    sys_proxies = urllib.request.getproxies()
    for key, val in sys_proxies.items():
        if val and not val.startswith(('http://', 'https://', 'socks')):
            fixed_val = f"http://{val}"
            # 强行注入环境变量，阻断 httpx 去底层读取残缺代理的逻辑
            env_key = f"{key}_proxy".lower()
            os.environ[env_key] = fixed_val
            os.environ[env_key.upper()] = fixed_val
            print(f"🍏 [Mac 系统代理修补] 自动接管并修正底层代理: {env_key}={fixed_val}")


def main():
    # 1. 在任何第三方库加载前，率先执行修补
    patch_macos_proxy_issue()

    # 2. 获取当前文件所在目录的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 3. 定位到 Streamlit app 文件
    app_path = os.path.join(current_dir, "src", "frontend", "app.py")

    print("🚀 正在启动 AI Form Analyzer 企业级演示终端...")
    # 4. 启动 streamlit (它会继承我们修补好的干净环境变量)
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])


if __name__ == "__main__":
    main()