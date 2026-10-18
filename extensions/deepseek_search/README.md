# DeepSeek 官方搜索提供方

为 DeepTutor 1.6.14 增加一个内置搜索适配器，使“提供方”页的 DeepSeek 官方配置同时具备搜索能力：搜索设置可以复用已有的 DeepSeek 连接与同一把官方 API Key，不需要另配第三方搜索服务。

## 内容

- 新增 `services/search/providers/deepseek.py`：调用 DeepSeek 官方 Search API（`POST /v1/tools/search`），把结构化结果映射为统一的搜索结果与引用，并交给既有 consolidation 生成答案。
- 搜索提供方表新增 `deepseek`：需要 API Key、不需要 base URL；缺 Key 时明确提示，不静默改用其他搜索引擎；运行期失败仍沿用既有回退链。
- `services/provider_registry.py` 的原生 `web_search` 白名单收敛为 `deepseek-v4-pro`：官方文档说明 Responses 服务端 `web_search` 仅在 v4-pro 支持、deepseek-flash 会忽略，旧白名单会让本地搜索工具被替换成被忽略的服务端工具。
- 前端资源无需改动：提供方标签、搜索页下拉与连接选择都由后端提供方表驱动。

宿主文件共 4 个（相对安装包内的 `deeptutor` 包目录），其中搜索适配器为新增文件；不与其他补丁共享文件。

## 行为说明

- 搜索提供方只有“最大结果数”配置（映射为 Search API 的 `count`，1–50），没有“搜索模型”这一层。
- 连接与搜索配置通过运行期 provider_ref 共享凭据，搜索配置可只保留一把 Key。
- 搜索结果包含标题、链接、短摘要、长摘要、日期、站点、权威性与排序分；默认不抓取网页正文，需要时可用 `need_content` 选项。
- DeepSeek 模型 id 建议使用 `deepseek-flash` 或 `deepseek-v4-pro`；旧名 `deepseek-v4-flash` 仍可调用但已映射到 Flash。

## 管理

从 DeepTutor 安装根目录运行，使用安装环境中的 Python：

```powershell
python extensions/deepseek_search/manage_integration.py check
python extensions/deepseek_search/manage_integration.py apply
python extensions/deepseek_search/manage_integration.py restore
```

应用或回退宿主代码前先停止 DeepTutor。清单绑定 1.6.14；升级 DeepTutor 后必须按新版宿主重新审查并制作新快照，不能照抄本组件快照。`restore` 会删除新增的适配器文件并恢复其余三个宿主文件。

## 验证

离线回归只使用 mock 响应，不联网、不需要真实 Key：

```powershell
python extensions/deepseek_search/tests/test_deepseek_search_provider.py
```

真实搜索联调需在设置中配置 DeepSeek 官方 API Key；该路径已在 1.6.14 上由使用者完成，搜索测试返回真实结果，默认搜索引擎切换为 DeepSeek。Search 按成功请求计费（每 1000 次 5 元），失败、空结果与超时不计费；账号级 QPS 为 5。
