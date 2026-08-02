# /background

| Field | Value |
|---|---|
| Description | Send this session to the background and free the terminal |
| Aliases | /bg |
| Argument | [prompt] |
| Availability | — |
| Hidden | no |
| Enabled | ()=>!0 |
| Immediate | (e)=>!e.trim() |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var eLy,tLy;var Tep=S(()=>{eLy={type:"local-jsx",name:"background",aliases:["bg"],description:"Send this session to the background and free the terminal",argumentHint:"[prompt]",immediate:(e)=>!e.trim(),isEnabled:()=>!0},tLy=eLy});function rLy(){return process.env.CLAUDE_JOB_DIR}async function LBo(e){M("tengu_bg_agent_action",{action:Te("stop"),source:fe(e),jobSessionId:wr(kt())});let t
```
