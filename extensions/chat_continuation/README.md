# 聊天续答、编辑与测验续题

前端补丁支持从已中断回答的原文末尾继续生成、编辑原消息后保留当时的请求设置、按剩余题数继续自定义测验，并正确显示完整教学正文和交互题卡。它保留 DeepTutor 的分支消息结构。

先用 DeepTutor 1.6.14 的前端文件运行补丁构建和校验：

```powershell
python extensions/chat_continuation/build_patch.py
python extensions/chat_continuation/manage_frontend.py check
```

确认资源状态后停止应用再执行 `apply`；`restore` 将资源恢复到相符清单记录的上游字节。可以通过 `--target` 使用独立前端副本。现有浏览器页面需重新加载前端资源。

前端快照可能包含 DeepTutor 发行包中的代码，发行包自带的许可文本位于 `third_party/deeptutor/`。请只对相符版本使用该快照，并在上游升级后重新适配。
