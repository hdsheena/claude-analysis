# /login

| Field | Value |
|---|---|
| Description | Switch Anthropic accounts / Sign in with your Anthropic account |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | ()=>!Z.DISABLE_LOGIN_COMMAND |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var uBd=()=>({type:"local-jsx",name:"login",get description(){return Tno()?"Switch Anthropic accounts":"Sign in with your Anthropic account"},isEnabled:()=>!Z.DISABLE_LOGIN_COMMAND,fleetHostCall:async({login:e})=>e()});var dBd=S(()=>{To();vr()});var ugr="subscription-switch",AHo=3;async function RHo(){try{await xU(async()=>{let e=await Hi.post("/api/oauth/account/grove
```
