from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


# notification/realtime.py
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.cache import cache

logger = logging.getLogger(__name__)


def push_to_user(user_id, message, notif_type="info", event=None):
    print(f"[DEBUG] push_to_user called with user_id={user_id} type={type(user_id)}")
    payload = {
        "type":    notif_type,
        "event":   event or notif_type,
        "message": message,
    }

    # 1. Try live WebSocket push
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {"type": "send_notification", "message": payload}
            )
            print(f"[RealTime] ✅ Live push to user_{user_id}")
    except Exception as e:
        print(f"[RealTime] ❌ Live push failed: {e}")

    # 2. Always store in cache for pending delivery
    cache_key = f"pending_notif_{user_id}"
    pending   = cache.get(cache_key) or []
    pending.append(payload)
    cache.set(cache_key, pending, timeout=300)
    print(f"[RealTime] 📦 Stored pending for user_{user_id} — total: {len(pending)}")


def push_to_all(message, notif_type="info", event="broadcast"):
    logger = logging.getLogger(__name__)
    
    payload = {
        "type":    notif_type,
        "event":   event,
        "message": message,
    }

    # ✅ get fresh channel layer — same as push_to_user
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "broadcast_all",
                {"type": "send_notification", "message": payload}
            )
            logger.info(f"[push_to_all] ✅ Sent to broadcast_all: {message}")
        else:
            logger.error("[push_to_all] ❌ No channel layer available")
    except Exception as e:
        logger.error(f"[push_to_all] ❌ Failed: {e}")