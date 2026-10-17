# 长对话上下文预算

调整 DeepTutor 会话上下文构建中的历史预算与重建上限，以支持更长的学习对话和摘要。此组件只包含针对 DeepTutor 1.6.14 的单文件版本化补丁。

```powershell
python extensions/context_budget/manage_integration.py check
python extensions/context_budget/manage_integration.py apply
```

应用或回退宿主代码前先停止 DeepTutor。升级后须核实新版上下文构建逻辑和哈希清单，不能强制覆盖未知文件。
