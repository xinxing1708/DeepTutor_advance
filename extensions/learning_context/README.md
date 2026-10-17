# 全局教学上下文

将通用教学上下文放在聊天系统指令之前，使普通对话和精通路线都能收到一致的教学规则，同时保留原有 system 指令、摘要与多模态消息。具体文本由使用者在本机配置；仓库只含通用集成代码和版本快照。

```powershell
python extensions/learning_context/manage_integration.py check
python extensions/learning_context/manage_integration.py apply
```

写入宿主文件前先停止 DeepTutor。回退时执行 `restore`，再重新启动。检查与应用规则见 [版本化补丁说明](../PATCH-MANAGEMENT.md)。此版本适配 DeepTutor 1.6.14；本机教学上下文、角色配置和画像均不包含在此发布版中。
