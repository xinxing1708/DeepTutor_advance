"""Build version-specific frontend patches; apply with manage_frontend.py."""
from pathlib import Path
import hashlib
import json
import runpy
IMAGE_PATCH = runpy.run_path(str(Path(__file__).resolve().parent.parent / "frontend_images/build_patch.py"))

ROOT = Path(__file__).resolve().parent
VERSION = "1.6.14"
NAMES = ["3450-849cf5416215cc1f.js", "1551-18d1afe69149078f.js", "5454-4d40eaa9bc3b8f82.js", "5750-4bc9c47d51f58f2e.js"]


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one patch anchor: {old[:100]}")
    return source.replace(old, new, 1)


def build(name, source):
    if name in IMAGE_PATCH["IMAGE_CHUNKS"]:
        return IMAGE_PATCH["transform"](name, source)
    if name.startswith("5454-"):
        # Only trace events belong in process disclosures. Ordinary answer
        # segments remain visible even when a tool follows the teaching.
        source = replace_once(source,
            'if(e.has(s)){r(),t.push({kind:"answer",key:a.key,segment:a});return}n.push(a)',
            'if("text"===a.kind||e.has(s)){r(),t.push({kind:"answer",key:a.key,segment:a});return}n.push(a)')
        # History previews omit token events and reconstruct the stored body.
        # Tool offsets are not Markdown boundaries; only interactive cards
        # need to split that body to preserve their position in the message.
        source = replace_once(source,
            'let n=s.get(t);void 0!==n?d(function(e,t)',
            'let n="trace"===e.kind?void 0:s.get(t);void 0!==n?d(function(e,t)')
        library = (ROOT / "continuation.cjs").read_text(encoding="utf-8")
        source = replace_once(source, ".push([[5053,5454],{", ".push([[5053,5454],{714014:(module,exports,require)=>{" + library + "},")
        source = replace_once(source, "n.d(t,{ah:()=>ta,ru:()=>e0});var r=", "n.d(t,{ah:()=>ta,ru:()=>e0});var dtContinueLib=n(714014),r=")
        source = replace_once(source, "()=>(0,V.a)(e,b),[e,b]", "()=>{let selected=(0,V.a)(e,b);return {...selected,messages:dtContinueLib.merge(selected.messages)}},[e,b]")
        source = replace_once(source,
            'L=()=>{let t=b.trim();t&&t!==e.content?"number"==typeof e.id&&(i?.(e.id,t),v(!1)):T()}',
            'L=()=>{let t=b.trim();if(!t||!B)return;i?.(e.id,t),v(!1)}')
        source = replace_once(source, 'disabled:!b.trim()||b.trim()===e.content', 'disabled:!b.trim()||!B')
        source = replace_once(source,
            '()=>"deep_question"!==e.capability?null:_?(0,W.i_)(_.metadata):(0,W.Ul)(e.events??[])',
            '()=>"deep_question"!==e.capability?null:dtContinueLib.quizSegments(e).flatMap(segment=>dtContinueLib.quizQuestions(segment))')
        source = replace_once(source,
            '(0,r.jsx)(eV,{questions:j,sessionId:a,turnId:w,language:i})',
            "(0,r.jsx)('div',{className:'space-y-3',children:dtContinueLib.quizSegments(e).map(segment=>{let result=segment.events?.find(event=>event.type==='result');let questions=result?(0,W.i_)(result.metadata):(0,W.Ul)(segment.events??[]);return questions?.length?(0,r.jsx)(eV,{questions,sessionId:a,turnId:(0,W.Ld)(segment.events??[]),language:i},segment.id):null})})")
    elif name.startswith("5750-"):
        source = replace_once(source,
            'V(i,void 0,void 0,void 0,void 0,{parentMessageId:s.parentMessageId??null},void 0,void 0,void 0)',
            'V(i,void 0,void 0,void 0,void 0,{parentMessageId:s.parentMessageId??null,requestSnapshotOverride:s.requestSnapshot?{...s.requestSnapshot,content:i,masteryAnswer:null,masterySkip:null}:void 0},void 0,void 0,void 0)')
    elif name.startswith("3450-"):
        source = replace_once(source, "S=a(78788),j=a(55454)", "S=a(78788),dtContinue=a(714014),dtBranches=a(76226),j=a(55454)")
        source = replace_once(source, "sW=(0,p.useCallback)(()=>{et()},[et]),sz=", """sW=(0,p.useCallback)(()=>{et()},[et]),dtTarget=(0,p.useMemo)(()=>dtContinue.target(dtBranches.a(W.messages,W.selectedBranches).messages,ag?ar:void 0),[W.messages,W.selectedBranches,ag,ar]),dtSendContinuation=(0,p.useCallback)(async()=>{
          if(!dtTarget||W.isStreaming||n3)return;
          try {
            if(tg.current?.key===W.sessionKey)await tg.current.pending;
            const {text,snapshot}=dtContinue.request(dtTarget);
            await Z(text,[],void 0,void 0,void 0,{parentMessageId:dtTarget.parentMessageId,requestSnapshotOverride:snapshot});
            nY.current=true;
          } catch(error) {(0,eC.notify)(error instanceof Error?error.message:I('Action failed'),{tone:'error'})}
        },[dtTarget,W.isStreaming,W.sessionKey,n3,Z,I]),sz=""")
        source = replace_once(source, "onToggleMemoryFile:re,onSend:s$,", "onToggleMemoryFile:re,canContinue:!!dtTarget&&!n3,onContinue:dtSendContinuation,canRetry:W.lastTurnFailed&&!dtTarget&&!n3,onRetry:sW,onSend:s$,")
        source = replace_once(source, "(0,eq.vh)(W.messages,W.selectedBranches)", "(0,eq.vh)(dtContinue.merge(dtBranches.a(W.messages,W.selectedBranches).messages),{})")
        source = replace_once(source, "(0,eG.i)(W.messages,{title:e})", "(0,eG.i)(dtContinue.merge(dtBranches.a(W.messages,W.selectedBranches).messages),{title:e})")
        source = replace_once(source, "},[W.messages]);return", "},[W.messages,W.selectedBranches]);return")
    else:
        source = replace_once(source, "onToggleMemoryFile:tb,onSend:ty,", "onToggleMemoryFile:tb,canContinue:dtCanContinue=false,onContinue:dtOnContinue,canRetry:dtCanRetry=false,onRetry:dtOnRetry,onSend:ty,")
        source = replace_once(source, "rw=t8||ry,rj=eG&&!eX,rN=rw&&!rj&&!rk,r_=rj?\"streaming\":rw?rk?\"blocked\":\"ready\":\"idle\"", "rw=t8||ry,rj=eG&&!eX,dtRecovery=!t8&&!et.length&&!eG&&(dtCanContinue?'continue':dtCanRetry?'retry':null),rN=rw&&!rj&&!rk,r_=rj?'streaming':dtRecovery??(rw?rk?'blocked':'ready':'idle')")
        source = replace_once(source, "()=>{rk?e1():rN&&rf(rn.current?.getValue()||\"\")},[rN,rf,rk,e1]", "()=>{dtRecovery==='continue'?dtOnContinue?.():dtRecovery==='retry'?dtOnRetry?.():rk?e1():rN&&rf(rn.current?.getValue()||'')},[dtRecovery,dtOnContinue,dtOnRetry,rN,rf,rk,e1]")
        source = replace_once(source, "rE=\"streaming\"===r_?tF(\"Stop generating\"):eX?tF(\"Send answer\"):tF(\"Send\")", "rE='continue'===r_?'继续生成':'retry'===r_?'重试上一轮':'streaming'===r_?tF('Stop generating'):eX?tF('Send answer'):tF('Send')")
        source = replace_once(source, "rz=\"blocked\"===r_?tF(\"Confirm settings on the right to send.\"):rE", "rz='continue'===r_?'从原回答末尾继续生成':'blocked'===r_?tF('Confirm settings on the right to send.'):rE")
        source = replace_once(source, '${eH[r_]}`,"aria-label":rE', '${eH[r_===\'continue\'||r_===\'retry\'?\'ready\':r_]} `,\'data-continuation-action\':r_,"aria-label":rE'.replace(']} `', ']}`'))
        old_icon = "(0,a.jsx)(N.A,{size:16,strokeWidth:2.5,className:`col-start-1 row-start-1 transition-[opacity,transform] duration-200 ${\"streaming\"===r_?\"scale-50 opacity-0\":\"scale-100 opacity-100\"}`})"
        source = replace_once(source, old_icon, "'continue'===r_?(0,a.jsx)('svg',{width:16,height:16,viewBox:'0 0 24 24','aria-hidden':true,className:'col-start-1 row-start-1 translate-x-px',children:(0,a.jsx)('path',{d:'M7 4v16l13-8z',fill:'currentColor'})}):" + old_icon)
    return IMAGE_PATCH["transform"](name, source)


