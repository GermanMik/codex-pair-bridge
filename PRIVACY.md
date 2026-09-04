# Privacy

Codex PAIR Bridge runs locally. It sends model-list requests and the text supplied
to its ask tool to the PAIR endpoint configured by the user. PAIR may route that
text to connected model servers. Model answers return to Codex and are subject to
the user's Codex/OpenAI data settings.

The bridge has no analytics, advertising, developer-hosted relay, or telemetry.
It does not intentionally persist prompts or answers. It stores a local lock file
and uses uv's dependency cache. PAIR, model servers, Codex, and the operating system
may keep their own logs. First installation contacts package registries/runtime
download services to obtain dependencies.

Only send data you intend to share with your configured model servers and Codex.
The project maintainer does not receive your requests through this plugin.
