# /clear

| Field | Value |
|---|---|
| Description | Start a new session with empty context; previous session stays on disk (resumable with /resume) |
| Aliases | /reset, /new |
| Argument | [name] |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | yes |

Extracted definition (raw snippet from the built-in command registry):

```js
);var Tly,BPo;var zNd=S(()=>{Tly={type:"local",name:"clear",description:"Start a new session with empty context; previous session stays on disk (resumable with /resume)",argumentHint:"[name]",aliases:["reset","new"],supportsNonInteractive:!0,thinClientDispatch:"post-text",load:()=>Promise.resolve().then(() => (VNd(),GNd))},BPo=Tly});function KNd(e){if(om())return;return e.standaloneAg
```
