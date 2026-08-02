# Claude Code built-in slash commands

Extracted from `/opt/homebrew/bin/claude` using `extract_commands.py`. These are the commands baked into the Claude Code CLI itself — not plugins, skills, or project commands.

103 commands. Each has a detail page in `commands/`.

| Command | Aliases | Description |
|---|---|---|
| /add-dir | — | Add a new working directory |
| /advisor | — | Let Claude consult a stronger model at key moments |
| /agents | — | (removed) Ask Claude to create/manage subagents, or edit .claude/agents/ |
| /artifacts | — | Browse your published and shared artifacts |
| /auto-mode-setup | — | Set up and customise auto mode — environment context, plus optional rule tweaks |
| /autocompact | — | Set how full the context gets before auto-summarizing |
| /autofix-pr | — | Monitor and autofix any issues with the current PR |
| /background | /bg | Send this session to the background and free the terminal |
| /branch | — | Create a branch of the current conversation at this point |
| /brief | — | Toggle brief-only mode |
| /btw | — | Ask a quick side question without interrupting the main conversation |
| /bug | /share | Report a bug or share your conversation |
| /cd | — | Move this session to a new working directory |
| /chrome | — | Open Claude in Chrome settings |
| /clear | /reset, /new | Start a new session with empty context; previous session stays on disk (resumable with /resume) |
| /color | — | Set the prompt bar color for this session |
| /compact | — | Free up context by summarizing the conversation so far |
| /config | /settings | Open settings |
| /context | — | Show current context usage |
| /copy | — | Copy Claude's last response to clipboard (or /copy N for the Nth-latest) |
| /daemon | — | Manage background services and routines |
| /design | — | Grant or revoke Claude agent access to your Design projects |
| /design-consent | — | Grant Claude agent access to your Design projects |
| /design-login | — | Authorize design-system access for /design-sync with your claude.ai account |
| /design-revoke | — | Revoke Claude agent access to your Design projects |
| /desktop | /app | Continue the current session in Claude Desktop |
| /diff | — | View uncommitted changes and per-turn diffs |
| /effort | — | Set effort level for model usage |
| /exit | /quit | Detach from this background session (it keeps running) / Exit the CLI |
| /export | — | Export the current conversation to a file or clipboard |
| /extra-usage | — | Renamed to /usage-credits |
| /fast | — | Toggle fast mode (Opus 5) |
| /feedback | /share | Send feedback to Anthropic or report a bug |
| /focus | — | Toggle focus view: just your prompt, summary, and response |
| /fork | — | Spawn a background agent that inherits the full conversation |
| /goal | — | Set a goal Claude checks before stopping |
| /heapdump | — | Dump the JS heap to ~/Desktop |
| /help | — | Show help and available commands |
| /hooks | — | View hook configurations for tool events |
| /ide | — | Manage IDE integrations and show status |
| /import | — | Import config from another AI coding agent |
| /init | — | Initialize new CLAUDE.md file(s) and optional skills/hooks with codebase documentation / Initialize a new CLAUDE.md file with codebase documentation |
| /insights | — | Generate a report analyzing your Claude Code sessions |
| /install | — | Install Claude Code native build |
| /install-github-app | — | Set up Claude GitHub Actions for a repository |
| /install-slack-app | — | Install the Claude Slack app |
| /keybindings | — | Open your keyboard shortcuts file |
| /login | — | Switch Anthropic accounts / Sign in with your Anthropic account |
| /logout | — | Sign out from your Anthropic account |
| /loops | — | List, create, and delete loops |
| /mcp | — | Manage MCP servers |
| /memory | — | Open a memory file in your editor |
| /mobile | /ios, /android | Show QR code to download the Claude mobile app |
| /model | — | Set the AI model for Claude Code |
| /passes | — | Share a free week of Claude Code with friends and earn usage credits |
| /pause-memory | /memory-pause, /toggle-memory | Pause automemory for this session |
| /permissions | /allowed-tools | Manage allow and deny tool permission rules |
| /plan | — | Enable plan mode or view the current session plan |
| /plugin | /plugins, /marketplace | Manage Claude Code plugins |
| /powerup | — | Discover Claude Code features through quick interactive lessons |
| /privacy-settings | — | View and update your privacy settings |
| /pro-trial-expired | — | Options shown when the Pro plan Claude Code trial has ended |
| /radio | — | Listen to Claude FM lo-fi radio |
| /rate-limit-options | — | Show options when rate limit is reached |
| /recap | — | Generate a one-line session recap now |
| /release-notes | — | View release notes |
| /reload-plugins | — | Activate pending plugin changes in the current session |
| /reload-skills | — | Pick up skills added or changed on disk during this session |
| /remote-control | /rc | Disconnect Remote Control / Control this session from your phone or claude.ai/code |
| /remote-env | — | Choose the default environment for cloud agents |
| /rename | /name | Rename the current conversation |
| /resume | /continue | Resume a previous conversation |
| /review | — | Review a GitHub pull request; for your working diff use /code-review |
| /rewind | /checkpoint, /undo | Restore the code and/or conversation to a previous point |
| /scroll-speed | — | Adjust mouse wheel scroll speed |
| /session | /remote | Show cloud session URL and QR code |
| /setup-bedrock | — | Reconfigure Amazon Bedrock authentication, region, or model pins |
| /setup-vertex | — | Reconfigure Google Vertex AI authentication, project, region, or model pins |
| /skill-doctor | — | Show which loaded skills are unused and costing context |
| /skills | — | List available skills |
| /status | — | Show Claude Code status including version, model, account, API connectivity, and tool statuses |
| /statusline | — | Set up Claude Code's status line UI |
| /stickers | — | Order Claude Code stickers |
| /stop | — | Stop this background session; transcript and worktree are kept |
| /subtask | — | Send a subagent off with your full context; its result comes back here |
| /tasks | /bashes | View and manage everything running in the background |
| /team-onboarding | — | Help teammates ramp on Claude Code with a guide from your usage |
| /teleport | /tp | Resume a Claude Code session from claude.ai |
| /terminal-setup | — | Enable Option+Enter key binding for newlines and disable the audible bell (skipped in screen-reader mode) |
| /theme | — | Change the theme |
| /tui | — | Set the terminal UI renderer (default | fullscreen) |
| /ultraplan | — | Draft an editable plan in Claude Code on the web ({dynamic}) · See {dynamic} |
| /ultrareview | — | Start a cloud agent that finds and verifies bugs in your branch ((dynamic: Ape()), (dynamic: J2e()) USD) · Runs in Claude Code on the web. See {dynamic} |
| /update | /restart | Switch to the latest version (conversation continues) |
| /upgrade | — | Upgrade to Max for higher rate limits and more Opus |
| /usage | /cost, /stats | Show session cost, plan usage, and activity stats |
| /usage-credits | — | Configure usage credits or request them from your admin when you hit a limit |
| /version | — | Show this session's version (autoupdate may have a newer one) |
| /voice | — | Toggle voice mode |
| /web-setup | — | Set up Claude Code on the web with your GitHub account |
| /wellbeing | /breaks, /break-reminder, /downtime | Configure optional break reminders and quiet-hours nudges |
| /workflow-launch-exec | — | Execute a server-launched workflow handoff (workflow_launch event sessions only) |
| /workflows | — | Browse running and completed workflows |

Notes:
- Hidden commands are flagged in their detail pages; they are usually internal.
- Descriptions containing `{dynamic}` are computed at runtime (e.g. include the current model or account state).
- Extraction is heuristic — it parses the minified JS bundle in the binary, so regenerate with `python3 extract_commands.py` after a Claude Code update.