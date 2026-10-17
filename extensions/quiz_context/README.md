# 测验上下文

此补丁为后续聊天提供当前分支中相关测验的完整题干、选项、作答和轮次信息，避免重复的题目编号串到其他测验。未作答题仍标记为未回答，不会提前暴露参考答案；显式从会话根部创建新分支时，不注入旧测验上下文。

```powershell
python extensions/quiz_context/manage_integration.py check
python extensions/quiz_context/manage_integration.py apply
```

此组件与 PDF OCR 共用两个宿主文件。应用前先检查两组清单，回退时先恢复测验补丁，再按 [PDF OCR 说明](../pdf_ocr/README.md) 恢复共享文件。具体校验规则见 [版本化补丁说明](../PATCH-MANAGEMENT.md)。

发布包刻意省略依赖本机聊天数据库的实时回归记录和数据库样本；没有提供可直接读取的聊天或知识库数据。
