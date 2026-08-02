# /heapdump

| Field | Value |
|---|---|
| Description | Dump the JS heap to ~/Desktop |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | yes |
| Enabled | ()=>ns("allow_heap_dump") |
| Immediate | no |
| Non-interactive | yes |

Extracted definition (raw snippet from the built-in command registry):

```js
);var bPy,tQd;var rQd=S(()=>{Gu();bPy={type:"local",name:"heapdump",description:"Dump the JS heap to ~/Desktop",isEnabled:()=>ns("allow_heap_dump"),isHidden:!0,supportsNonInteractive:!0,fleetHostCall:async({setInfo:e,setError:t})=>{e("Writing heap dump\\u2026");let{performHeapDump:r}=await Promise.resolve().then(() => (rjs(),QXd)),n=await r();if(n.success)e(`Heap dump written to ${n.heapPat
```
