# 精通路线完成判定

此 1.6.14 宿主补丁增强精通路线的多考点证据、答题门槛、选择题文字答案处理、简答归一化与模块完成状态校验。它不重写已有学习记录。

运行前先备份 DeepTutor 安装。按 [版本化补丁说明](../PATCH-MANAGEMENT.md) 执行检查、应用和回退：

```powershell
python extensions/mastery_completion/manage_integration.py check
python extensions/mastery_completion/manage_integration.py apply
```

独立测试位于 `tests/`；本目录中的官方补丁快照还包括适配版本的宿主测试。更新 DeepTutor 后须基于新版重新审查，不能直接复用 1.6.14 文件。
