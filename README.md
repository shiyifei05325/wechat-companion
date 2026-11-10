# 微信虚拟伴侣 · WeChat Companion

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

用屏幕捕捉 + 键鼠模拟，在**本人已登录的 PC 微信**里自动接收指定联系人的消息，
交给 DeepSeek 生成符合人设的回复，再像真人一样把消息发出去。

不注入 DLL、不逆向协议、不读写微信内存，也不绕过登录与风控；全部操作发生在
你眼前的微信窗口里，数据只留在本机。

> **使用前必读**：[合规与免责声明](#合规与免责声明)。本项目仅供个人自用与学习，
> 自动化操作微信存在账号被限制的风险，请自行评估并遵守微信服务条款。

---

## 目录

- [功能特性](#功能特性)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [工作原理](#工作原理)
- [稳定性与性能](#稳定性与性能)
- [控制台](#控制台)
- [目录结构](#目录结构)
- [开发与测试](#开发与测试)
- [打包发布](#打包发布)
- [隐私与安全](#隐私与安全)
- [常见问题](#常见问题)
- [合规与免责声明](#合规与免责声明)
- [License](#license)

## 功能特性

- **自动收发**：监听指定联系人的新消息，自动生成并发送回复；支持手机端、PC 端发来的消息。
- **人设与记忆**：可自定义伴侣名字、性格提示词，保留最近 N 轮上下文。
- **可视化控制台**：本地网页（`127.0.0.1:5005`）内完成配置、启动/停止、看日志、看统计。
- **键鼠级真实操作**：右键气泡复制消息、粘贴回复、`Ctrl+A/Ctrl+C` 回读校验、清空输入框确认，避免重复发送。
- **本地专用**：只绑定回环地址，非本机来源一律 `403`；不监听局域网/公网。
- **密钥保护**：API Key 用 Windows DPAPI 加密存于 `data/.apikey`，不写入源码与配置文件。
- **运行保障**：单实例锁、停止标记、心跳、看门狗、逐轮异常隔离与指数退避。
- **零依赖启动**：`一键启动.bat` 自动检测 Python/依赖/微信，仅安装缺失项。
- **本地统计**：SQLite 记录今日收发、成功率、平均耗时与近 7 天趋势。
- **可打包**：PyInstaller 一键打成免安装目录，分发给没有 Python 的机器。

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（依赖 Win32 窗口 API） |
| Python | 3.9 及以上（开发环境为 3.13） |
| 微信 | PC 微信 4.x（`Weixin.exe`，Qt 自渲染界面） |
| 模型 | DeepSeek API Key（默认 `https://api.deepseek.com`，可改为兼容接口） |
| 屏幕 | 建议 1920×1080 及以上；程序会把微信窗口固定为 `1180×900` |

> 微信 4.x 的界面由 Qt 自绘，UI Automation 读不到内部控件，因此本项目采用
> “截图识别 + 键鼠模拟”路线，而不是控件树操作。

## 快速开始

### 方式一：一键启动（推荐）

1. 克隆或下载本仓库到本地（目录名建议 `wechat-companion`）：

   ```powershell
   cd wechat-companion
   ```

2. 登录 PC 微信，保持主窗口可见。
3. 双击 **`一键启动.bat`**。启动器会依次：
   - 检查系统与 Python 版本（不满足时给出提示）；
   - 逐项检查运行依赖，仅对缺失或过旧的包执行 `pip install`；
   - 提示当前是否检测到微信进程；
   - 启动后端控制台并自动打开 `http://127.0.0.1:5005`。
4. 在控制台填写目标微信号、伴侣人设、DeepSeek API Key，点击 **保存配置**。
5. 点击 **启动伴侣**。程序会自动把微信窗口固定到屏幕左上角、搜索并打开目标聊天，
   然后进入监听。

> 伴侣不会随控制台自动启动，必须在页面上手动点一次「启动伴侣」。
> 关闭控制台窗口时，伴侣会自动退出，不会留下隐藏进程。

### 方式二：命令行

```powershell
pip install -r requirements.txt
python run.py
```

`run.py` 直接运行伴侣，适合调试。停止方式：

- 按 **F9**；
- 或把鼠标猛甩到**屏幕左上角**触发 pyautogui 的 FAILSAFE；
- 或在终端 `Ctrl+C`。

### 方式三：开发模式

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python launcher.py     # 控制台
python -m pytest tests -q
```

## 配置说明

个人配置**不再写进源码**。有两条路径，任选其一：

1. **控制台保存（推荐）**：写入项目根目录的 `local_config.json`，该文件已被
   `.gitignore` 排除，不会进入提交记录。
2. **手工编辑** `local_config.json`：

   ```json
   {
     "TARGET_WXID": "wxid_xxxxxxxx",
     "TARGET_NAME": "对方昵称",
     "COMPANION_NAME": "小伴",
     "SYSTEM_PROMPT": "你是一个温柔、体贴、说话自然的聊天伙伴……",
     "DEEPSEEK_MODEL": "deepseek-chat",
     "DEEPSEEK_TEMPERATURE": 1.0,
     "KEEP_ROUNDS": 12,
     "POLL_INTERVAL": 0.6,
     "IDLE_POLL_INTERVAL": 2.0,
     "TYPE_THINK_DELAY": [0.5, 2.2],
     "REPLY_COOLDOWN": 0.8,
     "DRY_RUN": false
   }
   ```

**优先级**：环境变量 > DPAPI 密钥存储 > `local_config.json` > `config.py` 默认值。

| 配置 | 说明 | 默认 |
|---|---|---|
| `TARGET_WXID` | 要监听的联系人微信号（搜索时使用） | 空，必须填写 |
| `TARGET_NAME` | 联系人显示名，仅用于日志校验，可留空 | 空 |
| `COMPANION_NAME` | 伴侣名字（日志与控制台展示） | `小伴` |
| `SYSTEM_PROMPT` | 人设提示词 | 通用聊天伙伴 |
| `DEEPSEEK_API_KEY` | DeepSeek 密钥；也可用环境变量 `DEEPSEEK_API_KEY` | 空 |
| `DEEPSEEK_BASE_URL` | 接口地址，可换成兼容服务 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-chat` |
| `DEEPSEEK_TEMPERATURE` | 采样温度（0~2） | `1.0` |
| `KEEP_ROUNDS` | 记忆保留的最近对话轮数 | `12` |
| `POLL_INTERVAL` | 活跃期轮询间隔（秒） | `0.6` |
| `IDLE_POLL_INTERVAL` | 空闲期轮询间隔（秒） | `2.0` |
| `TYPE_THINK_DELAY` | 模拟真人思考的停顿区间（秒） | `[0.5, 2.2]` |
| `REPLY_COOLDOWN` | 发送后的冷却时间（秒） | `0.8` |
| `DRY_RUN` | 演练模式：只记录不发送 | `false` |
| `RESTORE_WINDOW_ON_EXIT` | 退出时恢复微信窗口原位置 | `false` |
| `AUTO_RESTART_ON_CRASH` | 看门狗自动重启（默认关闭） | `false` |

窗口位置与尺寸（`WINDOW_LEFT/TOP/WIDTH/HEIGHT`）属于布局参数，改版面结构时才会用到，
默认 `0, 0, 1180, 900`。**运行期间不要手动移动/缩放微信窗口**；关闭或最小化微信是允许的
（关闭则伴侣退出，最小化则暂停截图）。

## 工作原理

```
屏幕轮询（mss 截图，自适应间隔）
   │  消息区下半部灰度网格签名变化
   ▼
画面稳定确认（连续 2 次一致，防半截动画/误触发）
   ▼
气泡定位（动态采样聊天背景色 + 填充差异 + 半区限定）
   ▼
右键气泡 → 菜单首项「复制」→ Down + Enter → 读剪贴板
   │  （唯一哨兵文本，杜绝残留内容误读）
   ▼
DeepSeek /chat/completions（system 人设 + 最近 N 轮上下文）
   ▼
聚焦输入框 → 清空残留 → 粘贴 → Ctrl+A/Ctrl+C 回读校验
   ▼
Enter 发送（失败依次尝试 Ctrl+Enter、点击「发送」按钮）
   ▼
消息区签名变化 + 输入框清空 = 发送成功
```

关键防错设计：

- **哨兵剪贴板**：每次读取前写入唯一标记，读不到标记就判定读取失败，避免把上一次的剪贴板内容当成新消息。
- **发送后校验**：粘贴后回读输入框；发送后确认输入框已清空，防止重复发送。
- **防自回复**：记录最近发送的文本，即使气泡方向误判，也不会把自己的回复当作用户消息。
- **系统消息跳过**：时间分隔条等居中内容不参与收发判定。
- **新旧配色兼容**：微信 4.x 的经典配色（灰底白气泡）与新版配色（白底浅灰气泡）都能识别。
- **不与用户抢窗口**：最小化暂停、关闭退出，不“复活”窗口。

## 稳定性与性能

| 环节 | 设计 |
|---|---|
| 轮询 | 活跃期 0.6s；空闲 30s 后放慢到 2.0s |
| 检测区域 | 只监测消息区下半部，减少截图计算量 |
| 稳定确认 | 0.25s 级轮询，连续 2 次一致即认为稳定 |
| 读消息 | 右键菜单 0.75s 响应；首次读空时在气泡内换点重试 |
| 思考 + 请求 | 停顿与接口调用并行，耗时取较大值 |
| HTTP | 启动预热 TLS，keep-alive 长连接复用 |
| 异常 | 主循环逐轮隔离，指数退避（封顶 30s），单次异常不崩溃 |
| 生命周期 | `companion.lock` 单实例、`companion.stop` 优雅停止、`companion.heartbeat` 心跳、看门狗监测卡死 |
| 父进程联动 | 控制台退出后伴侣自动停止，不留隐藏进程 |

日志（均在 `logs/`）：

- `app.log`：运行日志，5MB × 5 轮转，密钥与 Bearer 自动脱敏；
- `companion_YYYYMMDD.log`：对话原文与 token 用量，按日滚动；
- `console_YYYYMMDD.log`：控制台拉起伴侣时的标准输出。

## 控制台

启动后访问 `http://127.0.0.1:5005`（仅本机可访问）：

- **联系人**：微信号、显示名；
- **人设**：伴侣名字、性格/说话风格提示词；
- **接口**：API Key、模型、温度；
- **节奏**：记忆轮数、活跃/空闲轮询、思考停顿、回复冷却；
- **看板**：今日收发数、成功率、平均耗时、近 7 天柱状图；
- **日志**：增量查看运行日志；
- **配置备份/恢复**：导出/导入 JSON（不含 API Key）；
- **安全开关**：演练模式、退出恢复窗口、异常自动重启；
- **授权信息**：机器码与授权状态（可选模块，不限制运行）。

服务端只监听 `127.0.0.1`，并在中间件层拒绝所有非回环来源（`403`）。
请勿通过反向代理或内网穿透暴露控制台。

## 目录结构

```
wechat-companion/
├── 一键启动.bat          # 用户入口：环境检测 → 按需安装 → 打开控制台
├── launcher.py           # 统一启动器（打包后兼容 --companion 子进程）
├── env_check.py          # 环境检测与按需安装（仅标准库）
├── run.py                # 命令行备用入口（直接跑伴侣）
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml        # 工程元数据（src 布局、pytest 配置）
├── src/wechat_companion/
│   ├── __init__.py       # 版本号
│   ├── config.py         # 公开默认配置（个人值放 local_config.json）
│   ├── logging_setup.py  # 统一日志：轮转 + 脱敏
│   ├── exceptions.py     # 异常体系
│   ├── validation.py     # 启动配置校验
│   ├── secret_store.py   # DPAPI 密钥保护（data/.apikey）
│   ├── stats.py          # SQLite 运行统计
│   ├── license.py        # 可选授权框架（机器码 + HMAC 许可）
│   ├── wx_window.py      # 窗口查找/激活、截图、布局标定
│   ├── wx_detect.py      # 签名、气泡识别、系统消息过滤
│   ├── wx_actions.py     # 打开聊天、右键读消息、粘贴发送
│   ├── brain.py          # DeepSeek 调用：记忆、连接池、重试
│   └── companion.py      # 主控循环
├── control/
│   ├── server.py         # Flask 控制台：配置/进程/统计/日志/本地限制
│   └── static/index.html # 控制台页面
├── scripts/
│   ├── verify_layout.py  # 重新标定布局，输出 assets/calibration_overlay.png
│   ├── snap_wechat.py    # 截取微信窗口（需 uiautomation）
│   ├── gen_license.py    # 生成本机许可证（可选）
│   └── build_exe.py      # PyInstaller 打包
├── tests/                # 单元测试（不触碰真实微信）
├── assets/               # 标定产物目录（截图不入库）
├── data/                 # 运行数据（自动创建，不入库）
└── logs/                 # 日志（自动创建，不入库）
```

运行时文件（`companion.lock` / `companion.stop` / `companion.heartbeat` /
`companion.pid`）在项目根目录自动创建、退出时自动清理，同样已被 `.gitignore` 排除。

## 开发与测试

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q          # 63 项用例
python -m pytest tests -v          # 查看明细
```

测试覆盖：环境检测、本地限制、配置校验与持久化、密钥/日志脱敏、生命周期、
窗口状态、气泡收发识别（含新旧配色与点击点抗污染）、菜单清理、DeepSeek mock、
性能并行、服务器路由。测试全部使用 mock，不会打开或操作真实微信。

代码风格：4 空格缩进、UTF-8、LF；源码内不写真实联系人信息。
CI 在 GitHub Actions 的 `windows-latest` 上运行同一套测试（见
`.github/workflows/ci.yml`）。

## 打包发布

```powershell
python -m pip install pyinstaller
python scripts/build_exe.py            # onedir，推荐
python scripts/build_exe.py --onefile  # 单文件，启动稍慢
```

产物在 `dist/WeChatCompanion/`：双击 `WeChatCompanion.exe` 打开控制台，
伴侣由控制台以 `exe --companion` 在后台拉起。用户数据、日志、密钥、统计
都写在 exe 旁的 `data/`、`logs/` 目录。

## 隐私与安全

- 以下内容**不会**进入仓库：`local_config.json`、`data/`、`logs/`、
  `assets/*.png`、运行时状态文件；`.gitignore` 已统一排除。
- API Key 使用 Windows DPAPI 加密，只有当前 Windows 用户在本机才能解密。
- 聊天内容仅在本机参与识别与生成；除你配置的模型接口外，不上传任何第三方。
- 控制台仅绑定 `127.0.0.1` 并校验来源地址。
- 分享日志或截图前请先脱敏：`logs/` 与 `assets/*.png` 可能包含真实聊天内容。

## 常见问题

**Q：启动后提示找不到目标聊天？**
确认微信号填写正确、微信已登录且主窗口可见；程序会通过搜索框打开聊天，
首次使用建议先手动打开一次目标聊天再启动。

**Q：能识别到消息但不发送？**
先看 `logs/app.log` 的报错。常见原因是输入框未清空、剪贴板被其他程序占用、
或窗口被移动导致布局偏移；停止后重新启动即可重新标定。

**Q：运行中能最小化微信吗？**
可以，最小化会暂停截图；但**不要移动或缩放窗口**，布局是固定的。
关闭微信主窗口会让伴侣退出（不会阻止你关闭）。

**Q：杀软/系统提示风险？**
程序会模拟键鼠并读取屏幕，这类行为容易被启发式规则标记。源码全部公开，
可自行审计；打包版请从本仓库自行构建。

**Q：手机端发的消息会回复吗？**
会。手机端发来的消息在 PC 端显示为左侧气泡，是主要回复对象；自己发出的消息
（绿色气泡/右侧）不会触发自回复。

**Q：微信 4.x 输入异常？**
若处于灰度“按住鼠标语音输入文字”状态，重启微信即可恢复。

## 合规与免责声明

- 本项目仅用于**本人账号、本人设备、一对一聊天**的自动化辅助。
- 不包含协议破解、DLL 注入、内存修改、登录/验证码绕过、风控规避、自动加好友、
  群发或养号能力；不会向目标以外的联系人发送消息。
- 自动化操作可能违反微信软件许可及服务协议，可能导致账号被限制或封禁。
  **使用风险由使用者自行承担**，作者不对账号处罚、数据丢失或任何间接损失负责。
- 禁止将本项目用于骚扰、诈骗、营销群发、冒充他人或其他违法用途。
- 请遵守所在地法律法规与微信平台规则；若不确定是否合规，请不要使用。

## License

[MIT](LICENSE)。你可以自由使用、修改与分发，但需保留版权与许可声明。
