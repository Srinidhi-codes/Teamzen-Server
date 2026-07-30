# Bot Gateway (Telegram + Slack)

## Telegram
- Webhook: `POST /api/bot/telegram/`
- Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`
- Setup: `python manage.py set_telegram_webhook https://<host>/api/bot/telegram/`

## Slack (Sequence 6)
- Webhook (Events + Slash + Interactivity): `POST /api/bot/slack/`
- Env: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- Guidance: `python manage.py slack_bot_setup`
- Scopes: `chat:write`, `commands`, `im:history`, `im:read`, `users:read`, `app_mentions:read`
- Slash: `/teamzen`, `/leaves`, `/checkin`, `/checkout`, `/payslip`, `/balance`
- Auth: same OTP email flow as Telegram (`BotSession.platform=slack`, `chat_id` = Slack user id)
- Check-in on Slack: reply with `lat,lng` after starting check-in (or use web/mobile)

Both platforms share `BotService` and proactive `notify_bot_user`.
