# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

### 安全

- 仓库不再包含 `config.py.bak`、`__pycache__`、日志、统计数据库、DPAPI 密钥、
  机器许可证与含真实聊天画面的标定截图。
- 服务端保存配置时会主动剔除 `DEEPSEEK_API_KEY`，密钥只进 DPAPI 存储。

## 1.0.0

- 首个完整版本：屏幕捕捉 + 键鼠模拟 + DeepSeek 自动回复、可视化控制台、
  单实例与生命周期保护、运行统计、授权框架、PyInstaller 打包。
