from .db import init_db, log_action, get_connection, db_session
from .models import (
    add_account,
    remove_account,
    list_accounts,
    get_active_accounts,
    update_account_checked,
    add_video,
    video_exists,
    file_hash_exists,
    update_video_status,
    add_upload,
    get_last_upload,
    get_upload_queue,
    record_upload_failure,
    get_failed_uploads,
    add_proxy,
    remove_proxy,
    get_all_proxies,
    get_active_proxies,
    update_proxy_status,
    record_proxy_failure,
    update_analytics,
    get_analytics_summary,
    get_system_history
)

# Initialize database schema
init_db()
