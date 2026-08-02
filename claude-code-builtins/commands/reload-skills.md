# /reload-skills

| Field | Value |
|---|---|
| Description | Pick up skills added or changed on disk during this session |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | yes |

Extracted definition (raw snippet from the built-in command registry):

```js
);var fPy,uBo;var VXd=S(()=>{fPy={type:"local",name:"reload-skills",description:"Pick up skills added or changed on disk during this session",supportsNonInteractive:!0,thinClientDispatch:"post-text",load:()=>Promise.resolve().then(() => (GXd(),WXd))},uBo=fPy});var zXd={};tt(zXd,{call:()=>mPy});async function mPy(e,t){return t.onQueryEvent?.({type:"open_message_selector"}),{type:"skip"
```
