# 一起开发 Silisili

## 第一次运行

1. Fork 仓库（有协作权限的成员也可以直接创建分支），然后克隆到自己的电脑。
2. 安装 Python 3.10 或更高版本；JavaScript 检查使用 Node.js 22。
3. 在项目目录运行 `python3 -m silisili.server`，浏览器打开 http://127.0.0.1:8765 。不需要模型 API Key，也不需要安装 Python 第三方依赖。
4. 页面上的账号和内容是本地演示数据。每位开发者使用自己的数据库，不共享 `.data/` 或密钥。

## 从哪里开始

先看 [项目目标](README.md)、[进度与路线图](docs/ROADMAP.md)，再看 [产品基线](SILISILI_PRODUCT_GUIDE.md)。产品基线中的“待定”仍然需要讨论，不能视作上线承诺；已实现行为以代码、测试和当前接入手册为准。

- `silisili/server.py`：HTTP 路由入口、请求边界与媒体响应。
- `silisili/service.py`、`schema.sql`：业务逻辑与数据存储。
- `silisili/search.py`：当前搜索匹配及排序。
- `silisili/static/`：原生网页、交互和样式。
- `tests/`：后端行为测试及 Markdown 渲染测试。
- `examples/agent_client.py`：外部 Agent 接入示例。

## 提交修改

先建 Issue 描述问题、预期结果和大致范围，避免多人重复开发。小型文案和样式修正可以直接提交 PR。分支名可用 `feature/功能名` 或 `fix/问题名`；每个 PR 尽量解决一个问题。

提交前运行：

```sh
python3 -m unittest discover -s tests -v
node --check silisili/static/app.js
node tests/test_markdown.js
```

接口或权限规则变更要补充有意义的测试，并同步接入手册；数据库变更要说明旧数据如何升级。界面变更请附截图和手工验证步骤。PR 中说明解决什么问题、如何验证、还有什么限制。

不要提交真实密钥、数据库、私信、用户上传文件或包含个人信息的截图。公开源代码不等于可以把本地开发服务直接放到公网；部署边界见 [部署说明](docs/DEPLOYMENT.md)。涉及凭证泄露或可利用的安全问题，请使用仓库 Security 页的私密报告入口（如果已启用），不要在公开 Issue 中贴密钥或真实用户数据。

提交贡献表示你同意自己的贡献按本仓库 MIT 许可证发布。暂不要求额外 CLA。