def main():
    source_root = ROOT / ("upstream-" + VERSION)
    patched_root = ROOT / ("patched-" + VERSION)
    patched_root.mkdir(exist_ok=True)
    records = []
    for name in NAMES + IMAGE_PATCH["IMAGE_CHUNKS"]:
        original = (source_root / name).read_bytes()
        patched = build(name, original.decode("utf-8")).encode("utf-8")
        (patched_root / name).write_bytes(patched)
        records.append({"path": ".next/static/chunks/" + name,
                        "upstream_sha256": hashlib.sha256(original).hexdigest(),
                        "patched_sha256": hashlib.sha256(patched).hexdigest()})
    references = ROOT / "references.json"
    if references.exists():
        for relative in json.loads(references.read_text(encoding="utf-8")):
            snapshot = "references/" + relative
            original = (source_root / snapshot).read_bytes()
            patched = original
            for name in NAMES + IMAGE_PATCH["IMAGE_CHUNKS"]:
                if name == IMAGE_PATCH["IMAGE_CHUNKS"][2]:
                    replacement = IMAGE_PATCH["BOOTSTRAP_ALIAS"]
                elif name in IMAGE_PATCH["CHUNK_ALIASES"]:
                    replacement = IMAGE_PATCH["CHUNK_ALIASES"][name]
                else:
                    replacement = name + "?dt_continue=20261014images"
                patched = patched.replace(name.encode(), replacement.encode())
            output = patched_root / snapshot
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(patched)
            records.append({"path": relative, "snapshot": snapshot,
                            "upstream_sha256": hashlib.sha256(original).hexdigest(),
                            "patched_sha256": hashlib.sha256(patched).hexdigest()})
    aliases = {**IMAGE_PATCH["CHUNK_ALIASES"], IMAGE_PATCH["IMAGE_CHUNKS"][2]: IMAGE_PATCH["BOOTSTRAP_ALIAS"]}
    for original_name, alias in aliases.items():
        alias_bytes = (patched_root / original_name).read_bytes()
        (patched_root / alias).write_bytes(alias_bytes)
        records.append({"path": ".next/static/chunks/" + alias, "added": True,
                        "patched_sha256": hashlib.sha256(alias_bytes).hexdigest()})
    for legacy, current in IMAGE_PATCH["LEGACY_ALIASES"].items():
        alias_bytes = (patched_root / current).read_bytes()
        (patched_root / legacy).write_bytes(alias_bytes)
        records.append({"path": ".next/static/chunks/" + legacy, "added": True,
                        "patched_sha256": hashlib.sha256(alias_bytes).hexdigest()})
    previous_manifest = ROOT / ("previous-manifest-" + VERSION + ".json")
    if previous_manifest.exists():
        previous = {record["path"]: record for record in json.loads(previous_manifest.read_text(encoding="utf-8"))["files"]}
        for record in records:
            if record.get("added"):
                if record["path"] in previous:
                    record["previous_sha256"] = previous[record["path"]]["patched_sha256"]
                continue
            record["previous_sha256"] = previous.get(record["path"], record)["patched_sha256"] if record["path"] in previous else record["upstream_sha256"]
    (ROOT / ("frontend-manifest-" + VERSION + ".json")).write_text(
        json.dumps({"version": VERSION, "files": records}, indent=2), encoding="utf-8")
    print(f"Built {len(records)} version-specific frontend patches")


if __name__ == "__main__":
    main()

