# 图片上下文与 Mermaid 渲染

前端组件补充聊天中的图片上下文，并改进题卡和 Markdown 正文里的 Mermaid 图表渲染。

```powershell
python extensions/chat_continuation/build_patch.py
python extensions/chat_continuation/manage_frontend.py check
```

图片与聊天续答共享前端补丁构建器及文件清单。应用前先校验整组清单，停止运行中的 DeepTutor 后应用，之后重新加载页面。源图和图表测试数据均为合成内容；没有随发布包提交个人附件。
