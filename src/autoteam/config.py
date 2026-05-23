"""配置文件 - 从 .env 文件或环境变量加载"""

import os
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from autoteam.textio import parse_env_line, parse_env_value, read_text

# 项目根目录（pyproject.toml 所在位置）
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 加载 .env 文件（从项目根目录）
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for line in read_text(_env_file).splitlines():
        parsed = parse_env_line(line)
        if parsed:
            key, value = parsed
            os.environ.setdefault(key, value)


def _get_int_env(name: str, default: int) -> int:
    return int(parse_env_value(os.environ.get(name, str(default))))


def _get_float_env(name: str, default: float) -> float:
    return float(parse_env_value(os.environ.get(name, str(default))))


def _get_bool_env(name: str, default: bool) -> bool:
    raw = parse_env_value(os.environ.get(name, ""))
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _get_str_env(name: str, default: str = "") -> str:
    value = parse_env_value(os.environ.get(name, default))
    return str(value).strip()


def _normalize_sub2api_ws_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"off", "ctx_pool", "passthrough"}:
        return mode
    return "off"


def _normalize_chatgpt_api_transport(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"auto", "playwright", "curl_cffi"}:
        return mode
    return "auto"


# CloudMail 配置
CLOUDMAIL_BASE_URL = os.environ.get("CLOUDMAIL_BASE_URL", "")
CLOUDMAIL_EMAIL = os.environ.get("CLOUDMAIL_EMAIL", "")
CLOUDMAIL_PASSWORD = os.environ.get("CLOUDMAIL_PASSWORD", "")
CLOUDMAIL_DOMAIN = os.environ.get("CLOUDMAIL_DOMAIN", "")

# 邮箱提供者配置
MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "cloudmail").strip().lower() or "cloudmail"
MAIL_SERVICES_JSON = os.environ.get("MAIL_SERVICES_JSON", "")
MAIL_SERVICE_DEFAULT = os.environ.get("MAIL_SERVICE_DEFAULT", "").strip()

# Cloudflare Temp Email 配置
CF_TEMP_EMAIL_BASE_URL = os.environ.get("CF_TEMP_EMAIL_BASE_URL", "")
CF_TEMP_EMAIL_ADMIN_PASSWORD = os.environ.get("CF_TEMP_EMAIL_ADMIN_PASSWORD", "")
CF_TEMP_EMAIL_DOMAIN = os.environ.get("CF_TEMP_EMAIL_DOMAIN", "")

# ChatGPT Team 配置
CHATGPT_ACCOUNT_ID = os.environ.get("CHATGPT_ACCOUNT_ID", "")

# CPA (CLIProxyAPI) 配置
CPA_URL = os.environ.get("CPA_URL", "")
CPA_KEY = os.environ.get("CPA_KEY", "")

# Sub2API 配置
SUB2API_URL = os.environ.get("SUB2API_URL", "")
SUB2API_EMAIL = os.environ.get("SUB2API_EMAIL", "")
SUB2API_PASSWORD = os.environ.get("SUB2API_PASSWORD", "")
SUB2API_GROUP = os.environ.get("SUB2API_GROUP", "")
SUB2API_PROXY = _get_str_env("SUB2API_PROXY", "")
SUB2API_CONCURRENCY = _get_int_env("SUB2API_CONCURRENCY", 10)
SUB2API_PRIORITY = _get_int_env("SUB2API_PRIORITY", 1)
SUB2API_RATE_MULTIPLIER = _get_float_env("SUB2API_RATE_MULTIPLIER", 1)
SUB2API_AUTO_PAUSE_ON_EXPIRED = _get_bool_env("SUB2API_AUTO_PAUSE_ON_EXPIRED", True)
SUB2API_MODEL_WHITELIST = _get_str_env("SUB2API_MODEL_WHITELIST", "")
SUB2API_OPENAI_WS_MODE = _normalize_sub2api_ws_mode(_get_str_env("SUB2API_OPENAI_WS_MODE", "off"))
SUB2API_OPENAI_PASSTHROUGH = _get_bool_env("SUB2API_OPENAI_PASSTHROUGH", False)
SUB2API_OVERWRITE_ACCOUNT_SETTINGS = _get_bool_env("SUB2API_OVERWRITE_ACCOUNT_SETTINGS", False)

# 轮询邮件间隔/超时（秒）
EMAIL_POLL_INTERVAL = _get_int_env("EMAIL_POLL_INTERVAL", 3)
EMAIL_POLL_TIMEOUT = _get_int_env("EMAIL_POLL_TIMEOUT", 300)

# API 鉴权（不设置则不启用）
API_KEY = os.environ.get("API_KEY", "")

