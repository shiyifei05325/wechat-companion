# 安全策略

## 报告安全漏洞

如果你发现本项目存在安全漏洞，请**不要**直接在公开的 GitHub Issue 中披露。

请通过以下方式之一私下报告：

- 在仓库中使用 [GitHub 的私密安全公告（Security Advisories）](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
  功能私下提交；
- 或在 Issue 中选择仅维护者可见的方式说明情况，避免附上可直接利用的细节。

报告时请尽量包含：

- 问题的描述与影响范围；
- 复现步骤或概念验证（如适用）；
- 相关的版本、操作系统与运行环境；
- 你建议的修复方案（如有）。

## 响应流程

1. 维护者会在收到报告后尽快确认，并评估漏洞的严重性；
2. 在修复发布前，相关细节会被保密处理；
3. 修复完成后会在 [CHANGELOG](CHANGELOG.md) 中说明，并视情况发布新版本。

## 安全设计要点

本项目在设计上遵循以下安全原则：

- 控制台仅绑定回环地址 `127.0.0.1`，并拒绝所有非回环来源；
- API Key 使用 Windows DPAPI 加密存储，不写入源码与配置文件；
- 日志对密钥与令牌自动脱敏；
- 不包含协议逆向、DLL 注入、内存修改或登录/验证码绕过能力。

## 范围

本策略适用于本仓库的所有已发布版本与默认分支。
