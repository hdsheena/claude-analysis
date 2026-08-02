# /review

| Field | Value |
|---|---|
| Description | Review a GitHub pull request; for your working diff use /code-review |
| Aliases | — |
| Argument | [pr number] |
| Availability | — |
| Hidden | no |
| Enabled | yes |
| Immediate | no |
| Non-interactive | no |

Extracted definition (raw snippet from the built-in command registry):

```js
nce implications
- Test coverage
- Security considerations

Format your review with clear sections and bullet points.`,dDy,xYd,IYd,BFo;var wqs=S(()=>{pt();Vlt();dDy={type:"prompt",name:"review",description:"Review a GitHub pull request; for your working diff use /code-review",argumentHint:"[pr number]",progressMessage:"reviewing pull request",contentLength:0,source:"builtin",async getPromptForCommand(e){let[t="",...r]=e.trim().split(/\\s+/),n=t.replaceAll("`","").replace(/^#/,"");return[{type:"text",text:n?uDy(n,r.j
```