# 自动巡检配置
AUTO_CHECK_INTERVAL = _get_int_env("AUTO_CHECK_INTERVAL", 300)  # 巡检间隔（秒），默认 5 分钟
AUTO_CHECK_TARGET_SEATS = _get_int_env("AUTO_CHECK_TARGET_SEATS", 5)  # 自动巡检目标 Team seat 数
AUTO_CHECK_THRESHOLD = _get_int_env("AUTO_CHECK_THRESHOLD", 10)  # 额度低于此百分比触发轮转，默认 10%
AUTO_CHECK_MIN_LOW = _get_int_env("AUTO_CHECK_MIN_LOW", 2)  # 至少几个账号低于阈值才触发，默认 2
AUTO_CHECK_RETRY_ADD_PHONE = _get_bool_env("AUTO_CHECK_RETRY_ADD_PHONE", True)  # 是否自动重试 add_phone
AUTO_CHECK_ADD_PHONE_MAX_RETRIES = _get_int_env("AUTO_CHECK_ADD_PHONE_MAX_RETRIES", 3)  # add_phone 最大自动重试次数

# Playwright 代理配置
PLAYWRIGHT_PROXY_URL = os.environ.get("PLAYWRIGHT_PROXY_URL", "").strip()
PLAYWRIGHT_PROXY_SERVER = os.environ.get("PLAYWRIGHT_PROXY_SERVER", "").strip()
PLAYWRIGHT_PROXY_USERNAME = os.environ.get("PLAYWRIGHT_PROXY_USERNAME", "").strip()
PLAYWRIGHT_PROXY_PASSWORD = os.environ.get("PLAYWRIGHT_PROXY_PASSWORD", "").strip()
PLAYWRIGHT_PROXY_BYPASS = os.environ.get("PLAYWRIGHT_PROXY_BYPASS", "").strip()
PLAYWRIGHT_HEADLESS = _get_bool_env("PLAYWRIGHT_HEADLESS", False)



def _format_proxy_host(hostname: str) -> str:
    if ":" in hostname and not hostname.startswith("["):
        return f"[{hostname}]"
    return hostname


def _parse_proxy_url(proxy_url: str):
    if "://" not in proxy_url:
        return {"server": proxy_url}

    parsed = urlsplit(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return {"server": proxy_url}

    host = _format_proxy_host(parsed.hostname)
    server = f"{parsed.scheme}://{host}"
    if parsed.port:
        server = f"{server}:{parsed.port}"

    proxy = {"server": server}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


def get_chatgpt_api_transport() -> str:
    return _normalize_chatgpt_api_transport(_get_str_env("CHATGPT_API_TRANSPORT", "auto"))


def get_chatgpt_api_http_timeout() -> int:
    return max(5, _get_int_env("CHATGPT_API_HTTP_TIMEOUT", 60))


def get_chatgpt_api_impersonate() -> str:
    return _get_str_env("CHATGPT_API_IMPERSONATE", "chrome136") or "chrome136"


def get_chatgpt_http_proxy_url() -> str:
    proxy_url = _get_str_env("PLAYWRIGHT_PROXY_URL", "")
    if proxy_url:
        return proxy_url

    proxy_server = _get_str_env("PLAYWRIGHT_PROXY_SERVER", "")
    if not proxy_server:
        return ""

    username = _get_str_env("PLAYWRIGHT_PROXY_USERNAME", "")
    password = _get_str_env("PLAYWRIGHT_PROXY_PASSWORD", "")
    if not (username or password):
        return proxy_server

    parsed = urlsplit(proxy_server)
    if not parsed.scheme or not parsed.hostname:
        return proxy_server

    host = _format_proxy_host(parsed.hostname)
    auth = quote(username, safe="")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"

    proxy = f"{parsed.scheme}://{auth}@{host}"
    if parsed.port:
        proxy = f"{proxy}:{parsed.port}"
    return proxy


def get_playwright_launch_options():
    """统一的 Playwright Chromium 启动参数。"""
    options = {
        "headless": PLAYWRIGHT_HEADLESS,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-default-apps",
            "--no-default-browser-check",
        ],
    }

    proxy = None
    if PLAYWRIGHT_PROXY_URL:
        proxy = _parse_proxy_url(PLAYWRIGHT_PROXY_URL)
    elif PLAYWRIGHT_PROXY_SERVER:
        proxy = {"server": PLAYWRIGHT_PROXY_SERVER}
        if PLAYWRIGHT_PROXY_USERNAME:
            proxy["username"] = PLAYWRIGHT_PROXY_USERNAME
        if PLAYWRIGHT_PROXY_PASSWORD:
            proxy["password"] = PLAYWRIGHT_PROXY_PASSWORD

    if proxy:
        if PLAYWRIGHT_PROXY_BYPASS:
            proxy["bypass"] = PLAYWRIGHT_PROXY_BYPASS
        options["proxy"] = proxy

    return options


