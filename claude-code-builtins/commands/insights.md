# /insights

| Field | Value |
|---|---|
| Description | Generate a report analyzing your Claude Code sessions |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
tisfied","likely_satisfied","satisfied","happy","unsure"],RLy=["not_achieved","partially_achieved","mostly_achieved","fully_achieved","unclear_from_transcript"];LLy={type:"prompt",name:"insights",description:"Generate a report analyzing your Claude Code sessions",contentLength:0,progressMessage:"analyzing your sessions",source:"builtin",async getPromptForCommand(e){let t=!1,r=[],n=!1,{insights:o,htmlPath:i,data:s,remoteStats:a}=await Hep({collectRemote:t}),l=`file://${i}`,u=[s.total_sessions_scanned&&s.total_sessio
```
