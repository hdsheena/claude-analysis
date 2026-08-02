# /export

| Field | Value |
|---|---|
| Description | Export the current conversation to a file or clipboard |
| Aliases | — |
| Argument | [filename] |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
);var HPy,bjs;var XQd=S(()=>{HPy={type:"local-jsx",name:"export",description:"Export the current conversation to a file or clipboard",argumentHint:"[filename]",requires:{ink:!0}},bjs=HPy});var ZQd={};tt(ZQd,{call:()=>LPy});async function LPy(e,t){let r=e.trim();if(!r||RMe.includes(r)){let s=t.getAppState();return{type:"text",value:`${Lcn(s)}
${QQd}`}}if(roe.includes(r))return{type:"text",
```
