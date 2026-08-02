# /branch

| Field | Value |
|---|---|
| Description | Create a branch of the current conversation at this point |
| Aliases | — |
| Argument | [name] |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var jOy,fXd;var mXd=S(()=>{jOy={type:"local-jsx",name:"branch",description:"Create a branch of the current conversation at this point",argumentHint:"[name]",load:()=>Promise.resolve().then(() => (Kqs(),zqs))},fXd=jOy});var gXd={};tt(gXd,{spawnForkFromDirective:()=>Dpn,deriveForkName:()=>hXd});async function Dpn(e,t,r,n){if(t.getAppState().endedByModel)return pe("subagent_launch","subage
```
