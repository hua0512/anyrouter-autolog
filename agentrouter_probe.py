"""Manual probe of AgentRouter's actual check-in path without logging credentials."""

import asyncio
import json
import re
from html import unescape

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
    if not is_json:
        report_html(response.text)
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


def report_html(text):
    title = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
    visible = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text, flags=re.I | re.S)
    visible = unescape(re.sub(r'<[^>]+>', ' ', visible))
    visible = ' '.join(visible.split())[:600]
    print('[agent-probe] ' + json.dumps({
        'html_title': unescape(title.group(1)).strip() if title else None,
        'visible_text': visible,
        'challenge_markers': [v for v in ('captcha', 'aliyun', 'acw_sc__v2', 'verify', 'challenge', '访问受限', '验证') if v in text.lower()],
    }, ensure_ascii=False))


class DiagnosticClient(OriginalClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, event_hooks={'response': [inspect_response]})


async def main():
    accounts = load_accounts_config() or []
    account = next(a for a in accounts if a.provider == 'agentrouter')
    config = AppConfig.load_from_env()
    checkin.httpx.Client = DiagnosticClient
    success, _, _ = await checkin.check_in_account(account, 0, config)
    browser = await checkin.launch_async(headless=True)
    try:
        page = await browser.new_page()
        await page.context.add_cookies([
            {'name': name, 'value': value, 'domain': 'agentrouter.org', 'path': '/'}
            for name, value in account.cookies.items()
        ])
        await checkin.prepare_browser_page(page)
        await page.goto('https://agentrouter.org/login', wait_until='domcontentloaded')
        await checkin.wait_for_waf_ready(page)
        result = await page.evaluate("""async (userId) => {
            const response = await fetch('/api/user/self', {
                headers: {'new-api-user': userId}, credentials: 'include'
            });
            const text = await response.text();
            let data = null;
            try { data = JSON.parse(text); } catch (_) {}
            return {status: response.status, content_type: response.headers.get('content-type'),
                    valid_json: data !== null, success: data?.success === true,
                    html: data === null ? text : null};
        }""", str(account.api_user))
        html = result.pop('html')
        print('[agent-probe] browser_fetch ' + json.dumps(result))
        if html:
            report_html(html)
    finally:
        await browser.close()
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
