# /teleport

| Field | Value |
|---|---|
| Description | Resume a Claude Code session from claude.ai |
| Aliases | /tp |
| Argument | — |
| Availability | — |
| Hidden | !ii()||!ns("allow_remote_sessions") |
| Enabled | ()=>ii()&&ns("allow_remote_sessions") |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var _Dy,WYd;var GYd=S(()=>{Gu();To();_Dy={type:"local-jsx",name:"teleport",description:"Resume a Claude Code session from claude.ai",aliases:["tp"],isEnabled:()=>ii()&&ns("allow_remote_sessions"),get isHidden(){return!ii()||!ns("allow_remote_sessions")}},WYd=_Dy});function VYd({name:e,description:t,progressMessage:r,pluginName:n,pluginCommand:o,getPromptWhileMarketplaceIsPrivate:i}){return{type:"
```
