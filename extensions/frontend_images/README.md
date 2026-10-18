# 图片上下文与 Mermaid 渲染

前端组件补充聊天中的图片上下文，并改进题卡和 Markdown 正文里的 Mermaid 图表渲染。

```powershell
python extensions/chat_continuation/build_patch.py
python extensions/chat_continuation/manage_frontend.py check
```

图片与聊天续答共享前端补丁构建器及文件清单。应用前先校验整组清单，停止运行中的 DeepTutor 后应用，之后重新加载页面。源图和图表测试数据均为合成内容；没有随发布包提交个人附件。

## Mermaid XML 解析修复

Mermaid 流程图标签由渲染库按 HTML 写入 `<foreignObject>`，其中的 `<br/>` 会被清洗成 HTML 空元素 `<br>`。查看器原先用 `DOMParser` 以 `image/svg+xml` 严格解析 `render()` 原始输出，得到 `parsererror` 文档却不检查，继续序列化后交给 React，于是含换行的图只显示局部内容并出现 XML 错误。

`mermaid_viewer.js` 现在：

1. `parseMermaidSvgFragment()` 在 detached HTML 容器中按 HTML 片段解析，让 `foreignObject` 集成点按 HTML 规则处理 XHTML 空元素，并校验唯一根元素是 SVG 命名空间的 `svg`；
2. 保留原尺寸与文字对比度处理；
3. `assertSerializedSvgIsValid()` 序列化后再用严格 XML 解析**验证**，失败即抛错，由现有 `catch` 进入错误与源码回退，不再把 `parsererror` 当图形渲染。

未改 `securityLevel: "strict"`、分图、缩放/拖动/主题行为，也未用正则替换 `<br>`。题卡（6896）与聊天正文（7306）两个入口由同一源文件经构建器生成，必须同时更新。

`test_diagrams.cjs` 断言两个入口都使用新解析链路、保留 strict 安全级别，且不再严格解析原始输出。回归验证另需真实浏览器：Node 测试不覆盖 `DOMParser` 与 HTML 片段解析行为。
