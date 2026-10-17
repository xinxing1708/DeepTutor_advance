# 插件扫描优化

针对标准 Python wheel 安装包，若 RECORD 完整且没有 DeepTutor 插件清单，则跳过冗余逐文件存在性扫描；带清单的插件、缺失/空 RECORD 和自定义提供者仍沿用原检查路径。补丁不保留长期缓存，以便安装、更新和审批后的插件变化能即时生效。

```powershell
python extensions/startup_performance/manage_integration.py check
python extensions/startup_performance/manage_integration.py apply
```

更新宿主前停止 DeepTutor。独立验证脚本可用新的临时输出目录运行；不要复用或覆盖含诊断的目录。此补丁适配 1.6.14，升级时先检查上游是否已包含等价优化。
