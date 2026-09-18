#!/usr/bin/env python3
"""Create the isolated Proto home template homes/proto-glm (gitignored).

Direct-provider shape (no proxy, so bench traffic never enters the production ledger):
  llmProviders.custom = OpenRouter with the key; selectedModel = custom::z-ai/glm-5.3-flash
Key source: $OPENROUTER_API_KEY. Never printed or read from a personal profile.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
key = os.environ.get('OPENROUTER_API_KEY')
if not key:
    sys.exit('no OpenRouter key: set OPENROUTER_API_KEY through your secret manager')
model = os.environ.get('BENCH_GLM_MODEL', 'z-ai/glm-5.3-flash')
cfg = {
    'llmProviders': {'custom': {'enabled': True, 'apiKey': key,
                                'baseUrl': 'https://openrouter.ai/api/v1', 'reasoningEffort': 'high'}},
    'selectedModel': f'custom::{model}',
    # Output cap per request. Proto's default is 16,384; a thinking model at
    # high effort truncates there (finish=length) and the request is wasted.
    'llm': {'maxTokens': int(os.environ.get('BENCH_MAX_TOKENS', '65536'))},
}
# BENCH_HOME_NAME lets the council tiers (proto-sol, proto-glm53, proto-nano) share this recipe.
d = os.path.join(ROOT, 'homes', os.environ.get('BENCH_HOME_NAME', 'proto-glm'), '.proto'); os.makedirs(d, exist_ok=True)
p = os.path.join(d, 'config.json'); json.dump(cfg, open(p, 'w'), indent=2); os.chmod(p, 0o600)
print(f'wrote {os.path.relpath(p, ROOT)} (model custom::{model}, key length {len(key)})')
