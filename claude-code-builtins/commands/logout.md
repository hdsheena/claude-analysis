# /logout

| Field | Value |
|---|---|
| Description | Sign out from your Anthropic account |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | ()=>!Z.DISABLE_LOGOUT_COMMAND |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var bKd;var SKd=S(()=>{vr();bKd={type:"local-jsx",name:"logout",description:"Sign out from your Anthropic account",isEnabled:()=>!Z.DISABLE_LOGOUT_COMMAND,fleetHostCall:async(e)=>{let{fleetHostLogout:t}=await Promise.resolve().then(() => (fpn(),yKd));return t(e)}}});var fIy,TKd;var EKd=S(()=>{vr();fIy={type:"local-jsx",
```
