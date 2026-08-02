# /upgrade

| Field | Value |
|---|---|
| Description | Upgrade to Max for higher rate limits and more Opus |
| Aliases | — |
| Argument | — |
| Availability | claude-ai |
| Hidden | no |
| Enabled | Lye |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var zPy,dDe;var Ajs=S(()=>{OQt();zPy={type:"local-jsx",name:"upgrade",description:"Upgrade to Max for higher rate limits and more Opus",availability:["claude-ai"],isEnabled:Lye},dDe=zPy});async function vZd(e){return Vc("api_admin_request_create",async()=>{let t=await Hi.post("/api/oauth/organizations/:orgUUID/admin_requests",e,{auth:"teleport-org"});if(!t.ok)throw Error(t.reason==="no-auth"?
```
