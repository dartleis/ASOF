#!/bin/bash
set -a
source /home/pi/ASOF/.env
set +a

WEBHOOK_URL="$DISCORD_WEBHOOK_URL"

# Run the bot and forward logs to Discord
/usr/bin/python3 -u /home/pi/ASOF/BotV1,5.py 2>&1 | while IFS= read -r line; do
    echo "$line"  # still log locally

    [ -z "$line" ] && continue

    ESCAPED=$(echo "$line" | sed 's/"/\\"/g')

	curl -s -H "Content-Type: application/json" \
    	 -d "{\"content\": \"${ESCAPED}\", \"allowed_mentions\": {\"parse\": []}}" \
     	"$WEBHOOK_URL" >/dev/null 2>&1

done

