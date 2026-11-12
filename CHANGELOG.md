# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## 1.2.1 (2026-11-12)

全量逐字节复查后的缺陷修复与加固（只读复查发现，不改变既有功能契约）。

### 修复

- **P1**：`control/server.py` 启动伴侣时 `Popen.wait(time=1.8)` 误用不存在的形参，
  改为 `wait(timeout=1.8)`，消除点击启动即返回 500 的问题（进程此前已实际启动）。
- **P2**：`env_check.REQUIRED_PACKAGES` 补齐 `pynput`、`winocr`，新机器环境检测/
  按需安装与打包态导入冒烟随之覆盖，避免热键与 OCR 兜底静默失效。
- **P2**：控制台保存配置后的回读校验，对密钥/环境变量覆盖字段跳过等值比对，
  避免保存成功却误报 500。
- `license._cpu_id` 改为 CIM 优先（wmic 的现代替代）、注册表名称兜底，
  解决 Win11 移除 wmic 后机器指纹降级的问题。
- `wx_window.grab_region` 增加上界钳制，窗口缩放/标定偏差时不再越界抓取。
- `snap_wechat.py` 未找到窗口时友好退出，不再抛 AttributeError。

### 变更

- 移除 `single_instance.already_running()` 未使用且有句柄泄漏隐患的死代码。
- 抽取 `wx_detect._grid_signature` 公共 helper，消除两个签名函数的重复逻辑。
- 伴侣退出路径补充 `brain.close()`，显式释放 HTTP 连接池。
- `WeChatCompanion.spec` 同步补齐 pynput/winocr/winrt 的子模块收集。

### 测试

- 新增 `memory_store`、`wx_ocr`、历史双约束裁剪专项测试共 16 项，全量用例达到 79 项。
- README 目录树、配置表、控制台说明与手工配置示例同步新模块与新字段。

## 1.2.0 (2026-11-12)

### 安全（修复打包态进程爆炸）

- **根因**：打包后 `env_check` 仍用安装元数据判断依赖，内置包被误判缺失，
  再以 `sys.executable -m pip install` 自我拉起，形成无限自我复制直至内存耗尽。
- 打包态（frozen）彻底禁用 pip/ensurepip/在线安装，只做内置模块导入冒烟，失败即退出。
- 新增 `single_instance.py`：Windows 命名 Mutex 保证整机仅一个控制台实例。
- 启动器拒绝 `-m`/`pip`/`ensurepip` 等危险自调用参数，从机制上杜绝再次自我复制。

### 新增

- 接口故障熔断：连续失败 3 次后熔断 30s，期间快速失败，避免密集重试。
- 区域截屏：空闲轮询只抓消息区，稳定后才整窗抓取，降低 CPU 与内存占用。
- 统计库保留期治理：自动清理 30 天前事件并 VACUUM 回收空间。
- 端口占用友好提示，不再直接崩溃。
- **OCR 读消息兜底（`wx_ocr.py`）**：右键复制失败时，自动用 Windows 内置 OCR
  （winocr，无 PyTorch）识别气泡文字，并清理中文间插入的空格，提升读取成功率。
- **全局热键事件化（pynput）**：停止热键改为 pynput 监听，替代 `GetAsyncKeyState`
  轮询；依赖缺失时自动回退轮询，功能键与普通键均能正确解析。
- **会话历史持久化（`memory_store.py`）**：对话历史写入 SQLite，重启后自动恢复多轮上下文；
  新增近似 token 估算与“条数 + token 上限”双约束裁剪，防止超出模型上下文窗口。
- 控制台新增「识别与记忆增强」卡片，可可视化配置 OCR 与记忆策略；
  配置读取改为缓存，仅在保存后重载，减少重复模块 reload。

### 变更

- 读图剪贴板改为 try/finally 兜底，任何异常都还原用户原剪贴板。

## 1.1.0 (2026-11-10)

### 新增

- 开源仓库结构：`.gitignore`、`.gitattributes`、MIT `LICENSE`、`CONTRIBUTING.md`、GitHub Actions CI。
- `assets/README.md`：说明标定截图的生成方式与隐私风险，截图默认不入库。
- 配置持久化测试：覆盖密钥剔除、原子写入、扩展字段保留。

### 变更

- **控制台保存配置改为写入 `local_config.json`**，不再改写 `src/wechat_companion/config.py`，
  也不再生成 `config.py.bak`。保存配置不会污染源码或提交记录。
- `config.py` 只保留可公开的默认值：目标微信号、联系人名、伴侣人设改为占位/通用默认，
  真实值通过 `local_config.json`（已 gitignore）或环境变量提供。
- `DEEPSEEK_BASE_URL` 支持通过 `local_config.json` 覆盖，便于接入兼容接口。
- README 重写：去除个人化内容，补充快速开始、配置优先级、架构、测试、打包、隐私与合规说明。

### 修复

- 干净检出（无 `local_config.json`）时，`test_config_get` 不再假设存在真实联系人。
- 配置校验测试不再直接依赖本机 `local_config.json`：仅补齐必填示例值，干净克隆与 CI 均可通过。

### 安全

- 仓库不再包含 `config.py.bak`、`__pycache__`、日志、统计数据库、DPAPI 密钥、
  机器许可证与含真实聊天画面的标定截图。
- 服务端保存配置时会主动剔除 `DEEPSEEK_API_KEY`，密钥只进 DPAPI 存储。

## 1.0.0

- 首个完整版本：屏幕捕捉 + 键鼠模拟 + DeepSeek 自动回复、可视化控制台、
  单实例与生命周期保护、运行统计、授权框架、PyInstaller 打包。
