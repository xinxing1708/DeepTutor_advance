"""Compose image rendering with the existing version-specific frontend patch."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
IMAGE_CHUNKS = ["9347.ef125ab74f4fc87d.js", "9797-994ed73175354c60.js", "webpack-b9a1eccb0c94dba8.js", "6896-441cf43825adeefb.js", "7306.9daf7ebd715d14a3.js"]
BOOTSTRAP_ALIAS = "webpack-b9a1eccb0c94dba8-diagrams20261015r3.js"
CHUNK_ALIASES = {
    name: name[:-3] + "-images20261014.js"
    for name in IMAGE_CHUNKS[:2]
}
# 5454 embeds chat_continuation; a content change needs a new immutable name.
CHUNK_ALIASES["5454-4d40eaa9bc3b8f82.js"] = "5454-4d40eaa9bc3b8f82-continue20261015.js"
CHUNK_ALIASES[IMAGE_CHUNKS[0]] = "9347.ef125ab74f4fc87d-diagrams20261015r2.js"
CHUNK_ALIASES[IMAGE_CHUNKS[3]] = "6896-441cf43825adeefb-diagrams20261015r2.js"
CHUNK_ALIASES[IMAGE_CHUNKS[4]] = "7306.9daf7ebd715d14a3-diagrams20261015r3.js"
# Already-rendered pages and the running server still reference these names;
# they receive the same bytes as the current aliases.
LEGACY_ALIASES = {
    "webpack-b9a1eccb0c94dba8-diagrams20261015r2.js": BOOTSTRAP_ALIAS,
    "5454-4d40eaa9bc3b8f82-images20261014.js": CHUNK_ALIASES["5454-4d40eaa9bc3b8f82.js"],
    "webpack-b9a1eccb0c94dba8-images20261014r2.js": BOOTSTRAP_ALIAS,
    "webpack-b9a1eccb0c94dba8-continue20261015.js": BOOTSTRAP_ALIAS,
    "9347.ef125ab74f4fc87d-images20261014.js": CHUNK_ALIASES[IMAGE_CHUNKS[0]],
    "webpack-b9a1eccb0c94dba8-diagrams20261015.js": BOOTSTRAP_ALIAS,
    "9347.ef125ab74f4fc87d-diagrams20261015.js": CHUNK_ALIASES[IMAGE_CHUNKS[0]],
    "6896-441cf43825adeefb-diagrams20261015.js": CHUNK_ALIASES[IMAGE_CHUNKS[3]],
}


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one image patch anchor: {old[:100]}")
    return source.replace(old, new, 1)


def transform(name, source):
    if name == IMAGE_CHUNKS[4]:
        # Chat Markdown loads 57306 from 7306; cards/viz load its duplicate
        # from 6896. Patch both and preserve 7306's theme/storage modules.
        start = source.index("57306:")
        end = source.index(",68929:", start)
        return source[:start] + (ROOT / "mermaid_viewer.js").read_text(encoding="utf-8").strip() + source[end:]
    if name == IMAGE_CHUNKS[3]:
        start = source.index("57306:")
        end = source.index("}}]);", start)
        return source[:start] + (ROOT / "mermaid_viewer.js").read_text(encoding="utf-8").strip() + source[end + 1:]
    if name == IMAGE_CHUNKS[0]:
        start = source.index("59347:")
        end = source.index(",84559:", start)
        return source[:start] + (ROOT / "inline_markdown.js").read_text(encoding="utf-8").strip() + source[end:]
    if name == IMAGE_CHUNKS[1]:
        start = source.index("function v({attachments:")
        end = source.index("function y({name:", start)
        source = source[:start] + (ROOT / "context_provider.js").read_text(encoding="utf-8").strip() + source[end:]
        start = source.index("function j({name:")
        end = source.index("},54172:", start)
        # Keep the module's closing brace after replacing the image function.
        return source[:start] + (ROOT / "context_image.js").read_text(encoding="utf-8").strip() + source[end:]
    if name == IMAGE_CHUNKS[2]:
        # Refresh lazy chunks as well as the initial scripts after this update.
        # Next's trusted-script URL helper encodes '?' as part of the pathname.
        # Use new filenames so both its lazy loader and browser cache agree.
        lazy_aliases = {
            chunk_id: "static/chunks/" + CHUNK_ALIASES[name]
            for chunk_id, name in [(5454, "5454-4d40eaa9bc3b8f82.js"), (9347, IMAGE_CHUNKS[0]), (9797, IMAGE_CHUNKS[1]), (6896, IMAGE_CHUNKS[3]), (7306, IMAGE_CHUNKS[4])]
        }
        return replace_once(source, ',i.miniCssF=', ',i.u=(original=>e=>(' + json.dumps(lazy_aliases) + ')[e]??original(e))(i.u),i.miniCssF=')
    if name.startswith("5454-"):
        source = replace_once(source,
            'function e5({attachments:e,events:t,onOpen:n}){let{t:a}=(0,u.Bd)(),i=(0,s.useMemo)(()=>(0,z.ry)(e,t),[e,t]);',
            'function e5({attachments:e,events:t,onOpen:n}){let{t:a}=(0,u.Bd)(),imageContext=(0,z.Gm)(),i=(0,s.useMemo)(()=>(0,z.ry)(e,t).filter(file=>!file.mime_type?.startsWith("image/")||!imageContext?.loadedImages?.has(file.url)),[e,t,imageContext?.loadedImages]);')
        source = replace_once(source, 'children:(0,r.jsx)(e4,{msg:e,', 'children:(0,r.jsxs)(r.Fragment,{children:[(0,r.jsx)(e4,{msg:e,')
        source = replace_once(source,
            'masteryGrades:P,masterySkips:U})}),(0,r.jsx)(e5,{attachments:e.attachments??[],events:e.events,onOpen:x}),',
            'masteryGrades:P,masterySkips:U}),(0,r.jsx)(e5,{attachments:e.attachments??[],events:e.events,onOpen:x})]})}),')
    return source
