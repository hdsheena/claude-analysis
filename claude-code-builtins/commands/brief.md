# /brief

| Field | Value |
|---|---|
| Description | Toggle brief-only mode |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | ()=>cHy().enable_slash_command |
| Immediate | yes |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
;uHy={type:"local-jsx",name:"brief",description:"Toggle brief-only mode",isEnabled:()=>cHy().enable_slash_command,immediate:!0,load:()=>Promise.resolve({async call(e,t){let n=!t.getAppState().isBriefOnly;if(n&&!Con())return M("tengu_brief_mode_toggled",{enabled:!1,gated:!0,source:Te("slash_command")}),e("Brief tool is not enabled for your account",{display:"sys
```
