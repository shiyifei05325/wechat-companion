# Assets

本目录用于存放运行时的布局标定产物，**默认不入库**（已在 `.gitignore` 中排除）：

| 文件 | 生成方式 | 说明 |
|---|---|---|
| `calibration_overlay.png` | `python scripts/verify_layout.py` | 在当前微信窗口上标注消息区、气泡、输入框等识别结果 |
| `wx_layout.png` | `python scripts/snap_wechat.py` | 截取微信主窗口原始画面（需要 `uiautomation`） |

这两张图都会包含**真实聊天内容与联系人列表**，请勿提交到公开仓库，也不要随日志一起外传。

`scripts/build_exe.py` 打包时会把本目录作为资源一并带入，目录存在即可，不需要图片文件。