def setup_context_optimize(context):
    """设置 Playwright Context 资源请求过滤，拦截图片、视频和字体文件以节省流量和 CPU 开销。"""
    def block_resources(route):
        try:
            if route.request.resource_type in ("image", "media", "font"):
                route.abort()
            else:
                route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    try:
        context.route("**/*", block_resources)
    except Exception:
        pass
    return context


def create_optimized_context(browser, **extra_kwargs):
    """
    智能配置 Playwright BrowserContext。
    在 headful 模式下：保留浏览器原生的完美指纹（真实 UA、设备分辨率、物理显卡、时区等），避免人工伪装带来特征冲突。
    在 headless 模式下：对 Headless 特征（如 HeadlessChrome User-Agent、SwiftShader 虚拟显卡、navigator.webdriver）进行高保真无痕伪装。
    """
    import os

    is_headless = os.environ.get("PLAYWRIGHT_HEADLESS", "False").lower() in ("true", "1")

    context_args = {
        "accept_downloads": True,
    }

    if is_headless:
        # 1. 抽取真实浏览器版本，对齐 UA 版本，防止 navigator.userAgentData 版本冲突
        browser_ver = browser.version or "148.0.0.0"
        # 统一使用 Windows NT 10.0 作为 Headless 的高保真伪装系统（契合大多数部署环境）
        ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser_ver} Safari/537.36"
        context_args["user_agent"] = ua

        # 2. 随机设置常见分辨率，防止固定的 1280x800 特征被标记
        import random
        viewports = [
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
            {"width": 1920, "height": 1080}
        ]
        context_args["viewport"] = random.choice(viewports)
        context_args["device_scale_factor"] = random.choice([1, 1.25, 1.5, 2])
        
        # 3. 设置默认 Locale 和时区
        context_args["locale"] = "zh-CN"
        context_args["timezone_id"] = "Asia/Shanghai"

    # 允许显式传递的参数覆盖默认指纹
    context_args.update(extra_kwargs)

    context = browser.new_context(**context_args)

    # 4. 路由资源拦截优化（默认关闭，仅在显式开启 optimize_routes 时生效）
    # 注：注册、邀请等流程包含大量 Cloudflare Turnstile 验证，强行 abort 资源容易引起 CF 风控检测，因此默认不开启路由拦截优化。
    if extra_kwargs.get("optimize_routes"):
        setup_context_optimize(context)

    # 5. 注入高保真反检测 Stealth 脚本（内含 WebGL 智能降级/伪装）
    stealth_script = """
    // 隐藏 automation 属性 webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 伪装 chrome 全局对象
    window.chrome = {
      app: {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
      },
      runtime: {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
      }
    };

    // 伪装真实浏览器插件列表
    Object.defineProperty(navigator, 'plugins', {
      get: () => {
        return [
          { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
          { name: 'Chrome PDF Viewer', filename: 'mhjfbgojcjbhgocjbpjepghjelbphcgd', description: 'Portable Document Format' },
          { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
        ];
      }
    });

    // 伪装 Notification 权限查询
    if (window.navigator.permissions) {
      const originalQuery = window.navigator.permissions.query;
      window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
          Promise.resolve({ state: Notification.permission }) :
          originalQuery(parameters)
      );
    }

    // 智能伪装 WebGL 渲染硬件信息（仅当检测到虚拟/软件渲染器时，才覆盖为物理显卡）
    (() => {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return;
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (!debugInfo) return;
      const nativeRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || '';
      const nativeVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || '';
      
      const isVirtual = /swiftshader|llvmpipe|virtual|mesa|google|software/i.test(nativeRenderer) || 
                        /google/i.test(nativeVendor);
      
      if (isVirtual) {
        const mockWebGL = (glContext) => {
          const getParameter = glContext.prototype.getParameter;
          glContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) { // UNMASKED_VENDOR_WEBGL
              return 'Google Inc. (Intel)';
            }
            if (parameter === 37446) { // UNMASKED_RENDERER_WEBGL
               return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)';
            }
            return getParameter.call(this, parameter);
          };
        };
        if (window.WebGLRenderingContext) mockWebGL(WebGLRenderingContext);
        if (window.WebGL2RenderingContext) mockWebGL(WebGL2RenderingContext);
      }
    })();
    StealthScriptMarker = true;
    """
    
    context.add_init_script(stealth_script)
    return context

