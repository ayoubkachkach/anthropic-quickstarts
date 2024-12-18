import threading

import redis
from streamlit.runtime import Runtime
from streamlit.runtime.app_session import AppSession
from streamlit.runtime.scriptrunner import add_script_run_ctx


#### Helpers to notify Streamlit to rerun the rendering loop from another thread ####
def get_streamlit_sessions() -> list[AppSession]:
    runtime: Runtime = Runtime.instance()
    return [s.session for s in runtime._session_mgr.list_sessions()]


def notify() -> None:
    for session in get_streamlit_sessions():
        session._handle_rerun_script_request()


#### Helpers to notify Streamlit to rerun the rendering loop from another thread ####

REDIS_HOST = "redis"
REDIS_PORT = 6379
PROMPT_EVENT_CHANNEL = "prompt_events"
RESPONSE_EVENT_CHANNEL = "response_events"

_redis_listener_thread = None
_listener_lock = threading.Lock()


def start_redis_listener(session_state, on_message):
    global _redis_listener_thread

    with _listener_lock:
        # We should limit this to one global listener.
        # Just relying on st.session_state didn't work for some reason, so let's do it the
        # old-fashioned way.
        if _redis_listener_thread is not None and _redis_listener_thread.is_alive():
            return

        if session_state.get("listener_started", False):
            return

        def threaded_listener():
            try:
                redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
                pubsub = redis_client.pubsub()
                pubsub.subscribe(PROMPT_EVENT_CHANNEL)

                for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            content = message["data"].decode("utf-8")
                            on_message(content)
                            # Notify Streamlit sessions to rerun the rendering loop
                            notify()
                        except Exception as e:
                            print(f"Error processing message: {e}")
            except Exception as e:
                print(f"Redis listener error: {e}")

        print("Starting Redis listener thread")
        _redis_listener_thread = threading.Thread(target=threaded_listener, daemon=True)
        add_script_run_ctx(_redis_listener_thread)
        _redis_listener_thread.start()

        session_state.listener_started = True


def publish(message):
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    redis_client.publish(RESPONSE_EVENT_CHANNEL, message)
