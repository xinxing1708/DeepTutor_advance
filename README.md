# DeepTutor 本地增强组件

本仓库整理了一组面向 DeepTutor 1.6.14 的本地增强扩展与版本化补丁，覆盖学习者画像、精通判定、扫描 PDF OCR、聊天续答与测验上下文、跨会话检索与错题复盘、Markdown 图片/Mermaid 渲染、上下文预算和启动扫描优化。

这些组件是对 DeepTutor 的补充，不包含 DeepTutor 完整应用，也不会自动迁移补丁到其他版本。安装前请确认目标版本与补丁清单一致，并先备份宿主代码。

## 隐私与发布范围

- 学习者画像是运行时保存在本机设置目录中的功能。本仓库只有通用代码和合成测试，不含任何真实画像内容或示例副本。
- 聊天检索/错题复盘扩展只在运行时访问当前 DeepTutor 工作区的数据；仓库不含聊天数据库、聊天导出、学习进度或真实用户测试记录。
- 不包含知识库原文、向量索引、OCR 缓存、嵌入模型或模型权重；EmbeddingGemma 相关组件也不在本仓库中。
- 不包含 API key、登录令牌、模型目录、`.env` 文件、运行日志或本机诊断材料。
- 所有文件均以新 Git 历史发布；原工作区提交历史未复制到本仓库。

## 组件

| 目录 | 用途 |
|---|---|
| `extensions/learner_profile` | 在相关对话中可选询问学习偏好；仅在明确同意后将对话中已有的原文事实保存到本机画像 |
| `extensions/mastery_completion` | 精通路线多考点证据门槛、选择题/简答题判定与完成状态约束 |
| `extensions/pdf_ocr` | 扫描 PDF 本地 OCR、可恢复分页缓存及知识库页码映射补丁 |
| `extensions/learning_context` | 将通用学习上下文一致注入常规聊天、工具和精通路线请求 |
| `extensions/learning_continuity` | 当前工作区会话检索、分支核验与错题解析复盘工具 |
| `extensions/quiz_context` | 将当前分支中已保存的测验题干、选项和作答上下文提供给后续回合 |
| `extensions/chat_continuation` | 聊天续答、编辑后保留请求配置重发、自定义测验续题和教学正文显示修复 |
| `extensions/frontend_images` | 聊天图片上下文和 Mermaid 图表渲染的前端补丁 |
| `extensions/context_budget` | 调整长对话上下文构建预算的版本化宿主补丁 |
| `extensions/startup_performance` | 减少插件扫描时不必要的安装文件遍历 |

简要改进记录见 [ENHANCEMENTS.md](ENHANCEMENTS.md)。各组件的 README 说明安装环境、检查和回退方式。

## 安装原则

1. 使用与补丁匹配的 DeepTutor 版本和它自己的 Python 环境。
2. 阅读对应扩展 README；需要宿主文件补丁时，先停止 DeepTutor，再运行该组件的 `check`。
3. 只有校验状态与清单完全匹配时才应用补丁。未知版本或未知文件状态应停止操作并重新适配。
4. 画像、聊天数据库、学习进度、知识库和 OCR 缓存均由使用者本机应用管理；不要把它们复制进代码仓库。

本仓库的已记录宿主快照针对 DeepTutor 1.6.14。未来升级需对比新版官方文件并重新生成对应快照，不应直接覆盖。

## 验证

画像扩展测试使用临时目录和合成对话。其他可移植的 Python/Node 测试位于相应扩展目录；部分原始回归依赖真实本地会话数据，因此未随发布版提供。
