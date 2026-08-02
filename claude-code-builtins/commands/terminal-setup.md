# /terminal-setup

| Field | Value |
|---|---|
| Description | Enable Option+Enter key binding for newlines and disable the audible bell (skipped in screen-reader mode) |
| Aliases | — |
| Argument | — |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
,TDy={type:"local-jsx",name:"terminal-setup",get description(){if(Z.terminal==="Apple_Terminal")return"Enable Option+Enter key binding for newlines and disable the audible bell (skipped in screen-reader mode)";if(Z.terminal!==null&&Object.hasOwn(XYd,Z.terminal))return`Check terminal setup (Shift+Enter is natively supported in ${XYd[Z.terminal]})`;if(process.env
```
