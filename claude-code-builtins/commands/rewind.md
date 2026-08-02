# /rewind

| Field | Value |
|---|---|
| Description | Restore the code and/or conversation to a previous point |
| Aliases | /checkpoint, /undo |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
var hPy,KXd;var YXd=S(()=>{hPy={description:"Restore the code and/or conversation to a previous point",name:"rewind",aliases:["checkpoint","undo"],argumentHint:"",type:"local",supportsNonInteractive:!1,load:()=>Promise.resolve().then(() => zXd)},KXd=hPy});var QXd={};tt(QXd,{performHeapDump:()=>tjs,captureMemoryDiagnostics:()=>XXd});async function XXd(e,t=0){let r=process.memoryUsage(),n=dBo.getHeapStatistics(),o=process.resourceUsage(),i=p
```
