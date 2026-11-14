"""Manual probe of AgentRouter's actual check-in path without logging credentials."""

import asyncio
import json

import checkin
from utils.config import AppConfig, load_accounts_config

OriginalClient = checkin.httpx.Client


def inspect_response(response):
    response.read()
    try:
        response.json()
        is_json = True
    except ValueError:
        is_json = False
    print('[agent-probe] ' + json.dumps({
        'status': response.status_code,
        'content_type': response.headers.get('content-type'),
        'content_encoding': response.headers.get('content-encoding'),
        'server': response.headers.get('server'),
        'body_length': len(response.content),
        'valid_json': is_json,
        'first_8_bytes_hex': response.content[:8].hex() if not is_json else None,
        'accept_encoding': response.request.headers.get('accept-encoding'),
    }))


class DiagnosticClient(OriginalClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, event_hooks={'response': [inspect_response]})


async def main():
    accounts = load_accounts_config() or []
    account = next(a for a in accounts if a.provider == 'agentrouter')
    config = AppConfig.load_from_env()
    checkin.httpx.Client = DiagnosticClient
    success, _, _ = await checkin.check_in_account(account, 0, config)
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
