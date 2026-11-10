# 贡献指南

感谢你愿意改进这个项目。提交前请先确认以下几点。

## 开发环境

- Windows 10/11（项目依赖 Win32 窗口 API，其他系统无法运行）
- Python 3.9+
- PC 微信 4.x（仅手工联调时需要；自动化测试不依赖微信）

```powershell
pip install -r requirements.txt -r requirements-dev.txt
```

## 本地检查

```powershell
python -m pytest tests -q
python env_check.py
```

- 新增逻辑请配套单元测试，测试中不要调用真实微信窗口、不要发送消息。
- 涉及窗口/截图的代码请保证 `DRY_RUN=True` 时不会产生真实点击。
- 提交前确认 `local_config.json`、`logs/`、`data/`、`assets/*.png` 没有被带入。

## 代码约定

- 统一 UTF-8、LF 换行；Python 代码保持现有中文注释风格。
- 不要在源码中写入任何真实微信号、联系人姓名、API 密钥或聊天内容。
- 新增配置项时同步更新：`config.py`、`control/server.py` 的 `FIELD_TYPES`、
  控制台表单和 README 配置表。
- 所有对微信的写操作必须保留失败清理与发送后校验，不允许"发出去就不管"。

## 提交 PR

1. Fork 并新建分支（如 `feat/bubble-detect`）。
2. 提交信息说明动机与行为变化，一个 PR 只做一件事。
3. 确保 `pytest` 全绿，并在 PR 描述里写明测试方式与影响范围。
4. 涉及识别算法/布局的改动，请附上脱敏后的截图或数值说明，不要贴真实聊天内容。

## 合规底线

禁止提交以下改动：

- 协议逆向、DLL 注入、内存修改、登录或验证码绕过、风控规避；
- 群发、批量加好友、营销引流、骚扰他人相关的功能；
- 任何上传聊天内容到第三方服务的默认行为（用户显式配置的模型接口除外）。

维护者有权拒绝不符合上述底线的 PR。
